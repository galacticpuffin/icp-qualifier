# Feature parity: ICP Qualifier vs. the original master dashboard (:8793)

The original was inspected **read-only** (source read with cat/sed; the running page loaded with HTTP GET for screenshots).
No original file, database, service or repository was written, run, built, restarted or tested. The original source
files' modification times are unchanged (dashboard.py / master_src.html / master.html 2026-10-21, orig_template.css 2026-10-20).

| Area | Original | New | Status |
|---|---|---|---|
| Visual design | Dark glass theme, Figtree/JetBrains Mono, orange accent | Same CSS tokens and components carried over verbatim | ✅ equal |
| Header | Logo, "DIRECT · MASTER", tagline, list picker, health line, 4-part progress | Workspace monogram, "<WORKSPACE> · MASTER", tagline from profile, same picker/health/progress | ✅ (logo → monogram) |
| Research engine / Operations panels | GPU, pagescan, queues, search governor, systemd units, spend | AI provider, review queue, runs, search limiter, licensed search, usage ledger, spend | ✅ adapted |
| Pipeline cards (10) | Q, READY, REVIEW, RETRY, NO WEBSITE, PENDING, HOLD, DQ, ROUTED, SMS verified | Same 10 (core label from profile) | ✅ |
| Vertical cards | 5 fixed verticals | Segments from the profile (+ General) | ✅ configurable |
| Industry breakdown, hidden source/signal sections | ✓ | ✓ | ✅ |
| Results table | 10 columns, sort, search, 100-row paging, row expand, evidence pill | Same | ✅ |
| Filters popover | 13 groups | Same 13 (Twilio usage → target technology, shown only when configured) | ✅ |
| Row detail | Stage, outreach check, audit, quote, intel, history, evidence records | Same, plus pages checked, searches, missing evidence, signals verified/inferred | ✅+ |
| Verdict editing | Not in UI | Override priority + weak-evidence flag, recorded in history | ➕ new |
| Stages and READY rule | 10 stages; READY = A/B/C + SMS Yes + own domain + audit PASS + not weak + not vendor + dedupe | Same, driven by the profile | ✅ |
| Reconciliation | Per list, "✓ matches" | Same | ✅ |
| Final files + MANIFEST | 12 CSVs + sha256 manifest | Standard set per workspace, CSV and XLSX, manifest | ✅ |
| Export current view | CSV | CSV + XLSX using the profile's export columns | ✅+ |
| Research | Own-site crawl, link hints, sitemap, common paths, robots.txt, cache, search via governor | Same; hints, paths and queries come from the profile | ✅ |
| Evidence gate | Own-domain, smishing, content pages, templates, vendor copy, program markers | Same checks; vocabularies from the profile | ✅ |
| Dedupe / parent-subsidiary | Website-level merge, linked names, UNIT routed, franchisee/agency/subsidiary review, name conflict | Same logic | ✅ |
| Evidence audit | PASS / NEEDS REVIEW / FAIL | Same | ✅ |
| Opportunity score | Fixed MMS components | Weighted signals from the profile, explained per point | ✅ configurable |
| AI | Qwen on a rented GPU, shadow only | Claude Code / Codex CLI / API / local, shadow only, quotes verified | ✅ |
| Resumable processing | systemd workers + DB state | Leased claims, per-account checkpoints, retry, pause/resume/stop | ✅ |
| Multi-user, workspaces, ICP wizard | — | ✓ | ➕ new |

## Gaps / limitations
* Pages that render only with JavaScript (some large consumer sites) aren't executed. They come out REVIEW or RETRY, never a false qualify. A headless-browser fetcher would be the next addition.
* The original's protected hand-research rows and MMS-specific sources are deliberately not reproduced (company-specific).
* The Docker image isn't built on the Pi (no Docker here). CI builds and smoke-tests it.
* The Codex CLI token on this Pi has expired; the app reports "run `codex login`". The Claude Code CLI was tested live.
* Free search scraping can be blocked by the engine. Paid search APIs are wired in but untested live (no key, no approval).

## SaaS customer journey (2026-10-26)
Verified in a real browser by `scripts/customer_journey.py` (CI runs it): sign up → private workspace → describe business +
"Draft my ICP" (AI when connected; Claude CLI draft tested live, 15 s) → guided ICP → upload with auto column mapping → Start research →
live progress → dashboard with scores, reasons, sources, evidence audit and decision-makers → filters → CSV / Excel / decision-maker
exports → edit ICP with the guided questions → requalify without re-upload → per-workspace settings (AI, search, contacts, caps, keys, usage, team).

### Not finished / not verified
* Not deployed publicly: needs a server, domain and HTTPS (purchase/approval needed). Today it runs on the owner's Pi over Tailscale.
* "Forgot password" by e-mail isn't built (no e-mail sending). The workspace owner can set a new password for a member in Settings → Team.
* No billing / subscription plans.
* Hunter.io and Apollo.io contact lookups are implemented but untested live (no API key). Only own-website contacts are verified.
* Paid search (Serper, Brave, Tavily) and paid AI APIs are implemented but untested live (no keys).
* Sites that only render with JavaScript aren't executed, so they land in REVIEW rather than being qualified.
* Research of very large lists is limited by website crawling speed (about 5–13 s per company per worker).
