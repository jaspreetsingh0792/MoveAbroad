from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from opportunities_abroad import __version__
from opportunities_abroad.notifiers.email import EmailConfigError, EmailNotifier
from opportunities_abroad.pipeline import run
from opportunities_abroad.prefs import load_prefs
from opportunities_abroad.sources.registry import build_sources
from opportunities_abroad.store.sqlite import SqliteJobStore

DEFAULT_PREFS_CANDIDATES = ("prefs.yaml", "prefs.json", "prefs.example.yaml")


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    prefs_path = _resolve_prefs(args.prefs)
    db_path = args.db or os.environ.get("DATABASE_PATH") or "data/seen_jobs.db"

    try:
        prefs = load_prefs(prefs_path)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    notifier = EmailNotifier()
    if args.send:
        try:
            notifier.require_configured()
        except EmailConfigError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    sources = build_sources(prefs)
    if not sources:
        print("No sources enabled in prefs.", file=sys.stderr)
        return 2

    with SqliteJobStore(db_path) as store:
        matches = run(
            prefs,
            sources,
            store,
            notifier=notifier if args.send else None,
            send=args.send,
            mark_seen=args.mark_seen,
            limit=args.limit,
        )

    _print_digest(matches, dry_run=not args.send)
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="opportunities-abroad",
        description=(
            "Fetch public job APIs, match against your prefs, and print or email a digest. "
            "Default is dry-run (no email, no DB writes)."
        ),
    )
    parser.add_argument("--prefs", help="Path to YAML/JSON preferences (default: prefs.yaml)")
    parser.add_argument("--db", help="SQLite path for seen jobs (default: data/seen_jobs.db)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print matches only (default). Does not send email.",
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="Email the digest of new matches and mark them seen. For cron.",
    )
    parser.add_argument(
        "--mark-seen",
        action="store_true",
        help="In dry-run, still record matches in the seen-job store.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Cap printed/sent matches")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser.parse_args(argv)


def _resolve_prefs(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    env_path = os.environ.get("PREFS_PATH")
    if env_path:
        return Path(env_path)
    for name in DEFAULT_PREFS_CANDIDATES:
        candidate = Path(name)
        if candidate.exists():
            return candidate
    # Fall back to the example shipped with the repo, even if cwd differs.
    here = Path(__file__).resolve().parents[2] / "prefs.example.yaml"
    return here


def _print_digest(matches: list, *, dry_run: bool) -> None:
    header = "DRY-RUN matches (not emailed)" if dry_run else "Sent matches"
    print(f"\n{header}: {len(matches)}")
    if not matches:
        print("  (none)")
        return
    for match in matches:
        job = match.job
        loc = job.location or "n/a"
        print(f"- [{job.source}] {job.title} @ {job.company}")
        print(f"    {loc}  score={match.score}  {', '.join(match.reasons)}")
        print(f"    {job.url}")


if __name__ == "__main__":
    raise SystemExit(main())
