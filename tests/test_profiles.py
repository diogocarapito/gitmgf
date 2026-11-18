import io

from PIL import Image
from sqlalchemy import select

from app.models import AuditLog
from app.models.enums import Role, UserStatus
from app.services import email, gdpr, media
from tests.conftest import login, make_user, post
from tests.factories import make_tool


def jpeg(size=(900, 600), exif=True) -> bytes:
    image = Image.new("RGB", size, (200, 60, 60))
    buf = io.BytesIO()
    if exif:
        meta = Image.Exif()
        meta[0x010F] = "SecretCamera"
        image.save(buf, "JPEG", exif=meta.tobytes())
    else:
        image.save(buf, "JPEG")
    return buf.getvalue()


def _upload(client, data, name="eu.jpg"):
    return post(client, "/me/avatar", {}, files={"avatar": (name, data, "image/jpeg")})


def test_photo_is_square_webp_without_metadata_and_replaces_the_old_one(client, db):
    user = make_user(db, "ana@example.org")
    login(client, db, user)
    assert _upload(client, jpeg()).status_code == 303
    db.refresh(user)
    first = media.avatar_dir(user.id) / user.avatar_name
    out = Image.open(first)
    assert out.format == "WEBP" and out.size == (256, 256) and not out.getexif()
    assert b"SecretCamera" not in first.read_bytes()
    assert _upload(client, jpeg((300, 300), exif=False)).status_code == 303
    db.refresh(user)
    assert not first.exists() and (media.avatar_dir(user.id) / user.avatar_name).exists()
    assert post(client, "/me/avatar/delete").status_code == 303
    db.refresh(user)
    assert user.avatar_name is None and not any(media.avatar_dir(user.id).iterdir())


def test_bad_files_are_rejected(client, db):
    login(client, db, make_user(db, "ana@example.org"))
    r = _upload(client, b"<svg onload=alert(1)>", "x.svg")
    assert r.status_code == 422 and "imagem" in r.text.lower()


def test_photo_replaces_the_letter_avatar_on_cards_tool_page_and_header(client, db):
    owner = make_user(db, "ana@example.org")
    tool = make_tool(db, owner)
    login(client, db, owner)
    _upload(client, jpeg())
    db.refresh(owner)
    src = f'src="/media/avatars/{owner.id}/{owner.avatar_name}"'
    assert client.get("/").text.count(src) >= 2  # header + card
    page = client.get(f"/t/{tool.slug}").text
    assert src in page and f'href="/u/{owner.handle}"' in page


def test_profile_page_lists_published_tools_and_role(client, db):
    mod = make_user(db, "rui@example.org", Role.moderator, name="Rui Rodrigues")
    mod.workplace = "USF Segredo"
    db.commit()
    other_mod = make_user(db, "outro@example.org", Role.moderator)
    published = make_tool(db, mod, moderator=other_mod, title_pt="Calculadora publicada")
    make_tool(db, mod, status="draft", title_pt="Rascunho escondido")
    page = client.get(f"/u/{mod.handle}")
    assert page.status_code == 200
    assert "Rui Rodrigues" in page.text and "Moderador/a" in page.text
    assert "Calculadora publicada" in page.text and "Rascunho escondido" not in page.text
    assert "USF Segredo" not in page.text and "rui@example.org" not in page.text
    assert 'name="robots"' not in page.text
    assert f"/u/{mod.handle}</loc>" in client.get("/sitemap.xml").text
    assert f'href="/u/{mod.handle}"' in client.get(f"/t/{published.slug}").text
    assert client.get(f"/en/u/{mod.handle}").status_code == 200


def test_profiles_without_tools_are_noindex_and_hidden_ones_404(client, db):
    user = make_user(db, "sem@example.org")
    assert 'content="noindex"' in client.get(f"/u/{user.handle}").text
    user.status = UserStatus.suspended
    db.commit()
    assert client.get(f"/u/{user.handle}").status_code == 404
    assert client.get("/u/ninguem").status_code == 404
    pending = make_user(db, "novo@example.org", onboarded=False)
    pending.handle = "novo"
    db.commit()
    assert client.get("/u/novo").status_code == 404


def test_admin_removes_a_photo_with_a_reason_emailed_and_audited(client, db):
    admin = make_user(db, "admin@example.org", Role.admin)
    target = make_user(db, "ana@example.org")
    login(client, db, target)
    _upload(client, jpeg())
    login(client, db, admin)
    r = post(client, f"/admin/users/{target.id}/avatar/delete", {"reason": ""})
    assert "reason_required" in r.headers["location"]
    r = post(client, f"/admin/users/{target.id}/avatar/delete", {"reason": "Imagem com dados de utente"})
    assert "avatar_removed" in r.headers["location"]
    db.refresh(target)
    assert target.avatar_name is None
    mail = [m for m in email.SENT if m["To"] == "ana@example.org"][-1]
    assert "Imagem com dados de utente" in mail.get_body(preferencelist=("plain",)).get_content()
    entry = db.scalar(select(AuditLog).where(AuditLog.action == "user.avatar_remove"))
    assert entry.details["reason"] == "Imagem com dados de utente"


def test_photo_in_export_and_deleted_with_account(client, db):
    user = make_user(db, "ana@example.org")
    login(client, db, user)
    _upload(client, jpeg())
    db.refresh(user)
    path = media.avatar_dir(user.id) / user.avatar_name
    assert gdpr.export(db, user)["profile"]["profile_photo"].endswith(user.avatar_name)
    gdpr.delete_account(db, user, user)
    db.commit()
    assert user.avatar_name is None and not path.exists()
