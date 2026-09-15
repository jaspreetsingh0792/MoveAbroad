# MoveAbroad

**Find jobs abroad that match your skills, target countries, work preferences, and visa needs.**

MoveAbroad is an open-source personal job-alert bot for people who want to work in another country. It pulls current listings from public job APIs and company ATS boards, filters them against your preferences, removes duplicates, and sends a focused digest by email.

> **MoveAbroad is not a job board.** It sends you links to the original job postings.

## Why MoveAbroad?

Searching for an international job is different from ordinary job searching. You care about:

- Is the role actually in a country I can move to?
- Is it remote, hybrid, or onsite?
- Does the company mention sponsorship or relocation?
- Is the posting still fresh?
- Is this really the type of role I want?
- Have I already seen this job somewhere else?

MoveAbroad is designed to answer those questions before a job reaches your inbox.

## How it works

```text
Your preferences
      ↓
Public job APIs + company job boards
      ↓
Freshness + title + seniority + keyword filters
      ↓
Location + remote eligibility + sponsorship signals
      ↓
Cross-source deduplication
      ↓
Ranked daily digest
```

Supported sources include Remotive, Arbeitnow, Greenhouse, Lever, Ashby, and optional Adzuna. No LinkedIn/Indeed/Naukri/Glassdoor scraping is used.

## First run

You do not need to understand the code to test MoveAbroad.

### 1. Clone it

```bash
git clone https://github.com/jaspreetsingh0792/moveabroad.git
cd moveabroad
```

### 2. Install it

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

### 3. Create your preferences

```bash
cp prefs.example.yaml prefs.yaml
```

Edit `prefs.yaml` for your target roles, countries, work modes, and other preferences.

### 4. Test before sending email

```bash
moveabroad --dry-run --prefs prefs.yaml
```

This fetches live listings but **does not send email and does not mark jobs as seen**.

A healthy run should give you a summary similar to:

```text
486 jobs fetched
21 matches
465 rejected

Netherlands
  Senior Security Engineer ...
  Platform Engineer ...

Germany
  Senior Software Engineer ...

Remote
  ...
```

Run the dry-run repeatedly while tuning your preferences. This is the recommended first-time user workflow.

### 5. Send the digest

Configure SMTP through `.env` and run:

```bash
moveabroad --send --prefs prefs.yaml
```

The send mode emails new matches and records them in the local SQLite database so the same jobs are not repeatedly alerted.

## GitHub Actions

The included workflow can run MoveAbroad automatically at **06:00 UTC Monday-Friday**.

Add these repository secrets:

| Secret | Required | Purpose |
| --- | --- | --- |
| `PREFS_YAML` | Yes | Your complete `prefs.yaml` |
| `SMTP_HOST` | Yes | SMTP server |
| `EMAIL_FROM` | Yes | Sender address |
| `EMAIL_TO` | Yes | Recipient address(es) |
| `SMTP_PORT` | No | Defaults to 587 |
| `SMTP_USER` / `SMTP_PASSWORD` | No | SMTP authentication |
| `SMTP_STARTTLS` | No | Defaults to true |
| `ADZUNA_APP_ID` / `ADZUNA_API_KEY` | No | Enables Adzuna |
| `ANTHROPIC_API_KEY` | No | Enables optional sponsorship classifier |

Alert history is kept in the GitHub Actions cache rather than committed to the public repository.

You can also trigger the workflow manually from the Actions tab.

## Matching

Geography is treated as a hard filter and comes from the job's explicit location field. Description text is not used to pretend an onsite job is in another country.

The matching pipeline considers:

1. Posting freshness
2. Title and role family
3. Seniority
4. Keywords
5. Sponsorship signals
6. Remote/onsite/hybrid eligibility
7. Location
8. Cross-source deduplication
9. Ranking

The sample preferences are aimed at an Indian software engineer targeting the Netherlands, Germany, wider EU, and suitable international remote roles. Edit the preferences for your own profile.

## Visa sponsorship

MoveAbroad can surface sponsorship signals from:

- Source-provided sponsorship fields
- Visa/sponsorship keywords
- Optional AI classification using the Anthropic API

Sponsorship information is a signal, not legal or immigration advice. Always verify eligibility with the employer and official government sources.

## Source health

A broken source should not silently look like an empty source. MoveAbroad reports source/ATS health in the digest and supports:

```bash
moveabroad --send --prefs prefs.yaml --fail-on-source-error
```

That lets scheduled runs go red when a source or company board fails.

## Tests

The test suite is offline and uses fixtures/HTTP mocks:

```bash
pytest
ruff check .
```

CI runs on Python 3.11 and 3.12.

## Project structure

The Python package remains named `opportunities_abroad` internally for backwards compatibility, while the public product and CLI are now **MoveAbroad**.

```text
src/opportunities_abroad/
  cli.py
  pipeline.py
  prefs.py
  models.py
  seniority.py
  matcher/
  sources/
  notifiers/
.github/workflows/
prefs.example.yaml
.env.example
tests/
```

## Privacy and source terms

- Do not commit `.env`, `prefs.yaml`, SMTP passwords, API keys, or database files.
- Do not add scrapers for sites that prohibit scraping.
- Link users back to the original job posting.
- Respect each provider's API terms and rate limits.
- This project is for personal job discovery, not republishing job feeds as a third-party job board.

## Contributing

1. Fork the repository and branch from `main`.
2. Use documented/public APIs where possible.
3. Add tests for matcher, source, or persistence changes.
4. Run `pytest` and `ruff check .` before opening a PR.
5. Include a dry-run example when changing a source or matching rule.

## License

MIT © 2026 Jaspreet Singh

Job listings remain the property of their original posters and source boards. MoveAbroad only helps you discover them.
