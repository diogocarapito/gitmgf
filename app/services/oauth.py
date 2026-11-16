"""GitHub and Google OAuth 2.0 (authorization code + PKCE) with a sync httpx client.

Authlib supplies the PKCE and token primitives; the flow is driven here so route handlers stay
synchronous (docs/DECISIONS.md D12). State lives in a short-lived signed cookie `gitmgf_oauth`.
"""

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
from authlib.common.security import generate_token
from authlib.oauth2.rfc7636 import create_s256_code_challenge
from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.config import get_settings
from app.models.enums import OAuthProvider
from app.services.auth import AuthError, OAuthProfile

COOKIE_NAME = "gitmgf_oauth"
COOKIE_MAX_AGE = 600
TIMEOUT = 10.0


@dataclass(frozen=True)
class ProviderConfig:
    authorize_url: str
    token_url: str
    scope: str


PROVIDERS = {
    OAuthProvider.github: ProviderConfig(
        "https://github.com/login/oauth/authorize",
        "https://github.com/login/oauth/access_token",
        "read:user user:email",
    ),
    OAuthProvider.google: ProviderConfig(
        "https://accounts.google.com/o/oauth2/v2/auth",
        "https://oauth2.googleapis.com/token",
        "openid email profile",
    ),
}


def enabled(provider: OAuthProvider) -> bool:
    settings = get_settings()
    return settings.github_enabled if provider == OAuthProvider.github else settings.google_enabled


def _client_credentials(provider: OAuthProvider) -> tuple[str, str]:
    s = get_settings()
    if provider == OAuthProvider.github:
        return s.github_client_id, s.github_client_secret
    return s.google_client_id, s.google_client_secret


def redirect_uri(provider: OAuthProvider) -> str:
    return f"{get_settings().base_url.rstrip('/')}/auth/{provider.value}/callback"


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().secret_key, salt="gitmgf-oauth")


def start(provider: OAuthProvider, next_path: str | None, lang: str, link: bool) -> tuple[str, str]:
    """Returns (authorize URL, signed state cookie value)."""
    cfg = PROVIDERS[provider]
    client_id, _ = _client_credentials(provider)
    state = generate_token(32)
    verifier = generate_token(64)
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri(provider),
        "response_type": "code",
        "scope": cfg.scope,
        "state": state,
        "code_challenge": create_s256_code_challenge(verifier),
        "code_challenge_method": "S256",
    }
    if provider == OAuthProvider.google:
        params["prompt"] = "select_account"
    cookie = _serializer().dumps(
        {"p": provider.value, "s": state, "v": verifier, "n": next_path, "l": lang, "k": link}
    )
    return f"{cfg.authorize_url}?{urlencode(params)}", cookie


def read_state(cookie_value: str | None, provider: OAuthProvider, state: str | None) -> dict[str, Any]:
    if not cookie_value or not state:
        raise AuthError("oauth_state")
    try:
        data = _serializer().loads(cookie_value, max_age=COOKIE_MAX_AGE)
    except BadSignature as exc:
        raise AuthError("oauth_state") from exc
    if data.get("p") != provider.value or data.get("s") != state:
        raise AuthError("oauth_state")
    return dict(data)


def exchange_code(provider: OAuthProvider, code: str, verifier: str, client: httpx.Client) -> str:
    client_id, client_secret = _client_credentials(provider)
    resp = client.post(
        PROVIDERS[provider].token_url,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri(provider),
            "client_id": client_id,
            "client_secret": client_secret,
            "code_verifier": verifier,
        },
        headers={"Accept": "application/json"},
    )
    if resp.status_code != 200:
        raise AuthError("oauth_failed")
    token = resp.json().get("access_token")
    if not token:
        raise AuthError("oauth_failed")
    return str(token)


def fetch_profile(provider: OAuthProvider, access_token: str, client: httpx.Client) -> OAuthProfile:
    headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
    if provider == OAuthProvider.github:
        user = client.get("https://api.github.com/user", headers=headers)
        emails = client.get("https://api.github.com/user/emails", headers=headers)
        if user.status_code != 200:
            raise AuthError("oauth_failed")
        data = user.json()
        primary = None
        if emails.status_code == 200:
            for item in emails.json():
                if item.get("primary") and item.get("verified"):
                    primary = item.get("email")
                    break
        return OAuthProfile(
            provider=provider,
            provider_user_id=str(data["id"]),
            email=primary,
            email_verified=primary is not None,
            name=data.get("name") or data.get("login") or "",
            github_login=data.get("login"),
        )
    info = client.get("https://openidconnect.googleapis.com/v1/userinfo", headers=headers)
    if info.status_code != 200:
        raise AuthError("oauth_failed")
    data = info.json()
    verified = data.get("email_verified") in (True, "true")
    return OAuthProfile(
        provider=provider,
        provider_user_id=str(data["sub"]),
        email=data.get("email"),
        email_verified=verified,
        name=data.get("name") or "",
    )


def http_client() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT, headers={"User-Agent": "gitmgf"})
