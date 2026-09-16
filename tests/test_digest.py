from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from opportunities_abroad.digest import (
    group_by_country,
    header_line,
    relative_age,
    render_console,
    render_html,
    render_text,
    save_html,
)
from opportunities_abroad.models import Match, RunResult, SourceHealth

from tests.conftest import make_job

NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)


def a_match(score: int = 10, **job_kwargs) -> Match:
    reasons = job_kwargs.pop("reasons", ["remote", "keywords:python"])
    sponsorship = job_kwargs.pop("sponsorship", None)
    sponsorship_reason = job_kwargs.pop("sponsorship_reason", None)
    return Match(
        job=make_job(**job_kwargs),
        score=score,
        reasons=reasons,
        sponsorship=sponsorship,
        sponsorship_reason=sponsorship_reason,
    )


@pytest.fixture
def result() -> RunResult:
    # The renderers read the real clock, so these ages must be relative to it.
    # Anchoring them to a fixed NOW made the suite pass only on that date.
    today = datetime.now(timezone.utc)
    return RunResult(
        matches=[
            a_match(
                score=40,
                source_id="1",
                title="Senior Python Engineer",
                location="Amsterdam, Netherlands",
                posted_at=today - timedelta(days=3),
                salary="€70k–90k",
                sponsorship="yes",
                sponsorship_reason="Offers relocation and a 30% ruling.",
            ),
            a_match(
                score=20,
                source_id="2",
                title="Backend Engineer",
                location="Berlin, Germany",
                posted_at=today - timedelta(days=1),
            ),
            a_match(
                score=30,
                source_id="3",
                title="Platform Engineer",
                location="Worldwide",
                remote=True,
            ),
        ],
        fetched=120,
        matched=9,
        already_seen=6,
        too_old=4,
        rejected_location=3,
        rejected_title=2,
        rejected_seniority=1,
        rejected_visa=1,
    )


def test_header_line_counts(result):
    assert header_line(result) == (
        "3 new · 6 already seen · 4 too old · 7 rejected (US-only / title / seniority / visa)"
    )


def test_header_line_mentions_a_backlog_only_when_there_is_one(result):
    assert "held for next run" not in header_line(result)
    result.backlog = 20
    assert "20 held for next run" in header_line(result)


def test_header_line_with_nothing_new():
    assert header_line(RunResult()) == (
        "0 new · 0 already seen · 0 too old · 0 rejected (US-only / title / seniority / visa)"
    )


@pytest.mark.parametrize(
    "posted_at,expected",
    [
        (None, ""),
        (NOW, "just now"),
        (NOW - timedelta(minutes=30), "just now"),
        (NOW - timedelta(hours=5), "5h ago"),
        (NOW - timedelta(hours=23), "23h ago"),
        (NOW - timedelta(days=1), "1d ago"),
        (NOW - timedelta(days=3), "3d ago"),
        (NOW - timedelta(days=45), "45d ago"),
    ],
)
def test_relative_age(posted_at, expected):
    assert relative_age(posted_at, now=NOW) == expected


def test_relative_age_assumes_utc_for_naive_dates():
    naive = (NOW - timedelta(days=2)).replace(tzinfo=None)
    assert relative_age(naive, now=NOW) == "2d ago"


def test_grouping_by_country_orders_by_score(result):
    groups = group_by_country(result.matches)
    assert [name for name, _ in groups] == ["Netherlands", "Remote", "Germany"]
    assert [m.job.source_id for m in groups[0][1]] == ["1"]


def test_other_bucket_sorts_last():
    matches = [
        a_match(score=99, source_id="a", location="Austin, Texas", remote=False, reasons=[]),
        a_match(score=1, source_id="b", location="Utrecht, Netherlands"),
    ]
    assert [name for name, _ in group_by_country(matches)] == ["Netherlands", "Other"]


def test_remote_bucket_only_catches_placeless_roles():
    matches = [a_match(source_id="a", location="Remote - Netherlands", remote=True)]
    assert group_by_country(matches)[0][0] == "Netherlands"


def test_text_digest_contains_every_detail(result):
    body = render_text(result)
    assert header_line(result) in body
    assert "Netherlands (1)" in body
    assert "Senior Python Engineer @ Acme" in body
    assert "3d ago" in body
    assert "€70k–90k" in body
    assert "test" in body  # source name
    assert "score 40" in body
    assert "sponsorship: yes — Offers relocation and a 30% ruling." in body
    assert "why: remote, keywords:python" in body
    assert "https://example.com/jobs/1" in body


def test_text_digest_when_empty():
    body = render_text(RunResult())
    assert "No new matching jobs this run." in body


def test_html_digest_groups_and_escapes():
    result = RunResult(
        matches=[
            a_match(
                title="Engineer <script>alert(1)</script>",
                location="Amsterdam",
                sponsorship="yes",
                sponsorship_reason="Sponsors & relocates",
            )
        ]
    )
    body = render_html(result)
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;" in body
    assert "Sponsors &amp; relocates" in body
    assert "<h3" in body and "Netherlands" in body


def test_html_digest_when_empty():
    assert "No new matching jobs this run." in render_html(RunResult())


def test_console_digest_marks_dry_run(result):
    dry = render_console(result, dry_run=True)
    sent = render_console(result, dry_run=False)
    assert "DRY-RUN matches (not emailed)" in dry
    assert "Sent matches" in sent
    assert header_line(result) in dry
    assert "Netherlands (1)" in dry
    assert "sponsorship: yes" in dry


def test_console_digest_when_empty():
    assert "(none)" in render_console(RunResult(), dry_run=True)


def unhealthy_result() -> RunResult:
    return RunResult(
        matches=[a_match(location="Amsterdam")],
        sources=[
            SourceHealth(name="remotive", fetched=42),
            SourceHealth(name="arbeitnow", failed=True, error="RuntimeError('boom')"),
            SourceHealth(
                name="greenhouse",
                fetched=8,
                boards_ok=["adyen", "mollie"],
                boards_failed=["databricks"],
            ),
        ],
    )


def test_source_summaries_distinguish_dead_from_quiet():
    healthy = SourceHealth(name="remotive", fetched=0)
    dead = SourceHealth(name="remotive", failed=True, error="Timeout")
    assert healthy.summary() == "remotive: 0 fetched"
    assert healthy.healthy is True
    assert "FAILED" in dead.summary()
    assert dead.healthy is False


def test_board_counts_appear_in_the_summary():
    health = SourceHealth(
        name="lever", fetched=3, boards_ok=["a", "b"], boards_failed=["c"]
    )
    assert "2/3 boards OK" in health.summary()
    assert "failed: c" in health.summary()


def test_text_digest_warns_and_lists_sources():
    body = render_text(unhealthy_result())
    assert "⚠ Source problems this run: arbeitnow, greenhouse" in body
    assert "Sources" in body
    assert "remotive: 42 fetched" in body
    assert "arbeitnow: FAILED" in body
    assert "2/3 boards OK" in body


def test_console_digest_warns_and_lists_sources():
    body = render_console(unhealthy_result(), dry_run=True)
    assert "⚠ Source problems this run" in body
    assert "arbeitnow: FAILED" in body


def test_html_digest_warns_and_lists_sources():
    body = render_html(unhealthy_result())
    assert "Source problems this run" in body
    assert "arbeitnow: FAILED" in body
    assert "<h3" in body and "Sources" in body


def test_healthy_run_shows_sources_without_a_warning():
    result = RunResult(
        matches=[a_match(location="Amsterdam")],
        sources=[SourceHealth(name="remotive", fetched=42)],
    )
    for body in (render_text(result), render_console(result, dry_run=True), render_html(result)):
        assert "Source problems" not in body
        assert "remotive: 42 fetched" in body


def test_empty_digest_still_reports_source_health():
    result = RunResult(sources=[SourceHealth(name="lever", failed=True, error="gone")])
    assert "lever: FAILED" in render_text(result)
    assert "lever: FAILED" in render_console(result, dry_run=True)


def test_digest_without_source_data_omits_the_section():
    assert "Sources" not in render_text(RunResult())


def test_save_html_creates_parent_directories(tmp_path, result):
    target = tmp_path / "nested" / "digest.html"
    written = save_html(result, target)
    assert written == target
    assert "Opportunities Abroad" in target.read_text(encoding="utf-8")


def test_save_html_overwrites_existing(tmp_path):
    target = tmp_path / "digest.html"
    target.write_text("stale", encoding="utf-8")
    save_html(RunResult(), target)
    assert "stale" not in target.read_text(encoding="utf-8")
