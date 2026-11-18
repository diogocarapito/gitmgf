"""Screenshots and profile photos: the only user files. Always re-encoded; original bytes are never stored or served (TECH_SPEC §12, D33)."""

import io
import uuid
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import get_settings

MAX_BYTES = 2 * 1024 * 1024
MAX_PER_TOOL = 5
MAX_WIDTH = 1600
THUMB_WIDTH = 480
AVATAR_SIZE = 256
ALLOWED_FORMATS = {"PNG", "JPEG", "WEBP"}
Image.MAX_IMAGE_PIXELS = 25_000_000


class MediaError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message  # msgid


@dataclass(frozen=True)
class ProcessedImage:
    file_name: str
    thumb_name: str
    width: int
    height: int


def tool_dir(tool_id: int) -> Path:
    return get_settings().media_dir / "tools" / str(tool_id)


def url_for(tool_id: int, file_name: str) -> str:
    return f"/media/tools/{tool_id}/{file_name}"


def _load(data: bytes) -> Image.Image:
    from app.i18n import N_

    if len(data) > MAX_BYTES:
        raise MediaError(N_("A imagem excede 2 MB."))
    if not data:
        raise MediaError(N_("Escolha um ficheiro de imagem."))
    try:
        probe = Image.open(io.BytesIO(data))
        fmt = probe.format
        probe.verify()  # structural check; the object is unusable afterwards
        if fmt not in ALLOWED_FORMATS:
            raise MediaError(N_("Formato não suportado. Use PNG, JPEG ou WebP."))
        image = Image.open(io.BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError) as exc:
        raise MediaError(N_("O ficheiro não é uma imagem válida.")) from exc
    return image


def _normalise(image: Image.Image) -> Image.Image:
    image = ImageOps.exif_transpose(image) or image  # honour orientation, then drop all metadata
    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA" if "A" in image.getbands() or image.mode == "P" else "RGB")
    clean = Image.new(image.mode, image.size)
    clean.paste(image)
    return clean


def _resize(image: Image.Image, width: int) -> Image.Image:
    if image.width <= width:
        return image.copy()
    height = round(image.height * width / image.width)
    return image.resize((width, height), Image.Resampling.LANCZOS)


def process(data: bytes, tool_id: int) -> ProcessedImage:
    image = _normalise(_load(data))
    full = _resize(image, MAX_WIDTH)
    thumb = _resize(image, THUMB_WIDTH)
    directory = tool_dir(tool_id)
    directory.mkdir(parents=True, exist_ok=True)
    stem = uuid.uuid4().hex
    file_name, thumb_name = f"{stem}.webp", f"{stem}-t.webp"
    full.save(directory / file_name, "WEBP", quality=82, method=4)
    thumb.save(directory / thumb_name, "WEBP", quality=80, method=4)
    return ProcessedImage(file_name, thumb_name, full.width, full.height)


def avatar_dir(user_id: int) -> Path:
    return get_settings().media_dir / "avatars" / str(user_id)


def avatar_url(user_id: int, file_name: str) -> str:
    return f"/media/avatars/{user_id}/{file_name}"


def process_avatar(data: bytes, user_id: int) -> str:
    """Square centre crop, 256 px WebP, no metadata. A new file name on every upload (immutable caching)."""
    image = _normalise(_load(data))
    side = min(image.width, image.height)
    left, top = (image.width - side) // 2, (image.height - side) // 2
    square = image.crop((left, top, left + side, top + side))
    if side > AVATAR_SIZE:
        square = square.resize((AVATAR_SIZE, AVATAR_SIZE), Image.Resampling.LANCZOS)
    directory = avatar_dir(user_id)
    directory.mkdir(parents=True, exist_ok=True)
    file_name = f"{uuid.uuid4().hex}.webp"
    square.save(directory / file_name, "WEBP", quality=82, method=4)
    return file_name


def delete_avatar(user_id: int, file_name: str | None) -> None:
    if file_name and "/" not in file_name and ".." not in file_name:
        (avatar_dir(user_id) / file_name).unlink(missing_ok=True)


def delete_files(tool_id: int, *names: str) -> None:
    directory = tool_dir(tool_id)
    for name in names:
        if name and "/" not in name and ".." not in name:
            (directory / name).unlink(missing_ok=True)


def delete_tool_dir(tool_id: int) -> None:
    directory = tool_dir(tool_id)
    if directory.is_dir():
        for path in directory.iterdir():
            path.unlink(missing_ok=True)
        directory.rmdir()
