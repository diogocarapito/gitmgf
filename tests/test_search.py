import pytest

from app.services import search
from app.services.search import SearchParams
from tests.factories import make_tool


def ids(db, **kwargs):
    return search.search(db, SearchParams(**kwargs)).ids


@pytest.fixture
def corpus(db):
    score2 = make_tool(
        db,
        title_pt="Calculadora SCORE2",
        title_en="SCORE2 calculator",
        summary_pt="Escala de risco cardiovascular a 10 anos.",
        summary_en="10-year cardiovascular risk score.",
        tags="score2, risco cardiovascular, escala de risco",
    )
    diabetes = make_tool(
        db,
        title_pt="Cálculo da dose de insulina",
        summary_pt="Ajuste de insulina na diabetes tipo 2.",
        tool_type="webapp",
        platforms=["android"],
        care_setting="hospital",
        license_spdx="proprietary",
        pricing="paid",
        tags="diabetes",
        tool_languages=["pt", "en"],
    )
    vacinas = make_tool(
        db,
        title_pt="Plano de vacinação",
        summary_pt="Esquema vacinal por idade.",
        care_setting="both",
        tags="pnv",
    )
    return score2, diabetes, vacinas


def test_prd_acceptance_score2(db, corpus):
    score2 = corpus[0]
    assert ids(db, q="escala de risco cardiovascular")[0] == score2.id
    assert ids(db, q="SCORE2")[0] == score2.id


def test_accent_insensitive_and_prefix(db, corpus):
    _, diabetes, vacinas = corpus
    assert diabetes.id in ids(db, q="calculo")  # "Cálculo"
    assert diabetes.id in ids(db, q="diab")  # prefix
    assert vacinas.id in ids(db, q="vacinacao")


def test_english_fields_are_searched(db, corpus):
    assert corpus[0].id in ids(db, q="calculator")


def test_categories_are_searched_in_both_languages(db, corpus):
    assert corpus[0].id in ids(db, q="cardiology")  # category name in EN


def test_or_fallback_marks_partial(db, corpus):
    result = search.search(db, SearchParams(q="vacinação inexistentepalavra"))
    assert result.partial and corpus[2].id in result.ids


@pytest.mark.parametrize(
    "evil", ['"', "*", "NEAR(a b)", "-", "a OR", "^x", "col:x", "(((", "'; DROP TABLE tools; --", "\x00"]
)
def test_fts_injection_strings_do_not_error(db, corpus, evil):
    search.search(db, SearchParams(q=evil))


def test_filters(db, corpus):
    score2, diabetes, vacinas = corpus
    assert ids(db, type="webapp") == [diabetes.id]
    assert ids(db, platform=["android"]) == [diabetes.id]
    assert set(ids(db, oss=True)) == {score2.id, vacinas.id}
    assert set(ids(db, free=True)) == {score2.id, vacinas.id}
    assert set(ids(db, setting="hospital")) == {diabetes.id, vacinas.id}  # "both" counts for each setting
    assert ids(db, lang="en") == [diabetes.id]
    assert set(ids(db, cat=["cardiologia"])) == {score2.id, diabetes.id, vacinas.id}


def test_published_and_unvalidated_tools_are_found_but_not_drafts(db):
    make_tool(db, status="draft", title_pt="Rascunho secreto")
    pending = make_tool(db, status="pending", title_pt="Pendente secreto")
    rejected_before = make_tool(db, status="pending", title_pt="Rejeitada antes secreto")
    from app.db import utcnow
    from app.services import search

    rejected_before.rejected_at = utcnow()  # resubmitted after a rejection: hidden until approved (D43)
    db.commit()
    search.reindex_tool(db, rejected_before.id)
    assert ids(db, q="secreto") == [pending.id]


def test_ranking_blends_popularity(db):
    quiet = make_tool(db, title_pt="Escala de Barthel A")
    popular = make_tool(db, title_pt="Escala de Barthel B")
    popular.score, popular.score_log = 500.0, 6.2
    db.commit()
    assert ids(db, q="barthel")[:2] == [popular.id, quiet.id]
    assert ids(db, sort="new")[0] == popular.id  # created last


def test_search_page_without_js_and_htmx_partial(client, db, corpus):
    r = client.get("/search?q=vacina&sort=new")
    assert r.status_code == 200 and "Plano de vacinação" in r.text and '<form id="search-form"' in r.text
    r = client.get("/search?q=vacina", headers={"HX-Request": "true"})
    assert r.text.startswith('<div id="results"') and "<html" not in r.text


def test_unknown_filter_values_are_ignored(client, db, corpus):
    r = client.get("/search?type=nope&platform=xx&cert=%27&page=-3&sort=evil")
    assert r.status_code == 200


def test_category_page_is_prefiltered(client, db, corpus):
    r = client.get("/c/cardiologia")
    assert r.status_code == 200 and "Calculadora SCORE2" in r.text
    assert client.get("/c/nao-existe").status_code == 404
