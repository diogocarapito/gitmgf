from datetime import date

import pytest
import time_machine

from app.models.enums import ClaimState, Role
from app.services import certifications as certs
from app.services import search
from app.services import tools as svc
from tests.conftest import login, make_user, post
from tests.factories import make_tool, tool_form

MDR_IIA = {
    "class": "IIa",
    "nb_number": "0123",
    "certificate_no": "C-1",
    "valid_until": "2028-05-01",
    "evidence_url": "https://nb.example/cert",
}
CE = {"legal_basis": "MDR", "manufacturer": "ACME", "evidence_url": "https://acme.example/doc"}


@pytest.fixture
def catalogue(db):
    return certs.by_code(db)


def test_field_schema_validation(catalogue):
    _, errors = certs.validate_claim(
        catalogue["mdr"], {"class": "IIa", "evidence_url": "https://x.example"}, full=True
    )
    assert {"nb_number", "certificate_no", "valid_until"} <= set(errors)  # required_if
    _, errors = certs.validate_claim(
        catalogue["mdr"], {"class": "I", "evidence_url": "https://x.example"}, full=True
    )
    assert errors == {}
    _, errors = certs.validate_claim(
        catalogue["mdr"], {"class": "IIa", "nb_number": "123", "evidence_url": "ftp://x"}, full=False
    )
    assert "nb_number" in errors and "evidence_url" in errors
    _, errors = certs.validate_claim(catalogue["mdr"], {"class": "IV"}, full=False)
    assert "class" in errors


def test_mdr_auto_enables_ce_with_legal_basis(catalogue):
    check = certs.check_claims(
        catalogue,
        {"mdr": {"class": "I", "evidence_url": "https://x.example"}},
        "none",
        full=False,
    )
    assert check.claims["ce"]["legal_basis"] == "MDR"
    check = certs.check_claims(
        catalogue,
        {"ivdr": {"class": "A", "evidence_url": "https://x.example"}},
        "none",
        full=True,
    )
    assert check.claims["ce"]["legal_basis"] == "IVDR"
    assert "cert_ce__manufacturer" in check.errors  # CE now needs its own fields


def test_warning_for_server_data_without_rgpd(catalogue):
    check = certs.check_claims(catalogue, {}, "server", full=False)
    assert len(check.warnings) == 1


def test_ai_tools_get_no_ai_act_hint(catalogue):
    """D45: the AI Act is optional for AI tools, like every other certification."""
    check = certs.check_claims(catalogue, {}, "none", full=False)
    assert check.warnings == []


def test_assurance_resolution(catalogue):
    assert certs.resolve_assurance(catalogue["mdr"], {"class": "I"}).value == "self_declared"
    assert certs.resolve_assurance(catalogue["mdr"], {"class": "IIb"}).value == "third_party"
    assert certs.resolve_assurance(catalogue["rgpd"], {}).value == "self_declared"


def test_prd_acceptance_mdr_iia_badges_filters_and_expiry(db):
    """PRD F20 acceptance: CE + MDR IIa coloured, RGPD slashed; leaves the MDR filter the day after expiry."""
    tool = make_tool(db, claims={"mdr": MDR_IIA, "ce": CE})
    with time_machine.travel(date(2027, 1, 1), tick=False):
        badges = {b.code: b for b in certs.badges_for(db, [tool.id], "pt")[tool.id]}
        assert badges["ce"].present and badges["mdr"].present and badges["mdr"].label == "MDR IIa"
        assert not badges["rgpd"].present
        assert [b.code for b in badges.values() if not b.present] == ["rgpd"]
        ids = search.search(db, search.SearchParams(cert=["mdr"])).ids
        assert tool.id in ids
        assert tool.id in search.search(db, search.SearchParams(cert=["ce", "mdr"])).ids
        assert (
            tool.id not in search.search(db, search.SearchParams(cert=["mdr", "rgpd"])).ids
        )  # AND semantics
    with time_machine.travel(date(2028, 5, 2), tick=False):
        badges = {b.code: b for b in certs.badges_for(db, [tool.id], "pt")[tool.id]}
        assert not badges["mdr"].present and badges["mdr"].expired
        assert tool.id not in search.search(db, search.SearchParams(cert=["mdr"])).ids


def test_core_items_always_present_additional_only_when_declared(db):
    tool = make_tool(db)
    codes = [b.code for b in certs.badges_for(db, [tool.id], "pt")[tool.id]]
    assert codes == ["ce", "mdr", "rgpd"]
    tool2 = make_tool(
        db,
        title_pt="Com ISO",
        claims={
            "iso27001": {
                "certification_body": "X",
                "certificate_no": "1",
                "valid_until": "2030-01-01",
                "evidence_url": "https://x.example",
            }
        },
    )
    codes = [b.code for b in certs.badges_for(db, [tool2.id], "pt")[tool2.id]]
    assert codes == ["ce", "mdr", "rgpd", "iso27001"]


def test_pending_or_rejected_claims_are_not_present(db):
    owner = make_user(db, "o@example.org")
    tool = make_tool(
        db,
        owner,
        status="pending",
        claims={"rgpd": {"evidence_url": "https://x.example/p", "data_location": "eu_eea"}},
    )
    assert not any(b.present for b in certs.badges_for(db, [tool.id], "pt")[tool.id])
    mod = make_user(db, "m@example.org", Role.moderator)
    svc.transition(db, tool, "approve", mod, claim_rejections={"rgpd": "A política de privacidade não abre."})
    db.commit()
    claim = tool.claims[0]
    assert claim.state == ClaimState.rejected and tool.status.value == "published"
    assert not any(b.present for b in certs.badges_for(db, [tool.id], "pt")[tool.id])


def test_removal_on_published_tool_is_immediate_additions_go_through_revision(db):
    owner = make_user(db, "o@example.org")
    tool = make_tool(db, owner, claims={"mdr": MDR_IIA, "ce": CE})
    data = {k: v for k, v in svc.snapshot(tool).items() if k not in ("certifications", "media_order")}
    # remove MDR (keep CE), add RGPD
    rgpd = {"evidence_url": "https://x.example/p", "data_location": "eu_eea"}
    claims = {"ce": CE, "rgpd": rgpd}
    outcome = svc.save_edit(db, tool, owner, data, claims, True)
    db.commit()
    assert outcome == "revision"
    present = {b.code for b in certs.badges_for(db, [tool.id], "pt")[tool.id] if b.present}
    assert present == {"ce"}  # MDR removed now; RGPD waits for review


def test_badges_render_with_accessible_labels(client, db):
    tool = make_tool(db, claims={"mdr": MDR_IIA, "ce": CE})
    html = client.get(f"/t/{tool.slug}").text
    assert "cert--present" in html and "cert--absent" in html
    assert "Com Marcação CE" in html and "Sem Conformidade RGPD (autodeclarada)" in html
    assert "N.º do organismo notificado" in html and "0123" in html


def test_class_iia_without_notified_body_blocks_submission(client, db):
    owner = make_user(db, "o@example.org")
    login(client, db, owner)
    form = {
        **tool_form(db),
        "intent": "submit",
        "cert_mdr": "1",
        "cert_mdr__class": "IIa",
        "cert_mdr__evidence_url": "https://x.example",
    }
    r = post(client, "/me/tools/new", form)
    assert r.status_code == 422
    assert "cert_mdr__nb_number-error" in r.text
