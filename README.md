# Opportunities Abroad

Open-source **personal job-alert bot** for people in India who want **tech / engineering roles abroad** — especially the **Netherlands and EU**, plus **remote-friendly international** postings.

Each run pulls current listings from **public job APIs**, matches them against your YAML/JSON preferences (keywords, countries, remote vs onsite), de-duplicates against a local SQLite store, and either **prints a dry-run digest** or **emails** one. WhatsApp and Telegram are stubbed for later.

This is a cron-friendly single-shot CLI, not a long-running daemon.

## What it is (and is not)

| This project | Not this project |
| --- | --- |
| Personal digest of links back to original postings | A new job board or aggregator site |
| Public, documented APIs (Remotive, Arbeitnow, optional Adzuna) | LinkedIn / Indeed / Naukri / Glassdoor scraping |
| Your keywords + geography | Immigration, visa, or legal advice |
| Email now; WhatsApp/Telegram later via official APIs | Unofficial WhatsApp Web automation |

## Ethics and source terms

- **No scraping of LinkedIn or other ToS-gated boards.** Adding a LinkedIn scraper will not be accepted.
- **Link back.** Digests always include the original listing URL. Remotive in particular requires linking to their job URL and crediting Remotive — we do that by passing their `url` through unchanged.
- **Do not republish feeds** onto third-party job boards. This tool is for *your* inbox (or a small group you have permission to email).
- **Be polite.** Default HTTP `User-Agent` identifies this project. Arbeitnow pagination is capped (the public API is rate-limited). Remotive asks that you not poll aggressively; a few scheduled runs per day is enough.
- **Secrets stay local.** `.env` and `prefs.yaml` are gitignored. Never commit SMTP passwords or Adzuna keys.
- **Attribution in the digest** names the source (`remotive`, `arbeitnow`, `adzuna`).

If a provider asks you to stop, stop. Their API, their rules.

## Default focus

The sample `prefs.example.yaml` is aimed at an **Indian software engineer** targeting:

- Onsite / hybrid roles in the **Netherlands, Germany, and the wider EU**
- **Remote** roles that are worldwide, Europe/EMEA, or India-friendly
- Rejection of obvious **US-only / “must be in the United States”** remote jobs
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
- `opportunities_abroad.matcher` — keywords, geo, remote vs onsite
- `opportunities_abroad.store` — SQLite seen-job keys + normalized URLs
- `opportunities_abroad.notifiers` — email, plus WhatsApp/Telegram stubs

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
| `-v` | Debug logging |

### Cron

Once a day is plenty (Remotive listings are themselves delayed). Example:

```cron
15 7 * * * cd /path/to/opportunities-abroad && .venv/bin/python -m opportunities_abroad --send --prefs prefs.yaml >> /var/log/opportunities-abroad.log 2>&1
```

`--send` fails fast with a clear message if `SMTP_HOST`, `EMAIL_FROM`, or `EMAIL_TO` are missing.

## Configuration

### Preferences (`prefs.yaml`)

See `prefs.example.yaml`. Highlights:

- `include_keywords` / `exclude_keywords` — phrase match with word boundaries (`intern` will not drop `international`)
- `locations.countries` / `cities` — onsite/hybrid geography (aliases like NL → Netherlands/Amsterdam are built in)
- `work_mode.remote` / `hybrid` / `onsite` / `remote_only`
- `remote.accept_locations` / `reject_locations` — candidate-location strings on remote jobs
- `visa_keywords` — ranking boost only
- `sources.remotive` / `arbeitnow` / `adzuna` — toggle
- `adzuna.*` — country codes and query, used only when keys are set

JSON prefs are also accepted (`--prefs prefs.json`).

### Environment (`.env`)

| Variable | Required | Purpose |
| --- | --- | --- |
| `SMTP_HOST` | `--send` | SMTP server |
| `SMTP_PORT` | no (587) | 587 + STARTTLS, or 465 implicit TLS |
| `SMTP_USER` / `SMTP_PASSWORD` | no | Auth (optional for open relays) |
| `EMAIL_FROM` / `EMAIL_TO` | `--send` | Envelope addresses (`EMAIL_TO` may be comma-separated) |
| `SMTP_STARTTLS` | no (`true`) | Set `false` with port 465 |
| `ADZUNA_APP_ID` / `ADZUNA_API_KEY` | no | If **either** is unset, Adzuna is skipped (no live calls) |
| `DATABASE_PATH` / `PREFS_PATH` | no | Overrides |

## Sources

| Source | Auth | Notes |
| --- | --- | --- |
| [Remotive](https://github.com/remotive-com/remote-jobs-api) `GET https://remotive.com/api/remote-jobs` | none | Public remote feed (size varies; 15 listings when last checked). Filtered client-side. Credit Remotive; link their URL. |
| [Arbeitnow](https://www.arbeitnow.com/blog/job-board-api) `GET https://www.arbeitnow.com/api/job-board-api` | none | Europe-heavy ATS listings. Keep `arbeitnow.max_pages` small. |
| [Adzuna](https://developer.adzuna.com/overview) `GET https://api.adzuna.com/v1/api/jobs/{country}/search/{page}` | `app_id` + `app_key` | **Skipped** unless both env vars are set. |

To add a source: implement `JobSource` in `sources/`, register it in `sources/registry.py`, add a prefs toggle, and cover the mapper with tests if the response shape is non-trivial.

## Notifiers

- **Email** — HTML + plain-text digest via stdlib `smtplib`.
- **WhatsApp** — stub (`WhatsAppNotifier`). Documented no-op; future work should use Meta Cloud API or Twilio, never WhatsApp Web scraping.
- **Telegram** — stub (`TelegramNotifier`). Documented no-op; future work should use the official Bot API.

## Tests

```bash
pytest
```

Matcher and SQLite de-dupe tests do not need the network. Live dry-runs do.

## Project layout

```
src/opportunities_abroad/
  cli.py              # argparse entry (`python -m opportunities_abroad`)
  pipeline.py         # fetch → match → dedupe → notify
  prefs.py            # YAML/JSON preferences
  models.py           # Job, Match
  sources/            # remotive, arbeitnow, adzuna
  matcher/            # keyword + geo + work-mode
  store/              # SQLite seen jobs
  notifiers/          # email + stubs
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
