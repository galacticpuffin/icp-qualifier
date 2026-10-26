/* ICP wizard: one question at a time; conditional follow-ups; suggestion chips from the chosen market pack; answers are
   kept in this browser until the profile is saved. The server turns the answers into the profile (POST /api/wizard/build). */
let W = null, A = {}, idx = 0, PACK = null, KEY = "icpq-wizard";
const slug = s => String(s || "").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "").slice(0, 40) || "signal";
const save = () => { try { localStorage.setItem(KEY, JSON.stringify({A, idx})); } catch (e) { /* private mode: answers live for this page only */ } };
const packOf = () => W.packs.find(p => p.id === (A.pack || "generic")) || W.packs[W.packs.length - 1];
const mandatoryCount = () => (A.signals || []).filter(s => s.requirement === "mandatory").length;

function visible(q){
  const w = q.when; if (!w) return true;
  if (w.nonempty) return (A[w.nonempty] || []).length > 0;
  if (w.eq) return A[w.eq[0]] === w.eq[1];
  if (w.min_mandatory) return mandatoryCount() >= w.min_mandatory;
  return true;
}
const steps = () => W.questions.filter(visible).concat([{id: "review", n: 16, title: "Review", kind: "review"}]);

function tagInput(key, sugg){
  const box = document.createElement("div"); box.className = "tagbox"; box.style.cssText = "display:flex;flex-direction:column;gap:8px";
  const draw = () => {
    const vals = A[key] || [];
    box.innerHTML = `<div class="chips">${vals.map((v, i) => `<span class="tagx">${esc(v)}<button type="button" aria-label="Remove ${esc(v)}" data-i="${i}">×</button></span>`).join("")}</div>
      <input class="in" type="text" placeholder="Type and press Enter (comma separates several)" aria-label="Add">
      ${sugg && sugg.length ? `<div class="chips">${sugg.filter(s => !vals.includes(s)).slice(0, 16).map(s => `<button class="chip add" type="button" data-add="${esc(s)}">+ ${esc(s)}</button>`).join("")}</div>` : ""}`;
    const inp = box.querySelector("input");
    inp.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === ",") { e.preventDefault(); add(inp.value); } });
    inp.addEventListener("blur", () => { if (inp.value.trim()) add(inp.value); });
    box.querySelectorAll("[data-i]").forEach(b => b.onclick = () => { A[key].splice(+b.dataset.i, 1); save(); draw(); });
    box.querySelectorAll("[data-add]").forEach(b => b.onclick = () => add(b.dataset.add));
  };
  const add = v => { const parts = String(v).split(",").map(x => x.trim()).filter(Boolean); if (!parts.length) return; A[key] = [...new Set([...(A[key] || []), ...parts])]; save(); draw(); box.querySelector("input").focus(); };
  draw(); return box;
}
function choice(key, choices, onPick){
  const d = document.createElement("div"); d.className = "chips";
  d.innerHTML = choices.map(([v, l]) => `<button class="chip" type="button" data-v="${esc(v)}" aria-pressed="${A[key] === v}">${esc(l)}</button>`).join("");
  d.querySelectorAll("button").forEach(b => b.onclick = () => { A[key] = b.dataset.v; save(); d.querySelectorAll("button").forEach(x => x.setAttribute("aria-pressed", x === b)); onPick && onPick(b.dataset.v); });
  return d;
}
function field(k, label, ph, long){
  const l = document.createElement("label"); l.className = "f";
  l.innerHTML = `${esc(label)}${long ? `<textarea class="in" placeholder="${esc(ph || "")}"></textarea>` : `<input class="in" type="text" placeholder="${esc(ph || "")}">`}`;
  const i = l.querySelector("input,textarea"); i.value = A[k] ?? ""; i.oninput = () => { A[k] = i.value; save(); };
  return l;
}
function signalCards(category){
  const P = packOf();
  let sugg = category === "problem" ? P.signals.filter(s => s.category === "problem") : category === "buying" ? P.buying : P.signals.filter(s => s.category !== "problem");
  const wrap = document.createElement("div"); wrap.style.cssText = "display:flex;flex-direction:column;gap:10px";
  const draw = () => {
    const chosen = A.signals || [];
    const mine = chosen.filter(s => (category === "any" ? !["problem", "buying"].includes(s.category) && !sugg.some(x => x.id === s.id) : s.category === category && !sugg.some(x => x.id === s.id)));
    wrap.innerHTML = (sugg.length ? `<div class="faint small">Suggestions for ${esc(P.label)}. Tap to add or remove.</div>` : "") +
      sugg.map(s => { const on = chosen.some(c => c.id === s.id); return `<button class="sig chip" style="all:unset;box-sizing:border-box;cursor:pointer" type="button" data-id="${esc(s.id)}" aria-pressed="${on}">
        <div class="sig" style="${on ? "border-color:var(--accent-line);background:var(--accent-soft)" : ""}"><div class="hd"><b>${on ? "✓ " : "+ "}${esc(s.label)}</b><span class="faint small">${esc(s.category)}</span></div>
        <div class="pats">looks for: ${s.patterns.slice(0, 5).map(p => esc(p.replace(/^re:/, "pattern "))).join(" · ")}</div></div></button>`; }).join("") +
      mine.map(s => `<div class="sig"><div class="hd"><b>${esc(s.label)}</b><button class="link" type="button" data-del="${esc(s.id)}">Remove</button></div><div class="pats">looks for: ${s.patterns.map(esc).join(" · ")}</div></div>`).join("") +
      `<div class="sig"><b class="small">Add your own</b><div class="grid2"><label class="f">What is it?<input class="in" id="nl" placeholder=""></label>
        <label class="f">Words their website would show (comma separated)<input class="in" id="np" placeholder=""></label></div>
        ${category === "any" ? `<label class="f">Kind of signal<select class="in" id="nc">${W.categories.filter(c => !["problem", "buying"].includes(c)).map(c => `<option>${c}</option>`).join("")}</select></label>` : ""}
        <div class="row"><button class="btn" type="button" id="nadd">Add signal</button><button class="link" type="button" id="aisug">Suggest with AI</button><span class="small faint" id="aimsg"></span></div></div>`;
    wrap.querySelectorAll("[data-id]").forEach(b => b.onclick = () => { const s = sugg.find(x => x.id === b.dataset.id); const i = chosen.findIndex(c => c.id === s.id);
      if (i >= 0) chosen.splice(i, 1); else chosen.push(JSON.parse(JSON.stringify(s))); A.signals = chosen; save(); draw(); });
    wrap.querySelectorAll("[data-del]").forEach(b => b.onclick = () => { A.signals = chosen.filter(c => c.id !== b.dataset.del); save(); draw(); });
    wrap.querySelector("#nadd").onclick = () => {
      const label = wrap.querySelector("#nl").value.trim(); if (!label) return wrap.querySelector("#nl").focus();
      const pats = wrap.querySelector("#np").value.split(",").map(x => x.trim()).filter(Boolean);
      const cat = category === "any" ? wrap.querySelector("#nc").value : category;
      let id = slug(label); while (chosen.some(c => c.id === id)) id += "_2";
      chosen.push({id, label, category: cat, patterns: pats.length ? pats : [label], markers: [], requirement: category === "buying" ? "preferred" : "preferred", weight: 10, use_case: label});
      A.signals = chosen; save(); draw();
    };
    wrap.querySelector("#aisug").onclick = async () => {
      const m = wrap.querySelector("#aimsg"); m.textContent = "Asking the AI provider…";
      try { const r = await api("/api/wizard/ai-suggest", {method: "POST", body: {answers: A}});
        r.signals.filter(s => category === "any" ? !["problem", "buying"].includes(s.category) : s.category === category).forEach(s => { s.id = slug(s.label); if (!sugg.some(x => x.id === s.id)) sugg = sugg.concat([s]); });
        m.textContent = r.signals.length ? "Suggestions added above: review each one." : "No suggestions."; draw();
      } catch (e) { m.textContent = e.message; }
    };
  };
  draw(); return wrap;
}
function rolesEditor(){
  const d = document.createElement("div"); d.style.cssText = "display:flex;flex-direction:column;gap:8px";
  const draw = () => {
    const sigs = A.signals || [];
    if (!sigs.length) { d.innerHTML = '<p class="err">No signals yet. Go back and add at least one signal the engine should look for.</p>'; return; }
    d.innerHTML = (mandatoryCount() ? "" : '<p class="small" style="color:var(--rev)">Pick at least one <b>Must have</b>: an account can only qualify on verified evidence of it.</p>') +
      sigs.map((s, i) => `<div class="sig"><div class="hd"><b>${esc(s.label)}</b><div class="seg" role="group" aria-label="Role of ${esc(s.label)}">${[["mandatory","Must have"],["preferred","Nice to have"],["negative","Counts against"],["info","Just record"]].map(([v, l]) => `<button type="button" data-i="${i}" data-v="${v}" aria-pressed="${s.requirement === v}">${l}</button>`).join("")}</div></div>
        <div class="row small faint">weight <input class="in" style="width:80px;padding:4px 8px" type="number" min="0" max="100" value="${s.weight ?? 10}" data-w="${i}" aria-label="Weight of ${esc(s.label)}"> · ${esc(s.category)} · id <code>${esc(s.id)}</code></div></div>`).join("");
    d.querySelectorAll("[data-v]").forEach(b => b.onclick = () => { sigs[+b.dataset.i].requirement = b.dataset.v; save(); draw(); });
    d.querySelectorAll("[data-w]").forEach(i => i.onchange = () => { sigs[+i.dataset.w].weight = Math.max(0, Math.min(100, +i.value || 0)); save(); });
  };
  draw(); return d;
}
async function preview(){
  const r = await api("/api/wizard/build", {method: "POST", body: {answers: A}});
  return r;
}

async function show(){
  const S = steps(); idx = Math.max(0, Math.min(idx, S.length - 1)); const q = S[idx]; save();
  $("wstep").textContent = `${idx + 1} / ${S.length}`; $("wbar").style.width = (100 * (idx + 1) / S.length) + "%"; $("wtopic").textContent = q.title;
  $("qprompt").textContent = q.prompt || "Here is what your engine will do"; $("qhelp").textContent = q.help || "";
  const B = $("qbody"); B.innerHTML = ""; $("back").disabled = idx === 0; $("skip").classList.toggle("hidden", q.kind === "review"); $("next").textContent = q.kind === "review" ? "Save profile" : "Next";
  const P = packOf();
  const sug = k => k === "industries" ? P.industries : k === "technologies" ? P.technologies : k === "titles" ? P.titles : k === "departments" ? P.departments : [];
  switch (q.kind){
    case "fields": q.fields.forEach(f => B.appendChild(field(f.k, f.label, f.ph, f.long))); break;
    case "longtext": B.appendChild(field(q.k, "", "", true)); break;
    case "pack": {
      B.appendChild(choice("pack", W.packs.map(p => [p.id, p.label]), () => show()));
      B.appendChild(field("market_text", "In your own words (optional)", ""));
      const n = document.createElement("p"); n.className = "small faint"; n.textContent = A.pack && A.pack !== "generic" ? `Optional suggestions from “${P.label}” will appear as chips you can click.` : "Optional: pick a market to get suggestion chips, or skip and type your own."; B.appendChild(n); break; }
    case "tags": B.appendChild(tagInput(q.k, sug(q.suggest))); break;
    case "tags2": q.fields.forEach(f => { const h = document.createElement("div"); h.className = "small muted"; h.textContent = f.label; B.appendChild(h); B.appendChild(tagInput(f.k, sug(f.suggest))); }); break;
    case "ranges": {
      const presets = [["SMB (1–50)", 1, 50], ["Mid-market (51–1,000)", 51, 1000], ["Enterprise (1,000+)", 1000, ""], ["Any size", "", ""]];
      const c = document.createElement("div"); c.className = "chips"; c.innerHTML = presets.map(([l, a, b], i) => `<button class="chip add" type="button" data-p="${i}">${l}</button>`).join("");
      c.querySelectorAll("button").forEach(b => b.onclick = () => { const [, a, z] = presets[+b.dataset.p]; A.employees_min = a; A.employees_max = z; show(); });
      B.appendChild(c); const g = document.createElement("div"); g.className = "grid2"; q.fields.forEach(f => g.appendChild(field(f.k, f.label, f.ph))); B.appendChild(g); break; }
    case "choice": B.appendChild(choice(q.k, q.choices)); break;
    case "signals": B.appendChild(signalCards(q.category)); break;
    case "disq": {
      const d = document.createElement("div"); d.className = "chips"; const cur = new Set(A.disqualifiers || []);
      d.innerHTML = W.disqualifiers.map(x => `<button class="chip" type="button" data-d="${x.id}" aria-pressed="${cur.has(x.id)}">${esc(x.label)}</button>`).join("");
      d.querySelectorAll("button").forEach(b => b.onclick = () => { cur.has(b.dataset.d) ? cur.delete(b.dataset.d) : cur.add(b.dataset.d); A.disqualifiers = [...cur]; save(); b.setAttribute("aria-pressed", cur.has(b.dataset.d)); });
      B.appendChild(d);
      const h = document.createElement("div"); h.className = "small muted"; h.textContent = "Disqualify when the company's own website says… (optional)"; B.appendChild(h); B.appendChild(tagInput("custom_disqualifiers", []));
      if ((A.disqualifiers || []).includes("competitor") && !(A.competitors || []).length) { const w = document.createElement("p"); w.className = "small"; w.style.color = "var(--rev)"; w.textContent = "Add competitor names in step 5 for the competitor rule to work."; B.appendChild(w); }
      break; }
    case "roles": B.appendChild(rolesEditor()); break;
    case "expression": {
      B.appendChild(field("gate_expression", "Rule", ""));
      const h = document.createElement("p"); h.className = "small faint"; h.innerHTML = "Signal names: " + (A.signals || []).map(s => `<code>${esc(s.id)}</code>`).join(", "); B.appendChild(h); break; }
    case "priority": {
      B.appendChild(choice("priority_mode", [["size", "By company size (A = large, B = meaningful, C = rest)"], ["score", "By fit score"], ["signals", "By key signals"]], () => show()));
      const pm = A.priority_mode || "size";
      if (pm === "score") { const g = document.createElement("div"); g.className = "grid2"; g.appendChild(field("a_min_score", "A needs a fit score of at least", "70")); g.appendChild(field("b_min_score", "B needs at least", "45")); B.appendChild(g); }
      if (pm === "size") { const g = document.createElement("div"); g.className = "grid2"; [["large_employees", "“Large” = employees from", "1001"], ["large_revenue", "or revenue from ($)", "500000000"], ["meaningful_employees", "“Meaningful” = employees from", "201"], ["meaningful_revenue", "or revenue from ($)", "50000000"]].forEach(([k, l, p]) => g.appendChild(field(k, l, p))); B.appendChild(g); }
      const sigs = A.signals || [];
      if (sigs.length && pm !== "score") { const h = document.createElement("div"); h.className = "small muted"; h.textContent = pm === "signals" ? "Key signals (A and B need one of them):" : "Optional: A also needs one of these signals:"; B.appendChild(h);
        const d = document.createElement("div"); d.className = "chips"; const cur = new Set(A.a_signals || []);
        d.innerHTML = sigs.map(s => `<button class="chip" type="button" data-s="${esc(s.id)}" aria-pressed="${cur.has(s.id)}">${esc(s.label)}</button>`).join("");
        d.querySelectorAll("button").forEach(b => b.onclick = () => { cur.has(b.dataset.s) ? cur.delete(b.dataset.s) : cur.add(b.dataset.s); A.a_signals = [...cur]; save(); b.setAttribute("aria-pressed", cur.has(b.dataset.s)); });
        B.appendChild(d); }
      break; }
    case "hold": {
      B.appendChild(choice("hold_enabled_c", [["yes", "Yes, park very large companies"], ["no", "No"]], v => { A.hold_enabled = v === "yes"; show(); }));
      if (A.hold_enabled) { const g = document.createElement("div"); g.className = "grid2"; g.appendChild(field("hold_employees", "Employees from", "10001")); g.appendChild(field("hold_revenue", "or revenue from ($)", "6000000000")); B.appendChild(g); }
      break; }
    case "sources": {
      A.sources = A.sources || {sitemap: true, search: false, discover: true, ai: false};
      const items = [["crawl", "Each company's own website (always on)", true], ["sitemap", "Their sitemap pages", false], ["search", "Web search (needs a search provider in Settings)", false],
        ["discover", "Find websites for rows without one (needs search)", false], ["ai", "AI review of unclear accounts (needs Claude Code, Codex or an API in Settings)", false]];
      const d = document.createElement("div"); d.className = "chips";
      d.innerHTML = items.map(([k, l, fixed]) => `<button class="chip" type="button" data-k="${k}" aria-pressed="${fixed || !!A.sources[k]}" ${fixed ? "disabled" : ""}>${esc(l)}</button>`).join("");
      d.querySelectorAll("button:not([disabled])").forEach(b => b.onclick = () => { A.sources[b.dataset.k] = !A.sources[b.dataset.k]; save(); show(); });
      B.appendChild(d);
      if (A.sources.search) { const r = await preview(); const h = document.createElement("div"); h.className = "small muted"; h.textContent = "Search queries the engine will run ({domain} = the company's website). Edit if you like:"; B.appendChild(h);
        if (!A.search_queries || !A.search_queries.length) A.search_queries = r.config.research.search_queries; B.appendChild(tagInput("search_queries", [])); }
      break; }
    case "columns": {
      if (!A.export_columns) A.export_columns = W.default_export.slice();
      const cur = new Set(A.export_columns); const d = document.createElement("div"); d.className = "chips";
      d.innerHTML = W.export_columns.map(([k, l]) => `<button class="chip" type="button" data-c="${k}" aria-pressed="${cur.has(k)}">${esc(l.replace(/_/g, " "))}</button>`).join("");
      d.querySelectorAll("button").forEach(b => b.onclick = () => { cur.has(b.dataset.c) ? cur.delete(b.dataset.c) : cur.add(b.dataset.c); A.export_columns = W.export_columns.map(x => x[0]).filter(k => cur.has(k)); save(); b.setAttribute("aria-pressed", cur.has(b.dataset.c)); });
      B.appendChild(d); break; }
    case "review": {
      const r = await preview();
      B.appendChild(field("profile_name", "Profile name", r.config.name));
      const dl = document.createElement("dl"); dl.className = "rules";
      dl.innerHTML = r.rules.map(([t, d]) => `<div><dt>${esc(t)}</dt><dd>${esc(d)}</dd></div>`).join(""); B.appendChild(dl);
      if (r.errors.length) { const e = document.createElement("div"); e.className = "err small"; e.innerHTML = "Fix before saving:<br>" + r.errors.map(esc).join("<br>"); B.appendChild(e); }
      const n = document.createElement("p"); n.className = "small faint"; n.textContent = "After saving you can fine-tune every phrase, weight and threshold on the ICP profiles page."; B.appendChild(n);
      $("next").disabled = !!r.errors.length; break; }
  }
  if (q.kind !== "review") $("next").disabled = false;
  const first = B.querySelector("input,textarea"); if (first && q.kind !== "review") first.focus({preventScroll: true});
}
$("next").onclick = async () => {
  const S = steps();
  if (S[idx].kind === "review") {
    $("next").disabled = true;
    try {
      const r = await api("/api/profiles", {method: "POST", body: {answers: A, name: A.profile_name || undefined}});
      try { localStorage.removeItem(KEY); } catch (e) { /* ignore */ }
      location.href = "/lists?profile=" + r.id + "&new=1";
    } catch (e) { $("saved").textContent = e.message; $("saved").className = "err small"; $("next").disabled = false; }
    return;
  }
  idx++; show();
};
$("back").onclick = () => { idx--; show(); };
$("skip").onclick = () => { idx++; show(); };
$("restart").onclick = () => { if (confirm("Clear all answers and start again?")) { A = {}; idx = 0; save(); show(); } };
document.addEventListener("keydown", e => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) $("next").click(); });
(async () => {
  await loadMe(); nav("/wizard"); KEY = "icpq-wizard-" + ME.workspace_id;
  W = await api("/api/wizard");
  try { const s = JSON.parse(localStorage.getItem(KEY) || "null"); if (s) { A = s.A || {}; idx = s.idx || 0; } } catch (e) { /* ignore */ }
  show();
})();
