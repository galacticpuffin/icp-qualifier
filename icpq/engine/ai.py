"""Interchangeable AI providers for research assistance. AI never decides a verdict.

Providers (Settings -> AI):
  off          default
  claude-cli   the Claude Code CLI signed in on this computer (`claude`): uses that subscription, no API key. Each call is
               isolated: no tools, no session persistence, no MCP, no project settings, JSON-schema output.
  codex-cli    the OpenAI Codex CLI signed in on this computer (`codex login`): read-only sandbox, ephemeral, schema output.
  openai       any OpenAI-compatible /v1/chat/completions endpoint (hosted or local: vLLM, llama.cpp, Ollama); a key if needed
  anthropic    the Claude API (Messages) with an API key
  mock         deterministic offline answers for tests (ICPQ_AI_MOCK=<json file> or built-in: never applies)
Limits: `daily_call_cap` for every provider; paid HTTP APIs also need `approved: true` and `monthly_cap_usd` (each call is
charged `usd_per_call` in the usage ledger before it runs). Subscription CLIs are subject to their plan's own usage limits and
terms; the cap here keeps a run from exhausting them. There is never a silent fallback from a CLI to a paid API.

What AI does: (1) shadow review of accounts in REVIEW: it reads cached passages from the company's own pages and may propose
a quote showing a mandatory signal; CODE keeps the proposal only if the quote is found word for word in the passage, and it
is shown as an UNVERIFIED candidate (STRONG when the quote carries the signal's proof marker). (2) Wizard help: suggest
signal phrases from a free-text description (the user reviews every suggestion)."""
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

from ..util import norm_text, now

SYSTEM = "You check B2B sales-qualification evidence. Use no tools. Reply only with the JSON object the schema asks for."


class AIUnavailable(Exception):
    pass


def settings(app):
    from ..db import get_setting
    s = json.loads(get_setting(app, "ai", "{}") or "{}")
    s.setdefault("provider", "off")
    s.setdefault("model", "")
    s.setdefault("effort", "low")
    s.setdefault("url", "")
    s.setdefault("approved", False)
    s.setdefault("daily_call_cap", 200)
    s.setdefault("monthly_cap_usd", 0)
    s.setdefault("usd_per_call", 0.01)
    s.setdefault("timeout", 180)
    return s


def _strict(schema):
    s = {k: v for k, v in schema.items() if k not in ("maxLength", "minItems", "maxItems")}
    if s.get("type") == "object":
        s["additionalProperties"] = False
        s["properties"] = {k: _strict(v) for k, v in s.get("properties", {}).items()}
        s["required"] = list(s["properties"])
    if s.get("type") == "array" and "items" in s:
        s["items"] = _strict(s["items"])
    return s


def _parse(txt):
    txt = re.sub(r"(?s)<think>.*?</think>", "", txt or "").strip()
    txt = re.sub(r"(?s)^```(?:json)?\s*(.*?)\s*```$", r"\1", txt)
    return json.loads(txt)


class Client:
    def __init__(self, s):
        self.s, self.kind = s, s["provider"]
        self.label = f"{s.get('model') or 'default'}@{self.kind}"

    # ---------------------------------------------------------------- transports
    def _cli(self, prompt, schema):
        name = "claude" if self.kind == "claude-cli" else "codex"
        exe = os.environ.get("ICPQ_AI_CLI") or shutil.which(name)
        if not exe:
            raise AIUnavailable(f"the {name} CLI is not installed on this computer")
        with tempfile.TemporaryDirectory(prefix="icpq-ai-") as d:       # empty working dir: no project files or instructions
            tmp = Path(d)
            if self.kind == "claude-cli":
                cmd = [exe, "-p", "--output-format", "json", "--json-schema", json.dumps(schema), "--tools", "", "--no-session-persistence",
                       "--setting-sources", "", "--strict-mcp-config", "--disable-slash-commands", "--system-prompt", SYSTEM,
                       "--effort", self.s.get("effort") or "low"]
                text = prompt
            else:
                (tmp / "schema.json").write_text(json.dumps(_strict(schema)))
                cmd = [exe, "exec", "--ephemeral", "--skip-git-repo-check", "--ignore-user-config", "--sandbox", "read-only",
                       "-c", f'model_reasoning_effort="{self.s.get("effort") or "low"}"', "--output-schema", str(tmp / "schema.json"),
                       "-o", str(tmp / "out.json"), "-"]
                text = SYSTEM + "\n\n" + prompt
            if self.s.get("model"):
                cmd += ["--model", self.s["model"]]
            p = subprocess.run(cmd, input=text, capture_output=True, text=True, cwd=d, timeout=float(self.s.get("timeout") or 180))  # nosec B603
            if self.kind == "claude-cli":
                try:
                    out = json.loads(p.stdout)
                except json.JSONDecodeError:
                    raise AIUnavailable(f"claude CLI failed: {(p.stderr or p.stdout).strip()[-240:] or 'no output'}")
                if out.get("is_error"):
                    msg = str(out.get("result"))[:240]
                    if "login" in msg.lower() or "auth" in msg.lower():
                        raise AIUnavailable("claude CLI is not signed in: run `claude` once in a terminal and sign in")
                    raise AIUnavailable("claude CLI: " + msg)
                return out["structured_output"] if out.get("structured_output") is not None else _parse(out.get("result") or "")
            f = tmp / "out.json"
            if p.returncode or not f.is_file():
                err = (p.stderr or p.stdout).strip()
                if "sign in" in err.lower() or "401" in err or "not logged in" in err.lower():
                    raise AIUnavailable("codex CLI is not signed in: run `codex login` in a terminal")
                raise AIUnavailable(f"codex CLI failed: {err[-240:] or 'no output'}")
            return json.loads(f.read_text())

    def _http(self, prompt, schema):
        from ..secrets import get_secret
        key = get_secret("ai_" + self.kind)
        if self.kind == "anthropic":
            if not key:
                raise AIUnavailable("no Claude API key saved")
            body = {"model": self.s.get("model") or "claude-sonnet-5-5", "max_tokens": 1500, "system": SYSTEM,
                    "messages": [{"role": "user", "content": prompt + "\n\nReturn only JSON matching: " + json.dumps(schema)}]}
            req = urllib.request.Request((self.s.get("url") or "https://api.anthropic.com").rstrip("/") + "/v1/messages", data=json.dumps(body).encode(),
                                         headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
            d = json.loads(urllib.request.urlopen(req, timeout=float(self.s.get("timeout") or 180)).read())     # nosec B310
            return _parse("".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text"))
        url = (self.s.get("url") or "https://api.openai.com").rstrip("/")
        body = {"model": self.s.get("model") or "gpt-5-mini", "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
                "response_format": {"type": "json_schema", "json_schema": {"name": "out", "schema": _strict(schema), "strict": True}}}
        req = urllib.request.Request(url + "/v1/chat/completions", data=json.dumps(body).encode(),
                                     headers={"content-type": "application/json", **({"authorization": f"Bearer {key}"} if key else {})})
        d = json.loads(urllib.request.urlopen(req, timeout=float(self.s.get("timeout") or 180)).read())         # nosec B310
        return _parse(d["choices"][0]["message"]["content"])

    def _mock(self, prompt, schema):
        path = os.environ.get("ICPQ_AI_MOCK")
        data = json.load(open(path)) if path else {}
        for k, v in data.items():
            if k in prompt:
                return v
        props = schema.get("properties", {})
        if "applies" in props:
            return {"applies": False, "quotes": [], "reason": "mock: no answer recorded"}
        if "ok" in props:
            return {"ok": True, "reply": "mock provider healthy"}
        return {"signals": []}

    def paid(self):
        """Hosted HTTP APIs are treated as paid; a local OpenAI-compatible server (localhost / private network) is not."""
        if self.kind == "anthropic":
            return True
        if self.kind != "openai":
            return False
        import urllib.parse
        h = urllib.parse.urlparse(self.s.get("url") or "https://api.openai.com").hostname or ""
        return not (h in ("localhost", "127.0.0.1", "::1") or re.match(r"^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|100\.)", h))

    # ---------------------------------------------------------------- public
    def ask(self, app, prompt, schema, workspace_id=None, retries=2):
        if self.kind == "off":
            raise AIUnavailable("AI is off (Settings → AI)")
        day = now()[:10]
        n = app.execute("SELECT count(*) FROM usage WHERE kind='ai' AND provider=? AND substr(at,1,10)=?", (self.kind, day)).fetchone()[0]
        if n >= int(self.s.get("daily_call_cap") or 0):
            raise AIUnavailable(f"daily AI call cap reached ({self.s.get('daily_call_cap')})")
        cost = 0.0
        if self.paid():
            if not self.s.get("approved"):
                raise AIUnavailable(f"{self.kind} is a paid API: approve it with a monthly cap in Settings first")
            cost = float(self.s.get("usd_per_call") or 0)
            m = app.execute("SELECT COALESCE(sum(usd),0) FROM usage WHERE kind='ai' AND provider=? AND substr(at,1,7)=?", (self.kind, day[:7])).fetchone()[0]
            if m + cost > float(self.s.get("monthly_cap_usd") or 0):
                raise AIUnavailable(f"{self.kind} monthly cap ${self.s.get('monthly_cap_usd')} reached")
        with app:
            cur = app.execute("INSERT INTO usage(at,provider,kind,workspace_id,units,usd,ok,note) VALUES(?,?,?,?,?,?,?,?)",
                              (now(), self.kind, "ai", workspace_id, 1, cost, 0, "started"))
        t = time.time()
        err = None
        for i in range(retries + 1):
            try:
                fn = self._cli if self.kind.endswith("-cli") else self._mock if self.kind == "mock" else self._http
                out = fn(prompt, schema)
                with app:
                    app.execute("UPDATE usage SET ok=1, note=? WHERE id=?", (f"{time.time() - t:.1f}s", cur.lastrowid))
                return out if isinstance(out, dict) else {"_raw": out}
            except AIUnavailable as e:
                err = e
                if "not signed in" in str(e) or "not installed" in str(e) or "cap" in str(e):
                    break
            except (subprocess.TimeoutExpired, OSError, ValueError, KeyError) as e:
                err = AIUnavailable(f"{type(e).__name__}: {str(e)[:200]}")
            time.sleep(min(2 ** i * 2, 20))
        with app:
            app.execute("UPDATE usage SET ok=0, note=? WHERE id=?", (str(err)[:200], cur.lastrowid))
        raise err

    def health(self, app):
        """A tiny real call (counts toward the caps). -> (ok, message, seconds)"""
        t = time.time()
        try:
            out = self.ask(app, "Health check. Reply with ok=true and reply='ready'.", {"type": "object", "properties": {"ok": {"type": "boolean"}, "reply": {"type": "string"}}, "required": ["ok", "reply"]})
            return bool(out.get("ok")), f"{self.label} answered: {str(out.get('reply'))[:60]}", round(time.time() - t, 1)
        except AIUnavailable as e:
            return False, str(e), round(time.time() - t, 1)


def client(app):
    return Client(settings(app))


RULE_SCHEMA = {"type": "object", "properties": {"applies": {"type": "boolean"}, "quotes": {"type": "array", "items": {"type": "string"}},
                                                "reason": {"type": "string"}}, "required": ["applies", "quotes", "reason"]}
RULE_PROMPT = """Organisation: {name} (website {domain}).
Question: do these excerpts from the organisation's own website show that this is true of {name} ITSELF?
Signal: {label}. {description}

Excerpts:
{snippets}

Rules: applies=true only if an excerpt EXPLICITLY shows it. False for other organisations, customers, vendors' marketing copy,
generic mentions, hypotheticals or guesses. quotes: copy 1-3 short sentences EXACTLY from the excerpts. reason: one sentence."""


def shadow_review(cl, app, icp, acct, pages, workspace_id=None):
    """-> ai dict for the verdict, or None. Proposals are UNVERIFIED and never change a verdict."""
    words = sorted({w for s in icp.mandatory for p in s["patterns"] + [s["label"]] for w in re.findall(r"[a-z]{5,}", p.lower())})[:12]
    if not words or not pages:
        return None
    rx = re.compile("|".join(map(re.escape, words)), re.IGNORECASE)
    snips = []
    for p in pages:
        t = p.get("text") or ""
        for m in rx.finditer(t):
            snips.append({"url": p.get("final_url") or p["url"], "text": re.sub(r"\s+", " ", t[max(0, m.start() - 220):m.end() + 220])})
            if len(snips) >= 8:
                break
        if len(snips) >= 8:
            break
    if not snips:
        return None
    best = None
    for s in icp.mandatory[:3]:
        prompt = RULE_PROMPT.format(name=acct["name"], domain=acct.get("domain") or "", label=s["label"], description=s.get("description") or "",
                                    snippets="\n".join(f"[{i + 1}] ({x['url']}) {x['text']}" for i, x in enumerate(snips)))
        out = cl.ask(app, prompt, RULE_SCHEMA, workspace_id)
        if not out.get("applies"):
            continue
        for q in out.get("quotes") or []:
            nq = norm_text(q).strip(" .\"'")
            src = next((x for x in snips if len(nq) >= 15 and nq in norm_text(x["text"])), None)
            if src:
                strength = "STRONG" if (s["_mk"] and s["_mk"].search(q)) or (s["_rx"] and s["_rx"].search(q)) else "WEAK"
                cand = {"quote": q[:400], "url": src["url"], "signal": s["label"], "strength": strength, "model": cl.label, "at": now(),
                        "reason": str(out.get("reason"))[:240]}
                if best is None or (strength == "STRONG" and best["strength"] != "STRONG"):
                    best = cand
                break
    return best


SUGGEST_SCHEMA = {"type": "object", "properties": {"signals": {"type": "array", "items": {"type": "object", "properties": {
    "label": {"type": "string"}, "category": {"type": "string"}, "patterns": {"type": "array", "items": {"type": "string"}},
    "requirement": {"type": "string"}}, "required": ["label", "category", "patterns", "requirement"]}}}, "required": ["signals"]}


def suggest_signals(cl, app, answers):
    prompt = (f"A company sells: {answers.get('sells')}. Market: {answers.get('market_text') or answers.get('pack')}. Ideal customer: {answers.get('ideal')}.\n"
              "Suggest up to 6 signals a researcher could verify on a PROSPECT's own public website that show the prospect needs this. "
              "For each: label, category (one of product, technology, competitor, problem, buying, behavioral, operational, financial, organizational, compliance), "
              "patterns = 2-5 short literal phrases that would appear on such a website, requirement = mandatory or preferred.")
    out = cl.ask(app, prompt, SUGGEST_SCHEMA)
    sigs = []
    for s in (out.get("signals") or [])[:6]:
        pats = [p for p in s.get("patterns") or [] if isinstance(p, str) and 2 < len(p) < 60 and not p.lower().startswith("re:")][:5]
        if pats and s.get("label"):
            sigs.append({"label": str(s["label"])[:60], "category": s.get("category") if s.get("category") in
                         ("product", "technology", "competitor", "problem", "buying", "behavioral", "operational", "financial", "organizational", "compliance") else "other",
                         "patterns": pats, "requirement": "mandatory" if s.get("requirement") == "mandatory" else "preferred", "weight": 10,
                         "ai_suggested": True})
    return sigs
