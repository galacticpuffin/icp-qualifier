/* Master dashboard: same components, interactions and counts as the original; labels, segments and lists come from the
   workspace's ICP profiles and uploaded lists. */
const PAGE = 100;
let LISTS = [["", "All lists"]], LL = {}, VERTS = [["GENERAL", "General"]], VL = {GENERAL: "General"}, LBL = {core: "Fit verified", hold: "Enterprise Hold"}, PRIODESC = {};
const STATUSES_BASE = () => [["Q","Qualified"],["A","A"],["B","B"],["C","C"],["READY","Ready for outreach"],["HELD","Held back"],["REVIEW","Review"],["HOLD",LBL.hold],["DQ","Disqualified"],["ROUTED","Routed to parent"],["SMSYES",LBL.core + " (any status)"],["|"],["RETRY","Retry (search blocked)"],["PENDING_WEBSITE","No website yet"],["PENDING","Not yet processed"],["MERGED","Merged rows"],["ALL","All records"]];
const TITLE = {Q:"Qualified",A:"Priority A",B:"Priority B",C:"Priority C",READY:"Ready for Outreach",HELD:"Held Back",REVIEW:"Review",HOLD:"Hold",DQ:"Disqualified",ROUTED:"Routed to Parent",SMSYES:"Fit-Verified",RETRY:"Retry",PENDING_WEBSITE:"No Website Yet",PENDING:"Not Yet Processed",MERGED:"Merged",ALL:""};
let SHORT = {READY:"Ready for outreach",QUALIFIED:"Qualified · held back",HOLD:"Hold",REVIEW:"Review",RETRY:"Retry · research incomplete",PENDING_WEBSITE:"No website · not researched",PENDING:"Not yet processed",DQ:"Disqualified",ROUTED:"Routed to parent",MERGED:"Merged row"};
const PORD = {A:0,B:1,C:2,HOLD:3,REVIEW:4,DQ:6};
const SORD = {READY:0,QUALIFIED:1,HOLD:2,REVIEW:3,RETRY:4,PENDING_WEBSITE:5,PENDING:6,DQ:7,ROUTED:8,MERGED:9};
const isQ = a => a.pr === "A" || a.pr === "B" || a.pr === "C";
const dash = '<span style="color:var(--faint)">—</span>';
let S = null, A = [], view = [], DET = {}, RULES = null;
const st = {p:"", sig:"", l:"", s:"Q", v:"", m:"", q:"", t:"", r:"", o:"", c:"", g:"", k:"", x:"", u:"", a:"", sort:"", dir:1, shown:PAGE, open:new Set()};
const XF = {t:[["","All"],["TARGET TECH VERIFIED","Target technology verified"],["FIT VERIFIED ONLY","Fit verified only"],["NEEDS VERIFICATION","Needs verification"]],
  r:[["","All"],["Research complete","Research complete"],["BLOCKED","Blocked (search / no website)"],["Pending research","Pending research"]],
  o:[["","All"],["60","60+"],["40","40+"],["20","20+"]], c:[["","All"],["DIRECT","Direct prospects"],["CHANNEL / PARTNER","Channel / partner"]],
  g:[["","All"],["Y","Has verified trigger"]], p:[["","All"],["Y","Has decision-makers"],["C","Buying-committee match"]], a:[["","All"],["STRONG","AI candidate · strong marker"],["ANY","Any AI candidate"]]};
const optHtml = (id, list) => list.map(([k,l]) => `<input type="radio" name="f${id}" id="f${id}-${k ? k.replace(/[^A-Za-z0-9]/g,"_") : "ALL"}" value="${esc(k)}"><label for="f${id}-${k ? k.replace(/[^A-Za-z0-9]/g,"_") : "ALL"}">${esc(l)}</label>`).join("");
for (const [id, list] of Object.entries(XF)) $("opt" + id.toUpperCase()).innerHTML = optHtml(id, list);
function dynOpts(){
  const cnt = (f) => { const m = {}; A.forEach(a => String(a[f] || "").split(/[;,]/).map(x => x.trim()).filter(Boolean).forEach(x => m[x] = (m[x] || 0) + 1));
    return [["","All"], ...Object.entries(m).sort((a, b) => b[1] - a[1]).slice(0, 14).map(([k, n]) => [k, `${k} · ${n}`])]; };
  $("optK").innerHTML = optHtml("k", cnt("cc")); $("optX").innerHTML = optHtml("x", cnt("vend")); $("optU").innerHTML = optHtml("u", cnt("uc"));
}
const KPI = () => [["Q","Qualified","var(--accent)"],["READY","Ready for outreach","var(--ok)"],["REVIEW","Review","var(--rev)"],["RETRY","Retry · search blocked","var(--rev)"],
  ["PENDING_WEBSITE","No website yet","var(--faint)"],["PENDING","Not yet processed","var(--faint)"],["HOLD",LBL.hold,"var(--hold)"],["DQ","Disqualified","var(--dq)"],["ROUTED","Routed to parent","var(--qb)"],["SMSYES",LBL.core,"var(--ok)"]];
let COLS = [];

/* scaffolding that depends on the workspace (lists, segments, labels) */
function scaffold(){
  const prof = S.profiles[String(st.l ? (S.lists[st.l].profile_id || S.default_profile) : S.default_profile)] || Object.values(S.profiles)[0] || {labels:{}, segments:[["GENERAL","General"]], describe_priority:{}};
  LBL = {core: prof.labels.core || "Fit verified", hold: prof.labels.hold || "Hold", use_case: prof.labels.use_case || "Signal / use case", stack: prof.labels.stack || "Tech / competitor", tagline: prof.labels.tagline || ""};
  PRIODESC = prof.describe_priority || {};
  SHORT.HOLD = LBL.hold;
  TITLE.HOLD = LBL.hold; TITLE.SMSYES = LBL.core;
  LISTS = [["", "All lists"], ...Object.entries(S.lists).map(([k, x]) => [k, x.name])];
  LL = Object.fromEntries(LISTS.slice(1));
  VERTS = prof.segments.length ? prof.segments : [["GENERAL","General"]];
  VL = Object.fromEntries(VERTS);
  $("brand").textContent = (S.workspace || "ICP").toUpperCase() + " · MASTER";
  $("mono").textContent = (S.workspace || "IQ").replace(/[^A-Za-z0-9 ]/g, "").split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0]).join("").toUpperCase() || "IQ";
  document.title = (S.workspace || "ICP") + " · Master";
  $("tagline").textContent = (LBL.tagline ? LBL.tagline + " — " : "") + `one live view of ${LISTS.length - 1 === 1 ? "your uploaded list" : "your " + (LISTS.length - 1) + " uploaded lists"}, qualified with ${prof.name ? "the “" + prof.name + "” ICP profile" : "your ICP profile"}`;
  const cur = $("lpick").value;
  $("lpick").innerHTML = LISTS.map(([k, l]) => `<option value="${esc(k)}">${esc(k ? l : (LISTS.length > 2 ? "All " + (LISTS.length - 1) + " lists" : "All lists"))}</option>`).join("");
  $("lpick").value = LL[cur] ? cur : st.l || "";
  $("kpis").innerHTML = KPI().map(([k,l,c]) => `<button class="card kcard" type="button" data-s="${k}" aria-pressed="false">
  <span class="k"><i style="background:${c}"></i>${esc(l)}</span><span class="v" id="kv-${k}">0</span><span class="s" id="ks-${k}"></span></button>`).join("");
  $("lists").innerHTML = LISTS.map(([k,l]) => `<button class="card lcard" type="button" data-l="${k}" aria-pressed="false">
  <span class="k">${esc(l)}</span><span class="v" id="lv-${k || "ALL"}">0</span><span class="s" id="ls-${k || "ALL"}"></span></button>`).join("");
  $("verts").innerHTML = VERTS.map(([k,l]) => `<button class="card vcard" type="button" data-v="${esc(k)}" aria-pressed="false">
  <span class="k">${esc(l)}</span><span class="v" id="vv-${k}">0</span>
  <span class="abc"><span>A <b id="va-${k}">0</b></span><span>B <b id="vb-${k}">0</b></span><span>C <b id="vc-${k}">0</b></span><span>Ready <b id="vr-${k}">0</b></span></span>
  <span class="pp" id="vp-${k}" style="font:500 .72rem var(--f-data);color:var(--faint)"></span></button>`).join("");
  $("optL").innerHTML = LISTS.map(([k,l]) => `<input type="radio" name="fl" id="fl-${k || "ALL"}" value="${k}"><label for="fl-${k || "ALL"}">${esc(l)}</label>`).join("");
  $("optS").innerHTML = STATUSES_BASE().map(([k,l]) => k === "|" ? '<span class="sep"></span>' : `<input type="radio" name="fs" id="fs-${k}" value="${k}"><label for="fs-${k}">${esc(l)}</label>`).join("");
  $("optMh").textContent = LBL.core;
  $("optM").innerHTML = [["","All"],["YES","Verified (Yes)"],["NO","Not verified"]].map(([k,l]) => `<input type="radio" name="fm" id="fm-${k || "ALL"}" value="${k}"><label for="fm-${k || "ALL"}">${l}</label>`).join("");
  $("optV").innerHTML = [["","All"], ...VERTS].map(([k,l]) => `<input type="radio" name="fv" id="fv-${k || "ALL"}" value="${esc(k)}"><label for="fv-${k || "ALL"}">${esc(l)}</label>`).join("");
  $("optTw").classList.toggle("hidden", !prof.has_target_tech);
  COLS = [["company","Company"],["list","List"],["priority","Priority"],["sms",LBL.core],["useCase",LBL.use_case],["vertical","Segment"],["stack",LBL.stack],["opp","Fit score"],["evidence","Evidence"],["status","Status"]];
  $("thead").innerHTML = COLS.map(([k,l]) => `<th data-k="${k}"><button type="button">${esc(l)} <span class="ar"></span></button></th>`).join("");
  const finals = ["MASTER_ALL_ACCOUNTS","OUTREACH_READY",...Object.keys(S.lists).map(k => `LIST_${k}_QUALIFIED`),"PRIORITY_A_ACCOUNTS","TECHNOLOGY_OPPORTUNITIES","CHANNEL_PARTNER_OPPORTUNITIES","ACTIVE_BUYING_SIGNALS","REVIEW_AND_HOLD","RESEARCH_BLOCKED","WITH_DECISION_MAKERS","DECISION_MAKERS"].concat(prof.has_target_tech ? ["TARGET_TECH_VERIFIED"] : []);
  const nice = f => f.startsWith("LIST_") ? `${LL[f.split("_")[1]] || "List"} — qualified` : f;
  $("finals").innerHTML = finals.map(f => `<div style="display:flex;justify-content:space-between;gap:12px;padding:4px 0"><a class="link" href="/export/${f}.csv" download>${esc(nice(f))}.csv</a><a class="link" href="/export/${f}.xlsx" download>xlsx</a></div>`).join("") +
    `<a class="link" href="/export/MANIFEST.json" download style="display:block;padding:4px 0">MANIFEST.json (rows + sha256)</a>`;
  $("defsList").innerHTML = [["A", PRIODESC.A || "Verified fit + strong scale", "p-A"], ["B", PRIODESC.B || "Verified fit + meaningful scale", "p-B"], ["C", PRIODESC.C || "Verified fit; scale not established", "p-C"],
    ["READY", `Qualified A/B/C that passes the outreach checks: ${LBL.core.toLowerCase()}, evidence audit PASS (quote found on the cited page, on the company's own domain), not flagged weak, not a competitor/vendor, one record per company across lists`, "p-READY"],
    ["HELD BACK", "Qualified A/B/C kept out of outreach; the reason is shown on the row (evidence on another site, audit not PASS, flagged weak, duplicate of a READY record on another list)", "p-QUALIFIED"],
    ["REVIEW", "Research complete, fit not sufficiently verified (partial evidence, a missing mandatory signal, an entity check, or nothing was found after the full check)", "p-REVIEW"],
    ["RETRY", "Research incomplete: needed searches blocked or not run, the website could not be read, or research errors. Not counted as research complete", "p-RETRY"],
    ["NO WEBSITE", "No website known, so nothing was researched yet. Pending website discovery, not complete", "p-PENDING_WEBSITE"],
    ["PENDING", "Not processed yet", "p-PENDING"], [LBL.hold.toUpperCase(), "Passes the qualification rule but parked by the profile's hold rule (research kept)", "p-HOLD"],
    ["DQ", "Disqualified by the profile: competitor/vendor, excluded industry, outside the targeting, or a disqualifying statement on the company's own site", "p-DQ"],
    ["ROUTED", "Department, location or unit routed to its parent company in the same list; never qualified on the parent's evidence", "p-ROUTED"]]
    .map(([t, d, c]) => `<dt><span class="pill ${c}">${esc(t)}</span></dt><dd>${esc(d)}</dd>`).join("") +
    `<dt><span class="ea ea-PASS" style="margin:0">EVIDENCE PASS</span></dt><dd>Evidence audit of a qualified account: the quote is on the cited page on the company's own domain${S && Object.values(S.profiles)[0] ? "" : ""} and, when the profile asks for it, carries an explicit proof marker. Required for READY. NEEDS REVIEW / FAIL keep the account qualified but out of outreach</dd>` +
    `<dt><span class="pill p-MERGED">MERGED</span></dt><dd>A duplicate source row counted under its company (kept visible for reconciliation)</dd>` +
    `<dt>Segment</dt><dd>Segmentation only; never determines qualification</dd><dt>Fit score</dt><dd>Explains and ranks; it never qualifies an account by itself</dd>`;
}

/* counts */
const inList = a => !st.l || a.list === st.l;
function counts(){
  const L = st.l ? [S.lists[st.l]] : Object.values(S.lists);
  const sum = f => L.reduce((t, x) => t + f(x), 0);
  const comp = sum(x => x.companies), proc = sum(x => x.PROCESSED), done = sum(x => x.RESEARCH_COMPLETE);
  const pct = (n, d) => (d ? 100 * n / d : 0).toFixed(2) + "%";
  const recs = A.filter(inList);
  const c = {}; recs.forEach(a => c[a.stage] = (c[a.stage] || 0) + 1);
  const q = recs.filter(a => a.stage !== "MERGED" && isQ(a)), ab = {A:0,B:0,C:0}; q.forEach(a => ab[a.pr]++);
  const ready = recs.filter(a => a.stage === "READY"), rb = {A:0,B:0,C:0}; ready.forEach(a => rb[a.pr]++);
  $("pul").textContent = st.l ? LL[st.l] : (LISTS.length > 2 ? "All " + (LISTS.length - 1) + " lists" : "All lists");
  $("pu").textContent = fmt(comp);
  $("pus").textContent = `companies · ${fmt(recs.length)} source records incl. ${fmt(c.MERGED || 0)} merged duplicate rows`;
  $("p1").innerHTML = `${fmt(proc)} <small>/ ${fmt(comp)}</small>`; $("p1b").style.width = pct(proc, comp);
  $("p1s").textContent = `${fmt(c.PENDING || 0)} not yet processed`;
  $("p2").innerHTML = `${fmt(done)} <small>/ ${fmt(comp)}</small>`; $("p2b").style.width = pct(done, comp);
  $("p2s").textContent = `Retry ${fmt(c.RETRY || 0)} · no website ${fmt(c.PENDING_WEBSITE || 0)}`;
  $("pa").innerHTML = `${fmt(ready.length)} <small>A ${rb.A} · B ${rb.B} · C ${rb.C}</small>`; $("pab").style.width = pct(ready.length, Math.max(1, q.length));
  const tv = L.reduce((t, x) => t + (x.ready_target_verified || 0), 0);
  $("pas").textContent = `of ${fmt(q.length)} qualified` + (!$("optTw").classList.contains("hidden") ? ` · target technology verified on ${fmt(tv)} ready` : "");
  $("kv-Q").textContent = fmt(q.length); $("ks-Q").textContent = `A ${ab.A} · B ${ab.B} · C ${ab.C} · held back ${fmt(c.QUALIFIED || 0)}`;
  $("kv-READY").textContent = fmt(ready.length); $("ks-READY").textContent = "Verified evidence on own site, deduplicated";
  $("kv-REVIEW").textContent = fmt(c.REVIEW || 0); $("ks-REVIEW").textContent = "Research complete, fit not verified";
  $("kv-RETRY").textContent = fmt(c.RETRY || 0); $("ks-RETRY").textContent = "Searches blocked / site unreadable — not complete";
  $("kv-PENDING_WEBSITE").textContent = fmt(c.PENDING_WEBSITE || 0); $("ks-PENDING_WEBSITE").textContent = "Pending website discovery — not complete";
  $("kv-PENDING").textContent = fmt(c.PENDING || 0); $("ks-PENDING").textContent = "Queued for research";
  $("kv-HOLD").textContent = fmt(c.HOLD || 0); $("ks-HOLD").textContent = "Qualified, parked by the hold rule";
  $("kv-DQ").textContent = fmt(c.DQ || 0); $("ks-DQ").textContent = "Competitor, excluded, out of range, disqualifier";
  $("kv-ROUTED").textContent = fmt(c.ROUTED || 0); $("ks-ROUTED").textContent = "Unit/location counted under its parent";
  const sv = recs.filter(a => a.sms === "Yes" && !["DQ","ROUTED","MERGED"].includes(a.stage)).length;
  $("kv-SMSYES").textContent = fmt(sv); $("ks-SMSYES").textContent = "Company-specific verified evidence, not DQ";
  const ea = {PASS:0, "NEEDS REVIEW":0, FAIL:0}; q.forEach(a => { if (a.ea) ea[a.ea.s] = (ea[a.ea.s] || 0) + 1; });
  $("ks-Q").textContent += ` · Evidence audit: PASS ${fmt(ea.PASS)} · NEEDS REVIEW ${fmt(ea["NEEDS REVIEW"])} · FAIL ${fmt(ea.FAIL)}`;
  LISTS.forEach(([k]) => { const x = k ? [S.lists[k]] : Object.values(S.lists);
    $("lv-" + (k || "ALL")).textContent = fmt(x.reduce((t, y) => t + y.companies, 0));
    const rd = A.filter(a => (!k || a.list === k) && a.stage === "READY").length, qq = A.filter(a => (!k || a.list === k) && a.stage !== "MERGED" && isQ(a)).length;
    $("ls-" + (k || "ALL")).innerHTML = `Qualified ${fmt(qq)} · Ready ${fmt(rd)}`; });
  VERTS.forEach(([k]) => { const r = recs.filter(a => a.stage !== "MERGED" && (a.vert || "GENERAL") === k);
    const x = {A:0,B:0,C:0}; r.filter(isQ).forEach(a => x[a.pr]++);
    $("vv-" + k).textContent = fmt(x.A + x.B + x.C); $("va-" + k).textContent = x.A; $("vb-" + k).textContent = x.B; $("vc-" + k).textContent = x.C;
    $("vr-" + k).textContent = r.filter(a => a.stage === "READY").length;
    const pr = r.filter(a => a.stage !== "PENDING");
    $("vp-" + k).textContent = `${fmt(pr.length)} processed · Review ${fmt(pr.filter(a => a.stage === "REVIEW").length)} · Retry ${fmt(pr.filter(a => a.stage === "RETRY").length)} · Hold ${pr.filter(a => a.stage === "HOLD").length} · DQ ${fmt(pr.filter(a => a.stage === "DQ").length)}`; });
  panels(recs); recon(); health(); facts(); signals(recs);
}
function panels(recs){
  const sig = {}, ind = {};
  for (const a of recs){ if (a.stage === "MERGED" || a.stage === "PENDING") continue;
    const k = a.ind || "Not in list data"; (ind[k] ??= {n:0, q:0}).n++; if (isQ(a)) ind[k].q++;
    if (a.sms === "Yes" && (isQ(a) || a.stage === "HOLD")) String(a.uc || "").split(/[;,]/).map(s => s.trim()).filter(s => s && s !== "—").forEach(t => sig[t] = (sig[t] || 0) + 1); }
  const s = Object.entries(sig).sort((a, b) => b[1] - a[1]).slice(0, 24);
  $("sigs").innerHTML = s.length ? s.map(([k, n]) => `<div class="ind"><span>${esc(k)}</span><b>${fmt(n)}</b></div>`).join("") : '<div class="ind"><span>No verified signals yet</span><b>0</b></div>';
  const d = Object.entries(ind).sort((a, b) => b[1].q - a[1].q || b[1].n - a[1].n).slice(0, 24);
  $("inds").innerHTML = d.length ? d.map(([k, x]) => `<div class="ind" title="${esc(k)}"><span>${esc(k)}</span><b>${fmt(x.n)} · <em>${fmt(x.q)}</em></b></div>`).join("") : '<div class="ind"><span>No processed accounts yet</span><b>0</b></div>';
}
const ago = t => t ? Math.round((Date.now() - Date.parse(t.endsWith("Z") || t.includes("+") ? t : t + "Z")) / 60000) + " min ago" : "—";
function ops(){
  const O = S.ops; if (!O) { $("ops").innerHTML = '<div class="ind"><span>Operations data loading</span><b>—</b></div>'; return; }
  const rows = [];
  for (const k of Object.keys(S.lists).filter(k => !st.l || k === st.l)) { const x = O.lists[k] || {};
    rows.push([`${LL[k]} research`, `${fmt(x.researched_1h)}/h`, `${fmt(x.researched_24h)} in 24 h · ${fmt(x.not_researched)} not yet researched · checkpoint ${ago(x.last_checkpoint)}`]);
    rows.push([`${LL[k]} search queue`, fmt(x.search_queue), `own site done, waiting for search · ${fmt(x.evidence_24h)} evidence rows in 24 h · ${fmt(x.failed)} failed`]); }
  const g = O.search || {}, lf = g.last_60_min || [0, 0];
  rows.push(["Search (last 60 min)", `${fmt(lf[0])} ok / ${fmt(lf[1])} failed`, `provider ${g.provider || "none"}` + Object.entries(g.engines || {}).map(([n, v]) => ` · ${n} ${v.paused_for_min ? "paused " + Math.round(v.paused_for_min) + " min" : "gap " + Math.round(v.gap_s) + " s"}`).join("")]);
  rows.push(["Licensed search API", ["serper","brave","tavily"].includes(g.provider) ? (g.approved ? "ON" : "NOT APPROVED") : "OFF", ["serper","brave","tavily"].includes(g.provider) ? `${g.provider}: $${g.this_month_usd} of $${g.cap} this month` : "no paid search configured"]);
  const ai = O.ai || {};
  rows.push(["AI provider", ai.provider === "off" || !ai.provider ? "OFF" : ai.provider, ai.provider && ai.provider !== "off" ? `${ai.calls_today} of ${ai.daily_cap} calls today · model ${ai.model}` : "rules-only qualification"]);
  const R = O.runner || {};
  rows.push(["Workers", `${fmt(R.active_runs || 0)} run${R.active_runs === 1 ? "" : "s"} active`, `${R.threads_default || "—"} threads per run by default · runs are resumable`]);
  rows.push(["New research ETA", O.eta_hours_new_research != null ? `≈ ${O.eta_hours_new_research} h` : "—", `${fmt(O.not_researched)} accounts at ${fmt(O.research_rate_1h)}/h (last hour, measured)`]);
  rows.push(["Spend", `$${(O.spend.search_month_usd || 0) + (O.spend.ai_month_usd || 0)} this month`, `search $${O.spend.search_month_usd || 0} · AI APIs $${O.spend.ai_month_usd || 0} (subscription CLIs not billed here)`]);
  $("ops").innerHTML = rows.map(([k, v, s]) => `<div class="ind" title="${esc(s)}"><span>${esc(k)}<br><span style="color:var(--faint);font-size:.74rem">${esc(s)}</span></span><b>${esc(v)}</b></div>`).join("");
}
function engine(){
  const I = S.intel || {}, ai = I.ai || {};
  const rows = [["AI review", ai.provider && ai.provider !== "off" ? "On" : "Off", ai.provider && ai.provider !== "off" ? "shadow review of REVIEW accounts; never changes a verdict" : "turn on in Settings + the profile"],
    ["Model", ai.provider && ai.provider !== "off" ? (ai.model || "default") : "—", ai.provider && ai.provider !== "off" ? ai.provider : "rules only"],
    ["AI review queue", I.ai_queue != null ? fmt(I.ai_queue) : "—", "REVIEW accounts not yet reviewed"],
    ["Active runs", fmt((I.runner || {}).active_runs || 0), "Lists & runs page starts, pauses and resumes runs"],
    ["Researched last hour", fmt(I.researched_last_hour), Object.entries(S.ops.lists || {}).map(([k, v]) => `${LL[k]} ${v.researched_1h ?? "—"}`).join(" · ")],
    ["Not yet processed", fmt(I.pending), I.eta_hours_pending ? `≈ ${I.eta_hours_pending} h at the measured rate` : "rate not measurable"],
    ["Blocked: searches", fmt((I.blocked || {}).retry), "retry queue: provider off, paused or capped"], ["Blocked: no website", fmt((I.blocked || {}).no_website), "website discovery found no verified match"],
    ["Accounts with verified signals", fmt(I.with_verified_signals), "quotes from the company's own pages"], ["AI candidates (unverified)", `${fmt(I.ai_candidates_strong)} strong / ${fmt(I.ai_candidates)}`, "human review list, never auto-promoted; strong = proof marker in the quote"]];
  $("eng").innerHTML = rows.map(([k, v, s]) => `<div class="ind" title="${esc(s)}"><span>${esc(k)}<br><span style="color:var(--faint);font-size:.74rem">${esc(s)}</span></span><b>${esc(v)}</b></div>`).join("");
}
function recon(){
  const ST = [["READY","Ready for outreach"],["QUALIFIED","Qualified · held back"],["HOLD",LBL.hold],["REVIEW","Review (research complete)"],["RETRY","Retry (search blocked / site unreadable)"],["PENDING_WEBSITE","No website (not researched)"],["PENDING","Not yet processed"],["DQ","Disqualified"],["ROUTED","Routed to parent"],["MERGED","Merged duplicate rows"]];
  const keys = Object.keys(S.lists).filter(k => !st.l || st.l === k);
  $("recon").innerHTML = keys.length ? keys.map(k => { const x = S.lists[k];
    const total = ST.reduce((t, [s]) => t + (x.stages[s] || 0), 0) + (x.recon[1] ? 0 : 0), traced = x.recon[x.recon.length - 1][1];
    const shownRows = total;
    return `<div class="rbox"><h3>${esc(LL[k])}</h3><table class="rtab"><tbody>` +
      x.recon.map(([t, n]) => `<tr><td>${esc(t)}</td><td class="n">${typeof n === "number" ? fmt(n) : esc(n)}</td></tr>`).join("") +
      ST.map(([s, l]) => `<tr><td>${esc(l)}</td><td class="n">${fmt(x.stages[s] || 0)}</td></tr>`).join("") +
      `<tr class="tot"><td>Total records shown</td><td class="n ${shownRows === traced ? "okc" : "badc"}">${fmt(shownRows)} ${shownRows === traced ? "✓ matches" : "≠ " + fmt(traced)}</td></tr></tbody></table></div>`; }).join("")
    : '<div class="rbox"><h3>No lists yet</h3><table class="rtab"><tbody><tr><td>Upload a list on the <a href="/lists">Lists &amp; runs</a> page</td></tr></tbody></table></div>';
}
function health(){
  const live = S.last_success && (Date.now() - Date.parse(S.last_success)) / 1000 < 180;
  const ago2 = t => { if (!t) return "never"; const m = Math.round((Date.now() - Date.parse(t)) / 60000); return m < 1 ? "just now" : m < 120 ? m + " min ago" : Math.round(m / 60) + " h ago"; };
  $("health").innerHTML = `<span><span class="dot ${live ? "ok" : "bad"}"></span><b>${live ? "LIVE" : "STALE"}</b> · last successful refresh ${new Date(S.last_success).toLocaleTimeString()} (every 30 s)</span>` +
    (S.error ? `<span><span class="dot bad"></span>last refresh failed: ${esc(S.error)}</span>` : "") +
    Object.entries(S.lists).filter(([k]) => !st.l || k === st.l).map(([k, x]) => { const r = x.run, on = r && r.status === "running", warn = r && ["paused","queued"].includes(r.status), bad = r && r.status === "error";
      return `<span><span class="dot ${bad ? "bad" : on ? "ok" : warn ? "warn" : ""}"></span>${esc(LL[k])}: ${r ? esc(r.mode) + " run " + esc(r.status) : "no run yet"} · last research ${ago2(x.health.last_research)} · last verdict ${ago2(x.health.last_verify)}</span>`; }).join("");
}
function facts(){
  const f = [["Ready for outreach (all lists, deduplicated)", fmt(S.READY_deduped)],
    ...Object.entries(S.lists).flatMap(([k, x]) => [[`${LL[k]} research complete`, `${fmt(x.RESEARCH_COMPLETE)} / ${fmt(x.companies)}`], [`${LL[k]} ${LBL.core.toLowerCase()} (Yes)`, fmt(x.VERIFIED_SMS)]]),
    ["Data computed", new Date(S.generated).toLocaleString()]];
  $("rd").innerHTML = f.map(([t, d]) => `<div><dt>${esc(t)}</dt><dd>${esc(d)}</dd></div>`).join("") +
    (RULES ? RULES.map(([t, d]) => `<div class="wide"><dt>${esc(t)}</dt><dd>${esc(d)}</dd></div>`).join("") : "") +
    `<div class="wide"><dt>Research complete</dt><dd>Counts only accounts whose research actually finished: qualified, hold, review and disqualified. Accounts whose needed searches were blocked (RETRY), whose website could not be read, or that have no website yet are shown separately and are never counted as complete.</dd></div>` +
    `<div class="wide"><dt>Ready for outreach</dt><dd>Qualified A/B/C with the fit verified, an evidence quote and a source URL on the company's own website, evidence audit PASS, not flagged weak and not a competitor or vendor. When the same company is ready on more than one list it appears once; the other copies stay qualified with the reason "duplicate of READY …". Original list membership is kept in the List column.</dd></div>` +
    `<div class="wide"><dt>Live updates</dt><dd>This page reads this workspace's research database every 30 seconds. Workers keep running in the background after you close the page. Other workspaces' data is never mixed in.</dd></div>`;
}

/* signals panel: verified / inferred counts per profile signal; click = accounts with that signal, ranked by fit score */
function signals(recs){
  const pid = String(st.l ? (S.lists[st.l].profile_id || S.default_profile) : S.default_profile);
  const sigs = ((S.profiles[pid] || {}).signals) || [];
  const live = recs.filter(a => a.stage !== "MERGED");
  $("sgx").innerHTML = sigs.length ? sigs.map(g => { const v = live.filter(a => (a.sids || []).includes(g.id)).length, i = live.filter(a => (a.sidi || []).includes(g.id)).length;
    return `<button class="ind" type="button" data-sig="${esc(g.id)}" style="cursor:pointer;text-align:left;font:inherit;color:inherit;${st.sig === g.id ? "border-color:var(--accent-line);background:var(--accent-soft)" : ""}"><span>${esc(g.label)}<br><span style="color:var(--faint);font-size:.74rem">${esc({mandatory:"must have",preferred:"raises score",negative:"counts against",info:"recorded"}[g.req] || g.req)} · weight ${g.weight} · ${i} inferred</span></span><b>${fmt(v)}</b></button>`; }).join("")
    : '<div class="ind"><span>No signals in this profile yet</span><b>0</b></div>';
  $("sgx").querySelectorAll("[data-sig]").forEach(b => b.onclick = () => { st.sig = st.sig === b.dataset.sig ? "" : b.dataset.sig; if (st.sig) { st.sort = "opp"; st.dir = 1; } setView("ALL", ""); counts(); });
}
$("sigForm").addEventListener("submit", async e => {
  e.preventDefault(); const m = $("sgMsg"); m.className = "small"; m.textContent = "Saving…";
  try {
    const pid = st.l ? (S.lists[st.l].profile_id || S.default_profile) : S.default_profile;
    const prof = await api("/api/profiles/" + pid);
    const cfg = prof.config, label = $("sgName").value.trim();
    cfg.signals.push({id: label.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "").slice(0, 40) + "_" + (cfg.signals.length + 1), label, category: "other",
      patterns: $("sgPats").value.split(",").map(x => x.trim()).filter(Boolean), markers: [], requirement: $("sgReq").value, weight: +$("sgW").value || 0});
    await api("/api/profiles/" + pid, {method: "PUT", body: {config: cfg, note: "signal search added: " + label}});
    const lists = Object.entries(S.lists).filter(([, x]) => (x.profile_id || S.default_profile) === pid).map(([k]) => +k);
    for (const lid of lists) await api("/api/runs", {method: "POST", body: {list_id: lid, profile_id: pid, mode: "requalify"}});
    m.className = "small okt"; m.textContent = `Added. Rescoring ${lists.length} list${lists.length === 1 ? "" : "s"}; results update here automatically.`; $("sgName").value = ""; $("sgPats").value = "";
    lastGen = ""; setTimeout(load, 3000);
  } catch (err) { m.className = "small err"; m.textContent = err.message; }
});

/* filtering */
function matchS(a){
  switch (st.s){
    case "Q": return a.stage !== "MERGED" && isQ(a);
    case "A": case "B": case "C": return a.stage !== "MERGED" && a.pr === st.s;
    case "HELD": return a.stage === "QUALIFIED";
    case "SMSYES": return a.sms === "Yes" && !["DQ","ROUTED","MERGED"].includes(a.stage);
    case "ALL": return true;
    default: return a.stage === st.s;
  }
}
const hay = a => [a.name, a.domain, a.ind, a.uc, a.ev, a.buyer, VL[a.vert], a.status, a.hold, a.note, LL[a.list], a.also, a.row, a.cc, a.vend, a.trig, a.angle, a.missing, a.sigv].join(" ").toLowerCase();
function sval(a, k){
  switch (k){
    case "company": return (a.name || "").toLowerCase();
    case "list": return LL[a.list] || "";
    case "priority": return PORD[a.pr] ?? 9;
    case "status": return SORD[a.stage] ?? 9;
    case "vertical": return VL[a.vert] || "~";
    case "sms": return a.sms === "Yes" ? 0 : a.sms === "Signal" ? 1 : a.sms === "Unverified" ? 2 : 3;
    case "useCase": return (a.uc || "~").toLowerCase();
    case "evidence": return (a.ev || "~").toLowerCase();
    case "opp": return -(a.opp || 0);
    case "stack": return (a.cc || a.vend || "~").toLowerCase();
  }
}
function compute(){
  const n = st.q.trim().toLowerCase(), out = [];
  for (const a of A){
    if (!inList(a) || !matchS(a)) continue;
    if (st.v && (a.vert || "GENERAL") !== st.v) continue;
    if (st.m === "YES" && a.sms !== "Yes") continue;
    if (st.m === "NO" && a.sms === "Yes") continue;
    if (n && !hay(a).includes(n)) continue;
    if (st.t && a.tw !== st.t) continue;
    if (st.r && (st.r === "BLOCKED" ? !String(a.rs || "").startsWith("Blocked") : a.rs !== st.r)) continue;
    if (st.o && !((a.opp || 0) >= +st.o)) continue;
    if (st.c && a.chan !== st.c) continue;
    if (st.g && !a.trig) continue;
    if (st.p && !(st.p === "Y" ? a.npl > 0 : a.dmc > 0)) continue;
    if (st.a && !(a.aic && (st.a === "ANY" || a.aic.strength === st.a))) continue;
    const has = (f, v) => String(a[f] || "").split(/[;,]/).map(x => x.trim()).includes(v);
    if (st.k && !has("cc", st.k)) continue;
    if (st.x && !has("vend", st.x)) continue;
    if (st.u && !has("uc", st.u)) continue;
    if (st.sig && !(a.sids || []).includes(st.sig)) continue;
    out.push(a);
  }
  if (st.sort) out.sort((a, b) => { const x = sval(a, st.sort), y = sval(b, st.sort); return (x < y ? -1 : x > y ? 1 : 0) * st.dir; });
  return out;
}

/* evidence audit (qualified accounts), as in the original dashboards */
const EAL = {PASS: "EVIDENCE PASS", FAIL: "EVIDENCE FAIL", "NEEDS REVIEW": "EVIDENCE NEEDS REVIEW"};
const eaPill = a => (a.ea && (isQ(a) || a.stage === "HOLD")) ? `<br><span class="ea ea-${a.ea.s === "NEEDS REVIEW" ? "REVIEW" : esc(a.ea.s)}" title="Evidence audit of this qualified account">${esc(EAL[a.ea.s] || a.ea.s)}</span>` : "";
function eaRows(a){ const e = a.ea; if (!e || !(isQ(a) || a.stage === "HOLD")) return isQ(a) ? [["Evidence audit", "Pending — runs when the account is (re)qualified"]] : [];
  return [["Evidence audit", esc(EAL[e.s] || e.s)], ["Audit findings", esc(e.r) || "All checks passed"], ["Exact quote", e.q ? `<span class="eaq">“${esc(e.q)}”</span>` : "—", "wide"],
    ["Quote verified on", esc(e.w) || "—"], ["Cited page", /^https?:/.test(e.u || "") ? `<a href="${esc(e.u)}" target="_blank" rel="noopener">${esc(e.u)}</a>` : "—", "wide"]]; }

/* rendering */
function rowHtml(a){
  const open = st.open.has(a.k);
  const sub = `<span class="sub">row ${esc(a.row)}${a.domain ? " · " + esc(a.domain) : ""}${a.npl ? ` · ${a.npl} decision-maker${a.npl === 1 ? "" : "s"}` : ""}</span>`;
  const lists = `<span class="lb-list">${esc(LL[a.list] || a.src)}</span>` + (a.also ? a.also.split(",").map(l => `<span class="lb-list" style="opacity:.6" title="Also on the ${esc(LL[l])} list">+${esc(LL[l])}</span>`).join("") : "");
  const pr = a.stage === "MERGED" ? "MERGED" : a.stage === "PENDING" ? "PENDING" : a.pr || (a.stage === "PENDING_WEBSITE" ? "PENDING_WEBSITE" : a.stage === "RETRY" ? "RETRY" : "REVIEW");
  const prl = {PENDING:"Queued", PENDING_WEBSITE:"No website", MERGED:"Merged", RETRY:"Retry"}[pr] || pr;
  const sms = a.sms === "Yes" ? '<span class="pill p-YES">Yes</span>' : a.sms === "Signal" ? '<span class="pill p-SIG" title="some evidence, rule not met">Partial</span>' : a.sms === "Unverified" ? '<span class="pill p-UNV">Unverified</span>' : dash;
  const why = a.stage === "QUALIFIED" ? a.hold : (a.stage === "RETRY" || a.stage === "PENDING_WEBSITE" || a.stage === "MERGED") ? a.note : "";
  return `<tr class="r" tabindex="0" data-k="${esc(a.k)}" aria-expanded="${open}"><td class="co">${esc(a.name)}${a.ov ? ' <span class="lb-list" title="verdict edited by a person">edited</span>' : ""}${sub}</td>
    <td class="ls">${lists}</td>
    <td><span class="pill p-${esc(pr)}">${esc(prl)}</span></td>
    <td class="sv">${sms}</td>
    <td class="uc">${esc(a.uc) || dash}</td>
    <td class="vt">${esc(VL[a.vert] || a.vert || "") || dash}</td>
    <td class="sk">${a.cc ? `<b style="color:var(--ink-2)">${esc(a.cc)}</b>` : (a.cci ? `<span title="mentions (not proof of use)">${esc(a.cci)}</span>` : "")}${a.vend ? `<br>${esc(a.vend)}` : ""}${(a.chan || "").startsWith("CHANNEL") ? '<br><span class="lb-list">channel / partner</span>' : ""}${!a.cc && !a.cci && !a.vend && !(a.chan || "").startsWith("CHANNEL") ? dash : ""}</td>
    <td class="op" title="${esc(a.oppx || "")}">${a.opp != null ? fmt(a.opp) : dash}${a.opp != null ? `<div class="bar"><i style="width:${Math.max(0, Math.min(100, a.opp))}%"></i></div>` : ""}</td>
    <td class="ev"><span>${esc(a.ev) || dash}</span>${/^https?:\/\//.test(a.url || "") ? `<a class="src" href="${esc(a.url)}" target="_blank" rel="noopener" title="${esc(a.url)}">${esc(a.url.replace(/^https?:\/\/(www\.)?/, ""))}</a>` : ""}</td>
    <td class="st"><span class="pill p-${esc(a.stage)}" style="font-size:.66rem">${esc(SHORT[a.stage] || a.stage)}</span>${why ? `<span class="why">${esc(why)}</span>` : ""}${eaPill(a)}</td></tr>` + (open ? detail(a) : "");
}
const link = u => /^https?:\/\//.test(u || "") ? `<a href="${esc(u)}" target="_blank" rel="noopener">${esc(u)}</a>` : (esc(u) || "—");
function detail(a){
  const d = DET[a.k];
  const base = [
    ["Stage", esc(SHORT[a.stage] || a.stage)],
    ["Outreach check", a.stage === "READY" ? `Passed: ${esc(LBL.core.toLowerCase())}, evidence on own site, audit PASS, not flagged, deduplicated` : esc(a.hold || a.note) || "—", "wide"],
    ["Source", `${esc(LL[a.list] || a.src)} · source row ${esc(a.row)}`],
    ["Also on lists", esc((a.also || "").split(",").filter(Boolean).map(l => LL[l]).join(", ")) || "—"],
    ["Website", a.domain ? `<a href="https://${esc(a.domain)}" target="_blank" rel="noopener">${esc(a.domain)}</a>` : "None known"],
    ["Industry (list)", esc(a.ind) || "—"],
    ["Size (list)", [a.emp ? fmt(Math.round(a.emp)) + " employees" : "", a.rev ? "$" + fmt(Math.round(a.rev)) + " revenue" : "", a.loc].filter(Boolean).map(esc).join(" · ") || "unknown (never counted as a match)"],
  ];
  if (a.relation) base.push(["Entity check", esc(a.relation)]);
  base.push(...eaRows(a));
  base.push(["Research status", esc(a.rs) || "—"], ["Signals verified", esc(a.sigv) || "—"], ["Signals inferred (not verified)", esc(a.sigi) || "—"],
    ["Missing evidence", esc(a.missing) || "—", "wide"],
    ["Fit score", a.opp != null ? `${fmt(a.opp)} / 100 — ${esc(a.oppx) || "no verified signals yet"}` : "—", "wide"],
    ["Technologies (verified in use)", esc(a.cc) || "—"], ["Technologies mentioned (not proof of use)", esc(a.cci) || "—"],
    ["Competitors (verified in use)", esc(a.vend) || "—"], ["Channel vs direct", esc(a.chan) || "—"],
    ["Buying triggers (verified)", esc(a.trig) || "—"], ["Scale", esc(a.scale) || "—"],
    ["Recommended angle", esc(a.angle) || "—", "wide"], ["Buyer persona", esc(a.persona) || "—"], ["Buying committee", esc(a.buyer) || "—"]);
  if (a.tw) base.push(["Target technology", esc(a.tw)]);
  if (a.aic) base.push([`AI candidate (${esc(a.aic.strength)}) — UNVERIFIED, never changes the verdict`, `<span class="eaq">“${esc(a.aic.quote)}”</span> ${link(a.aic.url)}<br><span class="faint small">${esc(a.aic.signal)} · ${esc(a.aic.model)} · ${esc(a.aic.reason || "")}</span>`, "wide"]);
  let more = [];
  if (!d) more = [["Full research record", '<span class="loading">Loading from the workspace database…</span>', "wide"]];
  else if (d.error) more = [["Full research record", esc(d.error), "wide"]];
  else {
    const r = d.research || {}, v = d.verdict || {}, acc = d.account || {};
    const lg = (() => { try { return JSON.parse(r.log || "{}"); } catch (e) { return {}; } })();
    more = [["Research status", esc(v.status) || "—", "wide"],
      ["Full evidence", esc(v.evidence) || "—", "wide"], ["Evidence URL", link(v.url), "wide"], ["Evidence confidence", esc(v.confidence) || "—"],
      ["Qualification reason", esc(v.qual_reason) || "—", "wide"], ["Review reason", esc(v.review_reason) || "—", "wide"],
      ["Research checks", `${esc(r.pages_checked ?? "—")} own-site pages · ${esc(r.searches_used ?? "—")} searches · search ${esc(r.search_state || "not run")} · attempts ${esc(r.attempts ?? 0)} · researched ${esc(r.researched_at || "—")} · profile v${esc(r.profile_version ?? "—")}`, "wide"],
      ["Entity / parent check", esc(acc.merge_notes) || "—", "wide"]];
    more.push(["Decision-makers", d.contacts && d.contacts.length ? `<ul class="evl">${d.contacts.map(c => `<li><b>${esc(c.name || "General inbox")}</b>${c.title ? " · " + esc(c.title) : ""}${c.committee ? ` <span class="sg sg-VERIFIED">${esc(c.committee)}</span>` : ""}<br>${c.email ? `<span class="q">${esc(c.email)}</span> ` : ""}${c.phone ? esc(c.phone) + " " : ""}${link(c.source_url)}<br><span class="m">${esc(c.status)} · ${esc(c.source)} · ${esc(c.confidence)}</span></li>`).join("")}</ul>`
      : esc((d.research || {}).contacts_note || (["A","B","C","HOLD"].includes(a.pr) ? "None found on the company's own site" : "Searched for qualified accounts only")), "wide"]);
    if (d.parent) more.push(["Parent company", `${esc(d.parent.name)} ${d.parent.domain ? "(" + esc(d.parent.domain) + ")" : ""}`]);
    if (lg.note) more.push(["Research note", esc(lg.note), "wide"]);
    if (lg.search && lg.search.length) more.push(["Searches", `<ul class="evl">${lg.search.map(s => `<li><span class="m">${esc(s.q)}</span><br>${s.error ? '<span class="err">' + esc(s.error) + "</span>" : `${esc(s.results)} results · ${esc((s.candidates || []).length)} on the company's own site`}</li>`).join("")}</ul>`, "wide"]);
    if (lg.pages && lg.pages.length) more.push(["Pages checked", `<ul class="evl">${lg.pages.slice(0, 20).map(p => `<li>${link(p.url)} <span class="m">${esc(p.via)} · ${p.status || "—"} ${esc(p.error || "")}</span></li>`).join("")}</ul>`, "wide"]);
    if (d.discovery && d.discovery.found_at) more.push(["Website discovery", `${esc(d.discovery.domain || "none")} — ${esc(d.discovery.verified)} (${esc(d.discovery.found_at)})`, "wide"]);
    if (d.history && d.history.length) more.push(["Verdict history", `<ul class="evl">${d.history.map(h => `<li>${esc(h.changed_at)} · ${esc(h.change)}: ${esc(h.old_priority || "—")} → ${esc(h.new_priority || "—")}<br><span class="m">${esc(h.note)}</span></li>`).join("")}</ul>`, "wide"]);
    if (d.evidence && d.evidence.length) more.push(["Evidence records (status · signal · quote · source · reason)", `<ul class="evl">${d.evidence.map(e => `<li><span class="sg sg-${esc(e.status)}">${esc(e.status)}</span><b>${esc(e.label)}</b> <span class="m">${esc(e.kind)} · confidence ${esc(e.confidence)}${e.marker ? " · proof marker" : ""}</span><br><span class="q">“${esc((e.snippet || "").slice(0, 400))}”</span><br>${link(e.url)} <span class="m">${esc(e.reason)}</span></li>`).join("")}</ul>`, "wide"]);
  }
  const edit = ["Edit verdict", `<div class="edit" data-k="${esc(a.k)}"><select aria-label="Override priority"><option value="">Engine verdict${a.ov ? " (clear override)" : ""}</option>${["A","B","C","HOLD","REVIEW","DQ"].map(p => `<option value="${p}"${a.ov && a.ov.priority === p ? " selected" : ""}>${p}</option>`).join("")}</select><input type="text" maxlength="300" placeholder="Why (kept in the history)" value="${esc(a.ov ? a.ov.note : "")}"><button class="btn" type="button" data-act="ov">Save</button><button class="link" type="button" data-act="weak">${(a.hold || "").includes("flagged weak") ? "Clear weak-evidence flag" : "Flag evidence as weak"}</button></div>`, "wide"];
  const f = [...base, ...more, edit];
  return `<tr class="d"><td colspan="${COLS.length}"><dl class="dl">${f.map(([t, v, w]) => `<div class="${w || ""}"><dt>${esc(t)}</dt><dd>${v}</dd></div>`).join("")}</dl></td></tr>`;
}
function render(){
  view = compute();
  const vlabel = (st.l ? LL[st.l] + " · " : "All lists · ") + (st.v ? VL[st.v] : "All segments");
  const extra = [st.m === "YES" ? LBL.core + " only" : st.m === "NO" ? "Not verified" : "", st.q.trim() ? `Matching “${st.q.trim()}”` : "",
    st.t, st.r, st.o ? "Fit score " + st.o + "+" : "", st.c, st.g ? "Verified buying trigger" : "", st.sig ? "Signal: " + (((S.profiles[String(S.default_profile)] || {}).signals || []).find(g => g.id === st.sig) || {label: st.sig}).label + " · ranked by fit score" : "", st.a ? "AI candidate " + st.a.toLowerCase() : "", st.k, st.x, st.u].filter(Boolean).map(esc);
  $("ttl").innerHTML = `${esc(vlabel)} — ${fmt(view.length)} ${esc(TITLE[st.s])} ${view.length === 1 ? "Record" : "Records"}` + (extra.length ? `<small>${extra.join(" · ")}</small>` : "");
  const exp = $("exp"); exp.textContent = `Export ${fmt(view.length)} CSV`; exp.disabled = !view.length; $("expx").disabled = !view.length;
  const nonDefault = (st.s !== "Q") + (!!st.v) + (!!st.m) + (!!st.l) + ["t","r","o","c","g","k","x","u","a","p"].filter(k => st[k]).length;
  $("fBadge").hidden = !nonDefault; $("fBadge").textContent = nonDefault;
  document.querySelectorAll(".kcard").forEach(c => c.setAttribute("aria-pressed", !st.v && c.dataset.s === st.s));
  document.querySelectorAll(".vcard").forEach(c => c.setAttribute("aria-pressed", c.dataset.v === st.v));
  document.querySelectorAll(".lcard").forEach(c => c.setAttribute("aria-pressed", c.dataset.l === st.l));
  $("lpick").value = st.l || "";
  document.querySelectorAll("th[data-k]").forEach(th => { const on = th.dataset.k === st.sort;
    on ? th.setAttribute("aria-sort", st.dir > 0 ? "ascending" : "descending") : th.removeAttribute("aria-sort");
    th.querySelector(".ar").textContent = on ? (st.dir > 0 ? "↑" : "↓") : ""; });
  const slice = view.slice(0, st.shown);
  const empty = A.length ? "No accounts match. Clear the search or open Filters to widen the view." : `No accounts yet. <a href="${$("importBtn").getAttribute("href")}"${$("importBtn").target ? ' target="_blank" rel="noopener"' : ""}>Import a CSV or Excel file</a> and click Start research.`;
  $("tb").innerHTML = slice.length ? slice.map(rowHtml).join("") : `<tr><td colspan="${COLS.length}" class="empty">${empty}</td></tr>`;
  $("moreBox").hidden = view.length <= PAGE;
  $("shown").textContent = `Showing ${fmt(slice.length)} of ${fmt(view.length)}`;
  $("more").hidden = st.shown >= view.length;
}
function setView(s, v){ st.s = s; st.v = v; st.shown = PAGE; st.open.clear(); $("toast").textContent = ""; render(); }

/* events (same interactions as the original, plus the list switch and verdict editing) */
$("lists").addEventListener("click", e => { const b = e.target.closest(".lcard"); if (!b || e.target.closest("a")) return; st.l = b.dataset.l; st.shown = PAGE; st.open.clear(); counts(); render(); });
$("kpis").addEventListener("click", e => { const b = e.target.closest(".kcard"); if (b) setView(b.dataset.s, ""); });
$("verts").addEventListener("click", e => { const b = e.target.closest(".vcard"); if (!b) return; st.v === b.dataset.v && st.s === "Q" ? setView("Q", "") : setView("Q", b.dataset.v); });
$("q").addEventListener("input", e => { st.q = e.target.value; st.shown = PAGE; render(); });
$("more").onclick = () => { st.shown += PAGE; render(); };
$("thead").addEventListener("click", e => { const th = e.target.closest("th[data-k]"); if (!th) return; const k = th.dataset.k;
  if (st.sort === k && st.dir < 0){ st.sort = ""; st.dir = 1; } else { st.dir = st.sort === k ? -1 : 1; st.sort = k; } render(); });
let downAt = null, toggleTimer = 0;
async function toggleRow(k){
  if (st.open.has(k)) { st.open.delete(k); return render(); }
  st.open.add(k); render();
  if (!DET[k]) { try { DET[k] = await api("/api/account?k=" + encodeURIComponent(k)); } catch (e) { DET[k] = {error: "Could not load: " + e.message}; } render(); }
}
$("tb").addEventListener("mousedown", e => { downAt = {x: e.clientX, y: e.clientY}; });
$("tb").addEventListener("click", async e => {
  const act = e.target.closest("[data-act]");
  if (act) {
    const box = act.closest(".edit"), k = box.dataset.k;
    try {
      if (act.dataset.act === "ov") await api("/api/account/override", {method: "POST", body: {k, priority: box.querySelector("select").value, note: box.querySelector("input").value}});
      else await api("/api/account/weak", {method: "POST", body: {k, on: !act.textContent.startsWith("Clear"), note: box.querySelector("input").value}});
      $("toast").textContent = "Saved. The verdict history records who changed what."; delete DET[k]; lastGen = ""; await load();
    } catch (err) { $("toast").textContent = "Not saved: " + err.message; }
    return;
  }
  if (e.target.closest("a") || e.target.closest(".edit")) return;
  const tr = e.target.closest("tr.r"); if (!tr) return; const k = tr.dataset.k;
  if (e.detail === 0) return toggleRow(k);
  clearTimeout(toggleTimer); if (e.detail > 1) return;
  const moved = downAt && Math.hypot(e.clientX - downAt.x, e.clientY - downAt.y) > 4;
  if (moved || String(window.getSelection() || "").trim()) return;
  toggleTimer = setTimeout(() => { if (!String(window.getSelection() || "").trim()) toggleRow(k); }, 220);
});
$("tb").addEventListener("keydown", e => { if ((e.key === "Enter" || e.key === " ") && e.target.matches("tr.r")){ e.preventDefault(); e.target.click(); } });
const pop = $("pop"), fBtn = $("fBtn");
function openPop(on){ pop.hidden = !on; fBtn.setAttribute("aria-expanded", on);
  if (on){ for (const id of ["t","r","o","c","g","k","x","u","a","p"]){ const el = document.querySelector(`input[name="f${id}"][value="${CSS.escape(st[id])}"]`); if (el) el.checked = true; }
    const ck = id => { const el = $(id); if (el) el.checked = true; };
    ck("fl-" + (st.l || "ALL")); ck("fs-" + st.s); ck("fv-" + (st.v || "ALL")); ck("fm-" + (st.m || "ALL")); } }
fBtn.onclick = () => openPop(pop.hidden);
$("fDone").onclick = () => { openPop(false); fBtn.focus(); };
$("fReset").onclick = () => { st.sig = ""; st.m = ""; st.l = ""; for (const id of ["t","r","o","c","g","k","x","u","a","p"]) st[id] = ""; counts(); setView("Q", ""); openPop(true); };
pop.addEventListener("change", e => {
  if (e.target.name === "fl"){ st.l = e.target.value; $("lpick").value = st.l; counts(); setView(st.s, st.v); }
  if (e.target.name === "fs") setView(e.target.value, st.v);
  if (e.target.name === "fv") setView(st.s, e.target.value);
  if (e.target.name === "fm"){ st.m = e.target.value; setView(st.s, st.v); }
  const xf = /^f([trocgkxuap])$/.exec(e.target.name); if (xf){ st[xf[1]] = e.target.value; setView(st.s, st.v); }
});
document.addEventListener("click", e => { if (!pop.hidden && !e.target.closest(".fwrap")) openPop(false); });
document.addEventListener("keydown", e => { if (e.key === "Escape" && !pop.hidden){ openPop(false); fBtn.focus(); } });
const defs = $("defs");
$("defsBtn").onclick = () => defs.showModal(); $("defsClose").onclick = () => defs.close();
defs.addEventListener("click", e => { if (e.target === defs) defs.close(); });

/* export: exactly the records in the current filtered view, with the profile's export columns */
async function exportView(format){
  const rows = view.slice(); if (!rows.length) return;
  const slug = [st.l ? LL[st.l] : "all_lists", st.v, TITLE[st.s] || "all"].filter(Boolean).join("_").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
  try {
    const blob = await api("/api/export/view", {method: "POST", body: {keys: rows.map(a => a.k), format}});
    download(blob, `${(S.workspace || "icp").toLowerCase().replace(/[^a-z0-9]+/g, "_")}_master_${slug}.${format}`);
    $("toast").textContent = `Exported ${fmt(rows.length)} records. Note: the evidence column holds the first 260 characters; the full text is in the row detail.`;
  } catch (e) { $("toast").textContent = "Export failed: " + e.message; }
}
$("exp").onclick = () => exportView("csv");
$("expx").onclick = () => exportView("xlsx");

/* live data: summary every 30 s, the full account list whenever the server recomputes */
let lastGen = "", lastProfile = null;
async function load(){
  try {
    S = await api("/api/summary.json");
    if (S.generated !== lastGen){
      A = await api("/api/accounts.json"); lastGen = S.generated; DET = {};
      if (S.default_profile && S.default_profile !== lastProfile) { lastProfile = S.default_profile; try { RULES = (await api("/api/profiles/" + S.default_profile)).rules; } catch (e) { RULES = null; } }
      scaffold(); dynOpts(); counts(); render();
    }
    else health();
  } catch (e) { $("health").innerHTML = `<span><span class="dot bad"></span>Cannot reach the ICP Qualifier service: ${esc(e.message || e)}</span>`; }
}
$("lpick").addEventListener("change", e => { st.l = e.target.value; st.shown = PAGE; st.open.clear(); const r = $("fl-" + (st.l || "ALL")); if (r) r.checked = true; scaffold(); counts(); render(); });
loadMe().then(() => { nav("/"); load(); setInterval(load, 30000); });
