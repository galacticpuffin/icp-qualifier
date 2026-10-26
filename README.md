# ICP Qualifier

An industry-agnostic, evidence-first account research and qualification dashboard. You describe your ideal customer
in a short wizard. The answers become an editable ICP profile that directly controls what the engine crawls and
searches, which signals it verifies, what disqualifies an account, how A/B/C priority is set and what goes into the export.

**Workflow:** sign up → ICP wizard → review the generated rules → upload CSV/XLSX → map columns → research runs → watch
live progress → review accounts and evidence → edit rules → requalify (from cache, no re-download) → filter → export CSV/XLSX.

## Start (one command)

```sh
./start.sh                      # Python 3.11+, no packages needed → http://127.0.0.1:8890
```
On first run the server log prints a one-time **setup code** (also saved in `data/SETUP_CODE`). Open `/setup` and create
the admin account, or set `ICPQ_ADMIN_EMAIL` / `ICPQ_ADMIN_PASSWORD` to skip it. With Docker: `cp .env.example .env && docker compose up -d`.

Options: `ICPQ_HOST` (default 127.0.0.1), `ICPQ_PORT` (8890), `ICPQ_DATA` (./data), `ICPQ_THREADS` (4).
Ops: `python -m icpq backup`, `python -m icpq restore FILE --yes`, `python -m icpq migrate`, `python -m icpq validate-profile FILE`.

## Connect AI (optional, Settings → AI)
AI is never required. It only reviews accounts left in REVIEW, and it can suggest wizard signals. Code verifies every
quote word for word, AI output is labelled UNVERIFIED, and it never changes a verdict.
* **Claude Code CLI**: install Claude Code, run `claude` once and sign in, then pick "Claude Code CLI". Your plan's limits and terms apply.
* **OpenAI Codex CLI**: install Codex, run `codex login`, then pick "OpenAI Codex CLI".
* **API** (OpenAI-compatible or the Claude API): paste a key, set a monthly cap and tick the approval box. Paid APIs never run without it.
* Every provider has a daily call cap and **Test connection**. There is no silent fallback from a CLI to a paid API.

## Search (optional, Settings → Search)
Off by default: research then uses each company's own website only. The free DuckDuckGo HTML engine is rate-limited and
pauses itself for 30 minutes after a block. Serper, Brave and Tavily need a key, your approval and a monthly cap, and every call goes in the usage ledger.
Accounts whose needed searches can't run are shown as RETRY, never as complete.

## Evidence rules
* Only VERIFIED evidence (a quote from the company's own page that meets the profile's standard) can satisfy a mandatory signal.
* INFERRED (weaker or independent-page) and REJECTED (warning text, blog/news, vendor copy, templates) passages stay visible with their reason.
* Missing data (size, revenue, location) is never treated as a match or a mismatch.
* READY = qualified A/B/C + evidence audit PASS + own domain + not flagged + deduplicated across lists.

## Layout
`icpq/icp` profile schema, wizard and suggestion packs · `icpq/engine` fetch, search, extract, qualify, audit, AI ·
`icpq/ingest.py` mapping, dedupe and parent/subsidiary · `icpq/runner.py` resumable runs · `icpq/dashboard.py` stages and reconciliation ·
`icpq/server.py` HTTP API · `icpq/web` UI. Each workspace has its own SQLite database (`data/workspaces/<id>/ws.db`).

## Tests
`pip install pytest && pytest` (unit + full API workflow over three unrelated ICPs, offline with fixture websites) ·
`python scripts/browser_e2e.py --out shots` (real browser, screenshots; needs Playwright). CI runs both, plus lint, bandit,
a Docker build and a smoke test. Deployment is a manual job gated by the `production` environment.
