from __future__ import annotations

from pathlib import Path

from opportunities_abroad.prefs import load_prefs


def test_example_prefs_load():
    path = Path(__file__).resolve().parents[1] / "prefs.example.yaml"
    prefs = load_prefs(path)
    assert "python" in [k.lower() for k in prefs.include_keywords]
    assert "Netherlands" in prefs.countries or "netherlands" in [c.lower() for c in prefs.countries]
    assert prefs.accept_remote is True
    assert prefs.source_is_enabled("remotive")
    assert prefs.source_is_enabled("arbeitnow")
