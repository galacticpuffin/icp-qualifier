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
