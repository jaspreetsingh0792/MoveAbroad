from __future__ import annotations

import pytest

from opportunities_abroad import cli
from opportunities_abroad.sources.base import JobSource

from tests.conftest import make_job

PREFS_YAML = """
include_keywords: [python]
locations:
  countries: [Netherlands]
sources:
  remotive: false
  arbeitnow: false
  adzuna: false
  greenhouse: false
  lever: false
  ashby: false
digest:
  max_jobs: 10
"""


class StubSource(JobSource):
    name = "stub"

    def fetch(self, prefs):
        return [make_job(title="Senior Python Engineer", location="Amsterdam, Netherlands")]


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    prefs_path = tmp_path / "prefs.yaml"
    prefs_path.write_text(PREFS_YAML, encoding="utf-8")
    monkeypatch.setattr(cli, "build_sources", lambda prefs: [StubSource()])
    monkeypatch.chdir(tmp_path)
    return tmp_path, prefs_path


def run_cli(workspace, *extra):
    tmp_path, prefs_path = workspace
    return cli.main(
        ["--prefs", str(prefs_path), "--db", str(tmp_path / "seen.db"), *extra],
    )


def test_dry_run_prints_a_grouped_digest(workspace, capsys):
    assert run_cli(workspace) == 0
    out = capsys.readouterr().out
    assert "DRY-RUN matches (not emailed)" in out
    assert "1 new · 0 already seen · 0 too old · 0 rejected" in out
    assert "Netherlands (1)" in out
    assert "Senior Python Engineer @ Acme" in out


def test_save_html_flag_writes_on_a_dry_run(workspace, capsys):
    tmp_path, _ = workspace
    target = tmp_path / "out" / "digest.html"
    assert run_cli(workspace, "--save-html", str(target)) == 0

    body = target.read_text(encoding="utf-8")
    assert "Opportunities Abroad" in body
    assert "Senior Python Engineer" in body
    assert str(target) in capsys.readouterr().out


def test_save_html_pref_is_used_when_the_flag_is_absent(workspace):
    tmp_path, prefs_path = workspace
    prefs_path.write_text(
        PREFS_YAML + "\n  save_html_to: from-prefs.html\n",
        encoding="utf-8",
    )
    assert run_cli(workspace) == 0
    assert (tmp_path / "from-prefs.html").exists()


def test_flag_wins_over_the_pref(workspace):
    tmp_path, prefs_path = workspace
    prefs_path.write_text(
        PREFS_YAML + "\n  save_html_to: from-prefs.html\n",
        encoding="utf-8",
    )
    assert run_cli(workspace, "--save-html", "from-flag.html") == 0
    assert (tmp_path / "from-flag.html").exists()
    assert not (tmp_path / "from-prefs.html").exists()


class BrokenSource(JobSource):
    name = "broken"

    def fetch(self, prefs):
        raise RuntimeError("upstream is down")


def test_source_failure_is_visible_but_not_fatal_by_default(workspace, monkeypatch, capsys):
    monkeypatch.setattr(cli, "build_sources", lambda prefs: [StubSource(), BrokenSource()])
    assert run_cli(workspace) == 0
    out = capsys.readouterr().out
    assert "Source problems this run: broken" in out
    assert "broken: FAILED" in out


def test_fail_on_source_error_makes_the_run_go_red(workspace, monkeypatch, capsys):
    monkeypatch.setattr(cli, "build_sources", lambda prefs: [StubSource(), BrokenSource()])
    assert run_cli(workspace, "--fail-on-source-error") == 1
    assert "Source errors this run" in capsys.readouterr().err


def test_fail_on_source_error_passes_when_sources_are_healthy(workspace):
    assert run_cli(workspace, "--fail-on-source-error") == 0


def test_missing_prefs_file_is_a_clean_failure(tmp_path, capsys):
    assert cli.main(["--prefs", str(tmp_path / "nope.yaml")]) == 2
    assert "Preferences file not found" in capsys.readouterr().err


def test_send_without_smtp_settings_fails_fast(workspace, monkeypatch, capsys):
    for key in ("SMTP_HOST", "EMAIL_FROM", "EMAIL_TO"):
        monkeypatch.delenv(key, raising=False)
    assert run_cli(workspace, "--send") == 2
    assert "Email notifier is not configured" in capsys.readouterr().err


def test_no_enabled_sources_is_reported(workspace, monkeypatch, capsys):
    monkeypatch.setattr(cli, "build_sources", lambda prefs: [])
    assert run_cli(workspace) == 2
    assert "No sources enabled" in capsys.readouterr().err
