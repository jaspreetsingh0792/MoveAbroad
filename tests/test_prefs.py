from __future__ import annotations

from pathlib import Path

from opportunities_abroad.prefs import load_prefs, prefs_from_dict


def test_example_prefs_load():
    path = Path(__file__).resolve().parents[1] / "prefs.example.yaml"
    prefs = load_prefs(path)
    assert "python" in [k.lower() for k in prefs.include_keywords]
    assert "Netherlands" in prefs.countries or "netherlands" in [c.lower() for c in prefs.countries]
    assert prefs.accept_remote is True
    assert prefs.source_is_enabled("remotive")
    assert prefs.source_is_enabled("arbeitnow")


def test_example_prefs_seed_ats_boards_and_title_filters():
    path = Path(__file__).resolve().parents[1] / "prefs.example.yaml"
    prefs = load_prefs(path)
    for ats in ("greenhouse", "lever", "ashby"):
        assert prefs.source_is_enabled(ats)
        assert prefs.boards_for(ats), f"{ats} should ship with example boards"
    lowered = [t.lower() for t in prefs.title_exclude]
    assert {"junior", "working student", "intern"} <= set(lowered)
    assert prefs.max_age_days == 14


def test_defaults_when_keys_are_absent():
    prefs = prefs_from_dict({})
    assert prefs.max_age_days == 14
    assert prefs.title_include == []
    assert prefs.boards_for("greenhouse") == []
    assert prefs.visa_require is False
    assert prefs.visa_classifier is False
    assert prefs.save_html_to is None
    assert prefs.weight("title_hit") == 8
    assert prefs.location_weights == {"netherlands": 6, "germany": 3, "europe": 3}


def test_score_weights_merge_and_location_weights_replace():
    prefs = prefs_from_dict(
        {
            "score_weights": {"remote": 10},
            "location_weights": {"Portugal": 4},
        }
    )
    assert prefs.weight("remote") == 10
    assert prefs.weight("title_hit") == 8
    assert prefs.location_weights == {"portugal": 4}


def test_ats_boards_accept_a_bare_string():
    prefs = prefs_from_dict({"ats_boards": {"lever": "acme"}})
    assert prefs.boards_for("lever") == ["acme"]


def test_visa_and_digest_blocks():
    prefs = prefs_from_dict(
        {
            "visa": {"require": True, "classifier": True},
            "digest": {"save_html_to": "out/digest.html", "max_jobs": 5},
        }
    )
    assert prefs.visa_require is True
    assert prefs.visa_classifier is True
    assert prefs.visa_classifier_model == "claude-sonnet-4-6"
    assert prefs.save_html_to == "out/digest.html"
    assert prefs.max_jobs == 5
