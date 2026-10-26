/* Provider settings (admin): AI and search providers, caps and approvals, credentials, usage ledger, team. */
const HELP = {"claude-cli": "Uses the Claude Code CLI already signed in on this computer (run `claude` once in a terminal to sign in). Calls are isolated: no tools, no files, no saved sessions. Your plan's usage limits and terms apply; the daily cap keeps a run within them.",
  "codex-cli": "Uses the OpenAI Codex CLI signed in on this computer (run `codex login` once). Read-only sandbox, ephemeral sessions. Your ChatGPT plan's limits and terms apply.",
  "openai": "Any OpenAI-compatible endpoint. Hosted endpoints are treated as paid and need approval + a monthly cap; a local server (localhost or private network) does not.",
  "anthropic": "The Claude API with your API key. Paid: needs approval and a monthly cap.", "mock": "Offline test answers; never qualifies anything.", "off": "Rules only. Everything still works; AI review and AI wizard suggestions are off."};
async function load(){
  const s = await api("/api/settings"); const a = s.ai, q = s.search, c = s.contacts;
  document.querySelectorAll('#aiP option[value$="-cli"]').forEach(o => { if (!s.cli_allowed) o.remove(); });
  $("cP").value = c.provider; $("cCap").value = c.monthly_cap_usd; $("cPer").value = c.usd_per_lookup; $("cN").value = c.per_company; $("cOk").checked = !!c.approved;
  $("cKey").placeholder = s.secrets["contacts_" + c.provider] ? "saved: " + s.secrets["contacts_" + c.provider] : (c.provider === "site" ? "not needed" : "paste a key to save it");
  const M = (await api("/api/workspaces/members")).members;
  $("members").innerHTML = M.map(m => `<li>${esc(m.name || m.email)} <span class="m">${esc(m.email)} · ${esc(m.role)}</span>${s.is_admin && m.email !== ME.email ? ` <button class="link" type="button" data-reset="${m.id}">Set new password</button>` : ""}</li>`).join("");
  document.querySelectorAll("[data-reset]").forEach(b => b.onclick = () => { const li = b.parentElement; if (li.querySelector("input")) return;
    li.insertAdjacentHTML("beforeend", `<div class="row" style="margin-top:6px"><input class="in" type="password" style="max-width:220px" placeholder="new password (10+ characters)"><button class="btn" type="button">Save</button><span class="small"></span></div>`);
    const row = li.lastElementChild; row.querySelector("button").onclick = async () => { try { await api("/api/workspaces/reset-password", {method: "POST", body: {user_id: +b.dataset.reset, password: row.querySelector("input").value}});
      row.querySelector("span").className = "small okt"; row.querySelector("span").textContent = "Password changed. Tell them the new one."; } catch (e) { row.querySelector("span").className = "small err"; row.querySelector("span").textContent = e.message; } }; });
  $("aiP").value = a.provider; $("aiM").value = a.model || ""; $("aiE").value = a.effort || "low"; $("aiU").value = a.url || ""; $("aiCap").value = a.daily_call_cap; $("aiT").value = a.timeout;
  $("aiUsd").value = a.monthly_cap_usd; $("aiPer").value = a.usd_per_call; $("aiOk").checked = !!a.approved; $("aiHelp").textContent = HELP[a.provider] || "";
  const keyName = p => p === "anthropic" ? "ai_anthropic" : "ai_openai";
  $("aiKey").placeholder = s.secrets[keyName(a.provider)] ? "saved: " + s.secrets[keyName(a.provider)] : "paste a key to save it";
  $("sP").value = q.provider; $("sCap").value = q.monthly_cap_usd; $("sPer").value = q.usd_per_1k; $("sGap").value = q.gap_s; $("sOk").checked = !!q.approved;
  $("sKey").placeholder = s.secrets["search_" + q.provider] ? "saved: " + s.secrets["search_" + q.provider] : "paste a key to save it";
  if (!s.is_admin) document.querySelectorAll("#aiSave,#sSave,#cSave").forEach(b => { b.disabled = true; b.title = "Only the workspace owner can change providers"; });
  const u = (await api("/api/usage")).usage;
  $("usage").innerHTML = u.length ? u.map(r => `<tr><td>${esc(r.month)}</td><td>${esc(r.provider)}</td><td>${esc(r.kind)}</td><td>${fmt(r.calls)}</td><td>${fmt(r.ok)}</td><td>$${r.usd ?? 0}</td></tr>`).join("") : '<tr><td colspan="6" class="faint">No provider calls yet.</td></tr>';
}
$("aiP").onchange = () => { $("aiHelp").textContent = HELP[$("aiP").value] || ""; };
$("aiSave").onclick = async () => { try {
  const p = $("aiP").value;
  await api("/api/settings", {method: "POST", body: {ai: {provider: p, model: $("aiM").value.trim(), effort: $("aiE").value, url: $("aiU").value.trim(), daily_call_cap: +$("aiCap").value || 0, timeout: +$("aiT").value || 180,
    monthly_cap_usd: +$("aiUsd").value || 0, usd_per_call: +$("aiPer").value || 0, approved: $("aiOk").checked}}});
  if ($("aiKey").value.trim()) { await api("/api/settings/secret", {method: "POST", body: {name: p === "anthropic" ? "ai_anthropic" : "ai_openai", value: $("aiKey").value.trim()}}); $("aiKey").value = ""; }
  $("aiMsg").className = "small okt"; $("aiMsg").textContent = "Saved."; load(); } catch (e) { $("aiMsg").className = "small err"; $("aiMsg").textContent = e.message; } };
$("aiTest").onclick = async () => { $("aiMsg").className = "small"; $("aiMsg").textContent = "Testing (one small call)…"; try { const r = await api("/api/settings/test-ai", {method: "POST"});
  $("aiMsg").className = "small " + (r.ok ? "okt" : "err"); $("aiMsg").textContent = `${r.ok ? "Connected" : "Not working"}: ${r.message} (${r.seconds}s)`; load(); } catch (e) { $("aiMsg").className = "small err"; $("aiMsg").textContent = e.message; } };
$("sSave").onclick = async () => { try {
  const p = $("sP").value;
  await api("/api/settings", {method: "POST", body: {search: {provider: p, monthly_cap_usd: +$("sCap").value || 0, usd_per_1k: +$("sPer").value || 0, gap_s: +$("sGap").value || 20, approved: $("sOk").checked}}});
  if ($("sKey").value.trim() && ["serper","brave","tavily"].includes(p)) { await api("/api/settings/secret", {method: "POST", body: {name: "search_" + p, value: $("sKey").value.trim()}}); $("sKey").value = ""; }
  $("sMsg").className = "small okt"; $("sMsg").textContent = "Saved."; load(); } catch (e) { $("sMsg").className = "small err"; $("sMsg").textContent = e.message; } };
$("sTest").onclick = async () => { $("sMsg").textContent = "Searching…"; try { const r = await api("/api/settings/test-search", {method: "POST", body: {q: $("sQ").value}});
  $("sMsg").className = "small " + (r.ok ? "okt" : "err"); $("sMsg").textContent = r.ok ? `${r.results.length} results: ${r.results.slice(0, 3).join(", ")}` : r.message; } catch (e) { $("sMsg").textContent = e.message; } };
$("cSave").onclick = async () => { try {
  const p = $("cP").value;
  await api("/api/settings", {method: "POST", body: {contacts: {provider: p, monthly_cap_usd: +$("cCap").value || 0, usd_per_lookup: +$("cPer").value || 0, per_company: +$("cN").value || 5, approved: $("cOk").checked}}});
  if ($("cKey").value.trim() && p !== "site") { await api("/api/settings/secret", {method: "POST", body: {name: "contacts_" + p, value: $("cKey").value.trim()}}); $("cKey").value = ""; }
  $("cMsg").className = "small okt"; $("cMsg").textContent = "Saved. Applies to the next research run."; load(); } catch (e) { $("cMsg").className = "small err"; $("cMsg").textContent = e.message; } };
$("mAdd").onclick = async () => { try { await api("/api/workspaces/members", {method: "POST", body: {email: $("mE").value, password: $("mP").value}}); $("mMsg").className = "small okt"; $("mMsg").textContent = "Added."; } catch (e) { $("mMsg").className = "small err"; $("mMsg").textContent = e.message; } };
$("pSave").onclick = async () => { try { await api("/api/password", {method: "POST", body: {old: $("pOld").value, new: $("pNew").value}}); $("pMsg").className = "small okt"; $("pMsg").textContent = "Changed."; } catch (e) { $("pMsg").className = "small err"; $("pMsg").textContent = e.message; } };
(async () => { await loadMe(); nav("/settings"); load(); })();
