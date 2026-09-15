from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from opportunities_abroad.models import Match, RunResult
from opportunities_abroad.pipeline import fetch_all, run
from opportunities_abroad.prefs import prefs_from_dict
from opportunities_abroad.sources.base import JobSource
from opportunities_abroad.store.sqlite import SqliteJobStore

from tests.conftest import make_job


class StubSource(JobSource):
    def __init__(self, name, jobs=None, boom=False):
        self.name = name
        self._jobs = jobs or []
        self._boom = boom

    def fetch(self, prefs):
        if self._boom:
            raise RuntimeError("source exploded")
        return self._jobs


class RecordingNotifier:
    name = "recording"

    def __init__(self):
        self.sent: list[RunResult] = []

    def send(self, result):
        self.sent.append(result)


class StubClassifier:
    def __init__(self):
        self.seen: list[Match] = []

    def annotate(self, matches):
        self.seen.extend(matches)
        for match in matches:
            match.sponsorship = "yes"
            match.sponsorship_reason = "stubbed"


@pytest.fixture
def prefs():
    return prefs_from_dict(
        {
            "include_keywords": ["python"],
            "title_exclude": ["junior"],
            "locations": {"countries": ["Netherlands"]},
            "max_age_days": 14,
        }
    )


@pytest.fixture
def store(tmp_path):
    with SqliteJobStore(tmp_path / "seen.db") as opened:
        yield opened


def test_fetch_all_survives_a_crashing_source(prefs):
    jobs, health = fetch_all(
        [StubSource("broken", boom=True), StubSource("ok", [make_job()])],
        prefs,
    )
    assert [j.source_id for j in jobs] == ["1"]

    broken, ok = health
    assert broken.name == "broken"
    assert broken.failed is True
    assert broken.healthy is False
    assert "source exploded" in broken.error
    assert ok.healthy is True
    assert ok.fetched == 1


def test_run_carries_source_health(prefs, store):
    result = run(
        prefs,
        [StubSource("broken", boom=True), StubSource("ok", [make_job(title="Python Engineer")])],
        store,
    )
    assert [h.name for h in result.sources] == ["broken", "ok"]
    assert [h.name for h in result.unhealthy_sources] == ["broken"]


def test_healthy_run_reports_no_problems(prefs, store):
    result = run(prefs, [StubSource("ok", [make_job(title="Python Engineer")])], store)
    assert result.unhealthy_sources == []


def test_run_reports_every_rejection_reason(prefs, store):
    jobs = [
        make_job(source_id="1", title="Python Engineer"),
        make_job(source_id="2", title="Junior Python Engineer"),
        make_job(
            source_id="3",
            title="Python Engineer",
            company="Stale Co",
            posted_at=datetime.now(timezone.utc) - timedelta(days=60),
        ),
        make_job(
            source_id="4",
            title="Python Engineer",
            company="Texan Co",
            location="Austin, Texas",
            description="Onsite python role.",
            remote=False,
        ),
    ]
    result = run(prefs, [StubSource("stub", jobs)], store)

    assert isinstance(result, RunResult)
    assert result.fetched == 4
    assert result.matched == 1
    assert result.new_count == 1
    assert result.too_old == 1
    assert result.rejected_title == 1
    assert result.rejected_location == 1
    assert result.rejected == 2


def test_already_seen_is_counted_not_resent(prefs, store):
    jobs = [
        make_job(source_id="1", title="Python Engineer", company="A", url="https://a.example/1"),
        make_job(source_id="2", title="Python Engineer", company="B", url="https://b.example/2"),
    ]
    first = run(prefs, [StubSource("stub", jobs)], store, mark_seen=True)
    assert first.new_count == 2
    assert first.already_seen == 0

    second = run(prefs, [StubSource("stub", jobs)], store, mark_seen=True)
    assert second.matches == []
    assert second.new_count == 0
    assert second.already_seen == 2


def test_dry_run_does_not_touch_the_store(prefs, store):
    run(prefs, [StubSource("stub", [make_job(title="Python Engineer")])], store)
    assert store.count() == 0


def test_send_notifies_with_the_result_and_marks_seen(prefs, store):
    notifier = RecordingNotifier()
    result = run(
        prefs,
        [StubSource("stub", [make_job(title="Python Engineer")])],
        store,
        notifier=notifier,
        send=True,
    )
    assert notifier.sent == [result]
    assert store.count() == 1


def test_send_without_matches_skips_the_notifier(prefs, store):
    notifier = RecordingNotifier()
    run(prefs, [StubSource("stub", [])], store, notifier=notifier, send=True)
    assert notifier.sent == []


def test_send_without_a_notifier_is_an_error(prefs, store):
    with pytest.raises(RuntimeError, match="requires a notifier"):
        run(prefs, [StubSource("stub", [make_job(title="Python Engineer")])], store, send=True)


def test_classifier_annotates_only_the_digest(prefs, store):
    prefs.max_jobs = 1
    jobs = [
        make_job(source_id="1", title="Senior Python Engineer", company="A", url="https://a.tld/1"),
        make_job(source_id="2", title="Python Engineer", company="B", url="https://b.tld/2"),
    ]
    classifier = StubClassifier()
    result = run(prefs, [StubSource("stub", jobs)], store, classifier=classifier)

    assert len(result.matches) == 1
    assert len(classifier.seen) == 1
    assert result.matches[0].sponsorship == "yes"
    assert result.matches[0].sponsorship_reason == "stubbed"


def make_many(count: int):
    """Jobs with distinct, descending scores so ranking is deterministic."""
    return [
        make_job(
            source_id=str(i),
            title="Senior Python Engineer",
            company=f"Co{i:02d}",
            url=f"https://co{i}.example/jobs/{i}",
            description="python backend " + ("visa sponsorship " * (count - i)),
        )
        for i in range(count)
    ]


def test_matches_beyond_the_cap_are_held_not_dropped(prefs, store):
    """The cap must not silently discard: held-back jobs surface on later runs."""
    prefs.max_jobs = 10
    jobs = make_many(30)
    seen_order = []
    for _ in range(4):
        result = run(prefs, [StubSource("stub", jobs)], store, mark_seen=True)
        seen_order.append([m.job.company for m in result.matches])

    assert [len(day) for day in seen_order] == [10, 10, 10, 0]
    # Every job is shown exactly once, best first, with nothing lost.
    shown = [company for day in seen_order for company in day]
    assert shown == [f"Co{i:02d}" for i in range(30)]


def test_backlog_is_reported(prefs, store):
    prefs.max_jobs = 10
    result = run(prefs, [StubSource("stub", make_many(30))], store)
    assert result.new_count == 10
    assert result.backlog == 20


def test_no_backlog_when_everything_fits(prefs, store):
    prefs.max_jobs = 100
    result = run(prefs, [StubSource("stub", make_many(5))], store)
    assert result.backlog == 0


def test_limit_caps_the_digest(prefs, store):
    jobs = [
        make_job(
            source_id=str(i),
            title="Python Engineer",
            company=f"Co {i}",
            url=f"https://co{i}.example/jobs/{i}",
        )
        for i in range(5)
    ]
    result = run(prefs, [StubSource("stub", jobs)], store, limit=2)
    assert result.new_count == 2
    assert result.matched == 5
