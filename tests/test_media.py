import io

import pytest
from PIL import Image

from app.models.enums import MediaState
from app.services import media
from app.services import tools as svc
from app.services.media import MediaError
from tests.conftest import login, make_user, post
from tests.factories import make_tool


def png_with_exif(size=(2400, 1200)) -> bytes:
    image = Image.new("RGB", size, (10, 120, 110))
    exif = Image.Exif()
    exif[0x010F] = "SecretCamera"  # Make
    exif[0x8825] = {2: (38.0, 42.0, 0.0)}  # GPS
    buf = io.BytesIO()
    image.save(buf, "JPEG", exif=exif.tobytes())
    return buf.getvalue()


def test_reencodes_to_webp_resizes_and_strips_metadata(db_path):
    processed = media.process(png_with_exif(), tool_id=1)
    out = Image.open(media.tool_dir(1) / processed.file_name)
    assert out.format == "WEBP" and out.width == 1600
    assert not out.getexif()
    assert b"SecretCamera" not in (media.tool_dir(1) / processed.file_name).read_bytes()
    thumb = Image.open(media.tool_dir(1) / processed.thumb_name)
    assert thumb.width == 480


def test_rejects_non_images_by_content_not_extension(db_path):
    with pytest.raises(MediaError):
        media.process(b"<html><script>alert(1)</script></html>", tool_id=1)
    gif = io.BytesIO()
    Image.new("RGB", (10, 10)).save(gif, "GIF")
    with pytest.raises(MediaError):
        media.process(gif.getvalue(), tool_id=1)


def test_rejects_oversized_files(db_path):
    with pytest.raises(MediaError):
        media.process(b"\x89PNG" + b"0" * (media.MAX_BYTES + 1), tool_id=1)


def test_upload_route_draft_is_live_and_limit_is_five(client, db):
    owner = make_user(db, "o@example.org")
    tool = make_tool(db, owner, status="draft")
    login(client, db, owner)
    for i in range(5):
        r = post(
            client,
            f"/me/tools/{tool.id}/media",
            {"alt_text_pt": f"Ecrã {i}"},
            files={"file": ("a.jpg", png_with_exif((800, 600)), "image/jpeg")},
        )
        assert r.status_code == 303, r.text[-500:]
    db.refresh(tool)
    assert [m.state for m in tool.media] == [MediaState.live] * 5
    r = post(
        client,
        f"/me/tools/{tool.id}/media",
        {"alt_text_pt": "Sexta"},
        files={"file": ("a.jpg", png_with_exif((800, 600)), "image/jpeg")},
    )
    assert r.status_code == 422 and "Máximo de 5" in r.text


def test_alt_text_is_required(client, db):
    owner = make_user(db, "o@example.org")
    tool = make_tool(db, owner, status="draft")
    login(client, db, owner)
    r = post(
        client,
        f"/me/tools/{tool.id}/media",
        {"alt_text_pt": ""},
        files={"file": ("a.jpg", png_with_exif((800, 600)), "image/jpeg")},
    )
    assert r.status_code == 422


def test_media_on_published_tool_goes_through_revision(db):
    owner = make_user(db, "o@example.org")
    mod = make_user(db, "m@example.org")
    from app.models.enums import Role

    mod.role = Role.moderator
    db.commit()
    tool = make_tool(db, owner, status="published", moderator=mod)
    item = svc.add_media(db, tool, owner, png_with_exif((800, 600)), "Novo ecrã", None)
    db.commit()
    assert item.state == MediaState.pending and tool.live_media == []
    revision = svc.pending_revision(db, tool)
    assert revision.data["media_order"] == [item.id]
    svc.approve_revision(db, revision, mod)
    db.commit()
    assert [m.id for m in tool.live_media] == [item.id]


def test_card_shows_the_first_live_screenshot(client, db):
    from app.models.enums import Role

    owner = make_user(db, "o@example.org")
    mod = make_user(db, "m@example.org", Role.moderator)
    with_shot = make_tool(db, owner, status="draft", title_pt="Com imagem")
    first = svc.add_media(db, with_shot, owner, png_with_exif((800, 600)), "Primeiro ecrã", None)
    svc.add_media(db, with_shot, owner, png_with_exif((800, 600)), "Segundo ecrã", None)
    db.commit()
    svc.transition(db, with_shot, "submit", owner)
    svc.transition(db, with_shot, "approve", mod)
    plain = make_tool(db, owner, status="published", moderator=mod, title_pt="Sem imagem")
    pending = svc.add_media(db, plain, owner, png_with_exif((800, 600)), "Por rever", None)
    db.commit()
    html = client.get("/").text
    assert f'src="/media/tools/{with_shot.id}/{first.thumb_name}"' in html
    assert pending.thumb_name not in html  # pending screenshots stay off the card
    assert html.count("card__media--empty") >= 1


def test_form_says_the_first_screenshot_is_the_card_image(client, db):
    owner = make_user(db, "o@example.org")
    tool = make_tool(db, owner, status="draft")
    svc.add_media(db, tool, owner, png_with_exif((800, 600)), "Ecrã", None)
    db.commit()
    login(client, db, owner)
    assert "A primeira imagem aparece no cartão" in client.get("/me/tools/new").text
    edit = client.get(f"/me/tools/{tool.id}/edit").text
    assert "A primeira imagem aparece no cartão" in edit and "Imagem do cartão" in edit


def test_submit_buttons_come_after_the_screenshots(client, db):
    owner = make_user(db, "o@example.org")
    draft = make_tool(db, owner, status="draft")
    live = make_tool(db, owner, title_pt="Publicada", status="published")
    db.commit()
    login(client, db, owner)
    for url, button in (
        ("/me/tools/new", "Guardar e submeter para revisão"),
        (f"/me/tools/{draft.id}/edit", "Guardar e submeter para revisão"),
        (f"/me/tools/{live.id}/edit", "Submeter alteração para revisão"),
    ):
        html = client.get(url).text
        assert html.index('id="screenshots"') < html.index("decl_author") < html.index(button), url
        # outside the main form, so they must be tied to it explicitly
        assert html.count('form="tool-form"') == 3 + html.count('type="submit" form="tool-form"'), url
