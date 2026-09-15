# Opportunities Abroad

Open-source **personal job-alert bot** for people in India who want **tech / engineering roles abroad** — especially the **Netherlands and EU**, plus **remote-friendly international** postings.

Each run pulls current listings from **public job APIs** — aggregators plus the **Greenhouse / Lever / Ashby boards of companies you name** — matches them against your YAML/JSON preferences (keywords, titles, countries, remote vs onsite, posting age), de-duplicates against a local SQLite store, and either **prints a dry-run digest** or **emails** one, grouped by country. WhatsApp and Telegram are stubbed for later.

This is a cron-friendly single-shot CLI, not a long-running daemon.

## What it is (and is not)

| This project | Not this project |
| --- | --- |
| Personal digest of links back to original postings | A new job board or aggregator site |
| Public, documented APIs (Remotive, Arbeitnow, Greenhouse, Lever, Ashby, optional Adzuna) | LinkedIn / Indeed / Naukri / Glassdoor scraping |
| Your keywords + geography | Immigration, visa, or legal advice |
| Email now; WhatsApp/Telegram later via official APIs | Unofficial WhatsApp Web automation |

## Ethics and source terms

- **No scraping of LinkedIn or other ToS-gated boards.** Adding a LinkedIn scraper will not be accepted.
- **Link back.** Digests always include the original listing URL. Remotive in particular requires linking to their job URL and crediting Remotive — we do that by passing their `url` through unchanged.
- **Do not republish feeds** onto third-party job boards. This tool is for *your* inbox (or a small group you have permission to email).
- **Be polite.** Default HTTP `User-Agent` identifies this project and every call shares one configurable timeout. Arbeitnow pagination is capped (the public API is rate-limited). Company boards are fetched one request per slug, spaced out, so a long `ats_boards` list does not burst. Remotive asks that you not poll aggressively; a few scheduled runs per day is enough.
- **Secrets stay local.** `.env`, `prefs.yaml` and database files are gitignored. Never commit SMTP passwords, Adzuna keys, or an Anthropic key. In CI they belong in repository secrets.
- **Attribution in the digest** names the source (`remotive`, `arbeitnow`, `adzuna`, `greenhouse`, `lever`, `ashby`).

If a provider asks you to stop, stop. Their API, their rules.

## Default focus

The sample `prefs.example.yaml` is aimed at an **Indian software engineer** targeting:

- Onsite / hybrid roles in the **Netherlands, Germany, and the wider EU**
- **Remote** roles that are worldwide, Europe/EMEA, or India-friendly
- Rejection of obvious **US-only / “must be in the United States”** remote jobs
- Rejection of **junior / working student / trainee / intern** titles
- Postings from the **last 14 days**, when the source dates them
- A soft ranking boost when the text mentions **visa, sponsorship, relocation, Blue Card, kennismigrant**

Edit the prefs; the matcher is generic.

## Architecture

```
prefs.yaml  +  public APIs
        \        /
         pipeline
        /    |    \
  matcher  store  notifiers
           (SQLite)  email (live)
                     whatsapp / telegram (stubs)
```

Pluggable packages:

- `opportunities_abroad.sources` — `JobSource.fetch(prefs) -> list[Job]`
- `opportunities_abroad.matcher` — keywords, titles, geo, remote vs onsite, age
- `opportunities_abroad.store` — SQLite seen-job keys, normalized URLs, cross-source fingerprints
- `opportunities_abroad.digest` — country grouping and rendering, shared by email and the CLI
- `opportunities_abroad.classifier` — optional visa-sponsorship verdicts
- `opportunities_abroad.notifiers` — email, plus WhatsApp/Telegram stubs

A run returns a `RunResult` carrying the digest plus the counts behind every
drop (already seen, too old, rejected), which is what the header line reports.

### De-duplication

A job is considered already seen when **any** of these match a stored row: its
`source:id` key, its normalized URL, or a fingerprint of normalized company and
title scoped by URL host. The fingerprint is what stops the same role alerting
twice when it appears both on a company's own board and through an aggregator.
Postings with no company or title simply have no fingerprint rather than
colliding with each other.

## Requirements

- Python **3.11+**
- Network access for live API calls
- For `--send`: an SMTP account (`SMTP_HOST`, `EMAIL_FROM`, `EMAIL_TO`, …)

## Setup

```bash
git clone https://github.com/jaspreetsingh0792/opportunities-abroad.git
cd opportunities-abroad

python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install -e ".[dev]"
# or: pip install -r requirements-dev.txt && pip install -e .

cp prefs.example.yaml prefs.yaml   # then edit
cp .env.example .env               # then edit if you will --send
```

## Run

Dry-run (default): fetch live APIs, match, **print**, do **not** email, do **not** write the seen-job DB.

```bash
python -m opportunities_abroad
# or
python -m opportunities_abroad --dry-run --prefs prefs.example.yaml
# or after install:
opportunities-abroad --dry-run
```

Send mode (cron): email **new** matches and mark them seen.

```bash
python -m opportunities_abroad --send --prefs prefs.yaml
```

Useful flags:

| Flag | Meaning |
| --- | --- |
| `--prefs PATH` | YAML or JSON prefs (default: `prefs.yaml`, then `prefs.example.yaml`) |
| `--db PATH` | SQLite file (default: `data/seen_jobs.db`) |
| `--send` | SMTP digest + mark seen |
| `--dry-run` | Print only (default) |
| `--mark-seen` | Dry-run but still record matches so the next run skips them |
| `--limit N` | Cap the digest |
| `--save-html PATH` | Write the rendered HTML digest to `PATH` on every run, dry-run included (same as `digest.save_html_to`) |
| `-v` | Debug logging |

Every run opens with a line accounting for the whole batch:

```
1 new · 6 already seen · 4 too old · 6 rejected (US-only / title / visa)
```

Matches are then grouped by country (with a `Remote` bucket for location-less
remote roles and `Other` as a fallback), highest score first, each entry
showing how old the posting is, its salary when published, the source, the
sponsorship verdict when the classifier ran, and why it matched.

### Scheduling

#### GitHub Actions (recommended)

`.github/workflows/digest.yml` runs `--send` at 06:00 UTC Monday–Friday and can
also be triggered by hand from the Actions tab. After each run it commits
`data/seen_jobs.db` back to the repository so the next run knows what has
already been alerted; if nothing changed it skips the commit.

Add these repository secrets (Settings → Secrets and variables → Actions):

| Secret | Required | Purpose |
| --- | --- | --- |
| `PREFS_YAML` | yes | The whole contents of your `prefs.yaml` (see below) |
| `SMTP_HOST`, `EMAIL_FROM`, `EMAIL_TO` | yes | Delivery |
| `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_STARTTLS` | no | SMTP details |
| `ADZUNA_APP_ID`, `ADZUNA_API_KEY` | no | Enables the Adzuna source |
| `ANTHROPIC_API_KEY` | no | Enables the visa classifier |

Your preferences stay out of the repository by living in a secret. Store the
file verbatim:

```bash
gh secret set PREFS_YAML < prefs.yaml
```

The workflow writes it back to disk before the run and fails loudly if the
secret is missing:

```yaml
- name: Write prefs.yaml from the PREFS_YAML secret
  env:
    PREFS_YAML: ${{ secrets.PREFS_YAML }}
  run: printf '%s\n' "$PREFS_YAML" > prefs.yaml
```

Because the run commits to the default branch, the workflow needs
`permissions: contents: write`, which it declares.

#### Cron

Once a day is plenty (Remotive listings are themselves delayed). Example:

```cron
15 7 * * * cd /path/to/opportunities-abroad && .venv/bin/python -m opportunities_abroad --send --prefs prefs.yaml >> /var/log/opportunities-abroad.log 2>&1
```

`--send` fails fast with a clear message if `SMTP_HOST`, `EMAIL_FROM`, or `EMAIL_TO` are missing.

## Configuration

### Preferences (`prefs.yaml`)

See `prefs.example.yaml`. Highlights:

- `include_keywords` / `exclude_keywords` — phrase match with word boundaries (`intern` will not drop `international`)
- `title_include` / `title_exclude` — the same matching, against the title only. The sample excludes junior, working student, trainee and intern titles
- `max_age_days` — drop postings older than this when the source publishes a date (default `14`, `0` disables)
- `locations.countries` / `cities` — onsite/hybrid geography (aliases like NL → Netherlands/Amsterdam are built in)
- `work_mode.remote` / `hybrid` / `onsite` / `remote_only`
- `remote.accept_locations` / `reject_locations` — candidate-location strings on remote jobs
- `visa_keywords` — ranking boost only
- `visa.require` / `visa.classifier` — see [Visa sponsorship](#visa-sponsorship)
- `score_weights` — `title_hit` (8), `keyword_hit` (3), `remote` (4), `visa_hit` (5). Override individually; anything you omit keeps its default
- `location_weights` — country or city → bonus, matched against the job's location. Country names expand through the same aliases. Only the best single match applies, so a city bonus never stacks on its country's. Supplying this map replaces the defaults (`Netherlands: 6`, `Germany: 3`, `Europe: 3`) rather than merging, so you can drop entries
- `digest.max_jobs` / `digest.save_html_to`
- `sources.*` — toggle any source by name
- `ats_boards.greenhouse` / `lever` / `ashby` — company board slugs to fetch
- `adzuna.*` — country codes and query, used only when keys are set

JSON prefs are also accepted (`--prefs prefs.json`).

### Visa sponsorship

Sponsorship is usually the deciding factor when relocating, so it is tracked
three ways:

1. **Source flag.** Arbeitnow publishes a sponsorship field; it is carried on
   the job and shown as `visa:source-flagged`.
2. **Keywords.** `visa_keywords` still add to the score.
3. **Classifier (optional).** With `visa.classifier: true` and
   `ANTHROPIC_API_KEY` set, each matched posting's title and first ~2500
   characters of description go to the Anthropic Messages API, which returns
   `{"sponsorship": "yes"|"no"|"unclear", "reason": "..."}`. The verdict and
   reason appear in the digest.

Set `visa.require: true` to keep only jobs that either carry the source flag or
hit a visa keyword.

The classifier is off by default and costs money when on. Verdicts are cached
in SQLite by job key, so a rerun never pays for the same posting twice, and any
API error is recorded as `unclear` without being cached. The model is
`claude-sonnet-4-6` (override with `visa.classifier_model`), called over plain
`httpx` — no extra dependency.

### Environment (`.env`)

| Variable | Required | Purpose |
| --- | --- | --- |
| `SMTP_HOST` | `--send` | SMTP server |
| `SMTP_PORT` | no (587) | 587 + STARTTLS, or 465 implicit TLS |
| `SMTP_USER` / `SMTP_PASSWORD` | no | Auth (optional for open relays) |
| `EMAIL_FROM` / `EMAIL_TO` | `--send` | Envelope addresses (`EMAIL_TO` may be comma-separated) |
| `SMTP_STARTTLS` | no (`true`) | Set `false` with port 465 |
| `ADZUNA_APP_ID` / `ADZUNA_API_KEY` | no | If **either** is unset, Adzuna is skipped (no live calls) |
| `ANTHROPIC_API_KEY` | no | Required only when `visa.classifier` is true; otherwise the classifier is skipped |
| `DATABASE_PATH` / `PREFS_PATH` | no | Overrides |

## Sources

| Source | Auth | Notes |
| --- | --- | --- |
| [Remotive](https://github.com/remotive-com/remote-jobs-api) `GET https://remotive.com/api/remote-jobs` | none | Public remote feed (size varies; 15 listings when last checked). Filtered client-side. Credit Remotive; link their URL. |
| [Arbeitnow](https://www.arbeitnow.com/blog/job-board-api) `GET https://www.arbeitnow.com/api/job-board-api` | none | Europe-heavy ATS listings, including a sponsorship flag. Keep `arbeitnow.max_pages` small. |
| Greenhouse `GET https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true` | none | One company board per slug in `ats_boards.greenhouse`. |
| Lever `GET https://api.lever.co/v0/postings/{company}?mode=json` | none | One company board per slug in `ats_boards.lever`. |
| Ashby `GET https://api.ashbyhq.com/posting-api/job-board/{org}` | none | One company board per slug in `ats_boards.ashby`. |
| [Adzuna](https://developer.adzuna.com/overview) `GET https://api.adzuna.com/v1/api/jobs/{country}/search/{page}` | `app_id` + `app_key` | **Skipped** unless both env vars are set. |

### Company job boards (Greenhouse / Lever / Ashby)

Aggregators miss roles that a company only posts on its own board. All three
of these applicant-tracking systems publish a documented, key-free JSON
endpoint per company, so list the boards you care about:

```yaml
ats_boards:
  greenhouse: [adyen, mollie]
  lever: [wetransfer]
  ashby: [framer]
```

A slug is the company segment of the public board URL —
`https://boards.greenhouse.io/SLUG`, `https://jobs.lever.co/SLUG`,
`https://jobs.ashbyhq.com/SLUG`. The slugs shipped in `prefs.example.yaml` are
a starting point; open each board URL to confirm one before relying on it. An
unknown or failing slug is logged and skipped — it never sinks the run. Nothing
is fetched for an ATS with no slugs listed.

To add a source: implement `JobSource` in `sources/`, register it in `sources/registry.py`, add a prefs toggle, and cover the mapper with tests if the response shape is non-trivial.

## Notifiers

- **Email** — HTML + plain-text digest via stdlib `smtplib`.
- **WhatsApp** — stub (`WhatsAppNotifier`). Documented no-op; future work should use Meta Cloud API or Twilio, never WhatsApp Web scraping.
- **Telegram** — stub (`TelegramNotifier`). Documented no-op; future work should use the official Bot API.

## Tests

```bash
pytest
ruff check .
```

The whole suite runs offline: source mappers are driven by fixture payloads
through `httpx.MockTransport`, and matcher, digest and SQLite tests need no
network at all. Only live dry-runs do. CI runs both commands on Python 3.11
and 3.12.

## Project layout

```
src/opportunities_abroad/
  cli.py              # argparse entry (`python -m opportunities_abroad`)
  pipeline.py         # fetch → match → dedupe → classify → notify
  prefs.py            # YAML/JSON preferences
  models.py           # Job, Match, RunResult
  digest.py           # grouping + text/HTML/console rendering
  classifier.py       # optional visa-sponsorship verdicts
  sources/            # remotive, arbeitnow, adzuna, greenhouse, lever, ashby
  matcher/            # keyword + title + geo + work-mode + age
  store/              # SQLite seen jobs (key, URL, fingerprint) + verdict cache
  notifiers/          # email + stubs
.github/workflows/    # ci.yml (ruff + pytest), digest.yml (scheduled send)
prefs.example.yaml
.env.example
tests/
```

## Contributing

1. Fork and branch from `main`.
2. Keep sources limited to **public APIs with published terms**. No scrapers for LinkedIn or sites that forbid it.
3. Add or extend tests (`pytest`) for matcher/store behaviour.
4. Do not commit `.env`, `prefs.yaml`, or database files.
5. Open a PR with a short rationale and a dry-run snippet if you changed a source.

Ideas that fit: more official APIs, better ranking, HTML-to-text cleanup, an official Telegram/WhatsApp notifier, per-source max-age filters.

## License

[MIT](LICENSE) © 2026 Jaspreet Singh

Job listings remain the property of their original posters and source boards. This software only helps you notice them.
