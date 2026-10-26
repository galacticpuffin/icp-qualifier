/* ICP profiles: review the generated rules, edit signals (form) or everything (JSON), test rules on text, version history,
   requalify a list with the edited profile. */
let P = [], cur = null, cfg = null;
const params = new URLSearchParams(location.search);
async function loadList(){
  P = (await api("/api/profiles")).profiles;
  $("plist").innerHTML = P.length ? P.map(p => `<button class="ind" style="all:unset;box-sizing:border-box;cursor:pointer;display:flex;justify-content:space-between;gap:12px;padding:10px 14px;background:var(--surface);border:1px solid ${cur && cur.id === p.id ? "var(--accent-line)" : "var(--line)"};border-radius:var(--r)" data-id="${p.id}">
    <span>${esc(p.name)}<br><span class="faint small">v${p.version} · ${p.lists.length ? "used by " + p.lists.map(esc).join(", ") : "not used by a list yet"}</span></span><b class="small">Open</b></button>`).join("")
    : '<div class="ind"><span>No profiles yet. <a href="/wizard">Start the wizard</a>.</span><b>0</b></div>';
  $("plist").querySelectorAll("[data-id]").forEach(b => b.onclick = () => open(+b.dataset.id));
}
function rulesHtml(r){ return r.map(([t, d]) => `<div><dt>${esc(t)}</dt><dd>${esc(d)}</dd></div>`).join(""); }
function formEditor(){
  const reqs = [["mandatory","Must have"],["preferred","Nice to have"],["negative","Counts against"],["info","Just record"]];
  $("formEd").innerHTML = `<label class="f">Profile name<input class="in" id="fn" value="${esc(cfg.name)}"></label>` + cfg.signals.map((s, i) => `<div class="sig">
    <div class="hd"><input class="in" style="max-width:60%" data-k="label" data-i="${i}" value="${esc(s.label)}" aria-label="Signal name"><select class="in" style="width:auto" data-k="requirement" data-i="${i}">${reqs.map(([v, l]) => `<option value="${v}"${s.requirement === v ? " selected" : ""}>${l}</option>`).join("")}</select></div>
    <label class="f">Phrases to look for (one per line; prefix re: for a regular expression)<textarea class="in" data-k="patterns" data-i="${i}">${esc(s.patterns.join("\n"))}</textarea></label>
    <label class="f">Proof markers (explicit evidence; optional)<textarea class="in" style="min-height:50px" data-k="markers" data-i="${i}">${esc(s.markers.join("\n"))}</textarea></label>
    <div class="row small faint">weight <input class="in" style="width:80px" type="number" data-k="weight" data-i="${i}" value="${s.weight}"> · id <code>${esc(s.id)}</code> · ${esc(s.category)} <button class="link" type="button" data-del="${i}">Remove</button></div></div>`).join("") +
    `<button class="btn" type="button" id="addSig">+ Add signal</button>`;
  $("formEd").querySelectorAll("[data-k]").forEach(el => el.onchange = () => { const s = cfg.signals[+el.dataset.i], k = el.dataset.k;
    s[k] = ["patterns", "markers"].includes(k) ? el.value.split("\n").map(x => x.trim()).filter(Boolean) : k === "weight" ? +el.value : el.value; syncJson(); });
  $("fn").onchange = () => { cfg.name = $("fn").value; syncJson(); };
  $("formEd").querySelectorAll("[data-del]").forEach(b => b.onclick = () => { cfg.signals.splice(+b.dataset.del, 1); syncJson(); formEditor(); });
  $("addSig").onclick = () => { cfg.signals.push({id: "new_signal_" + (cfg.signals.length + 1), label: "New signal", category: "other", requirement: "preferred", patterns: [], markers: [], weight: 10}); syncJson(); formEditor(); };
}
const syncJson = () => { $("jsonEd").value = JSON.stringify(cfg, null, 2); };
function readEditor(){ if (!$("jsonEd").classList.contains("hidden")) cfg = JSON.parse($("jsonEd").value); return cfg; }
async function open(id){
  const r = await api("/api/profiles/" + id); cur = r; cfg = r.config;
  $("pedit").classList.remove("hidden"); $("ptitle").textContent = `${r.name} · v${r.version}`;
  $("rules").innerHTML = rulesHtml(r.rules); $("perr").textContent = r.errors.join(" ");
  $("dl").href = `/api/profiles/${id}/export`; syncJson(); formEditor();
  const L = (await api("/api/lists")).lists; $("rqList").innerHTML = L.length ? L.map(l => `<option value="${l.id}">${esc(l.name)}</option>`).join("") : "<option value=''>no lists yet</option>";
  const V = (await api(`/api/profiles/${id}/versions`)).versions; $("vers").innerHTML = V.map(v => `<li>v${v.version} · ${esc(v.saved_at)}<br><span class="m">${esc(v.note || "")}</span></li>`).join("");
  loadList(); history.replaceState(null, "", "/profiles?id=" + id);
}
$("tabForm").onclick = () => { try { readEditor(); } catch (e) { $("pmsg").textContent = "JSON error: " + e.message; return; } $("tabForm").setAttribute("aria-pressed", true); $("tabJson").setAttribute("aria-pressed", false); $("formEd").classList.remove("hidden"); $("jsonEd").classList.add("hidden"); formEditor(); };
$("tabJson").onclick = () => { syncJson(); $("tabJson").setAttribute("aria-pressed", true); $("tabForm").setAttribute("aria-pressed", false); $("formEd").classList.add("hidden"); $("jsonEd").classList.remove("hidden"); };
$("check").onclick = async () => { try { const r = await api("/api/profiles/check", {method: "POST", body: {config: readEditor()}}); $("rules").innerHTML = rulesHtml(r.rules);
  $("perr").textContent = r.errors.join(" "); $("pmsg").textContent = r.errors.length ? "" : "Looks good."; $("pmsg").className = "small okt"; } catch (e) { $("pmsg").textContent = e.message; $("pmsg").className = "small err"; } };
$("saveP").onclick = async () => { try { const r = await api("/api/profiles/" + cur.id, {method: "PUT", body: {config: readEditor(), note: $("note").value}}); $("pmsg").className = "small okt"; $("pmsg").textContent = `Saved as v${r.version}.`; $("note").value = ""; open(cur.id); }
  catch (e) { $("pmsg").className = "small err"; $("pmsg").textContent = e.message; } };
$("rq").onclick = async () => { const lid = +$("rqList").value; if (!lid) return; try { await api("/api/runs", {method: "POST", body: {list_id: lid, profile_id: cur.id, mode: "requalify"}}); location.href = "/lists"; } catch (e) { $("pmsg").className = "small err"; $("pmsg").textContent = e.message; } };
$("dup").onclick = async () => { const r = await api(`/api/profiles/${cur.id}/duplicate`, {method: "POST"}); open(r.id); };
$("arch").onclick = async () => { if (!confirm("Archive this profile? Lists keep their results.")) return; await api("/api/profiles/" + cur.id, {method: "DELETE"}); cur = null; $("pedit").classList.add("hidden"); loadList(); };
$("tRun").onclick = async () => {
  try { const r = await api("/api/profiles/test", {method: "POST", body: {config: readEditor(), text: $("tText").value, name: $("tName").value, domain: $("tDom").value, url: $("tUrl").value}});
    $("tGate").innerHTML = r.gate ? '<span class="okt">Qualification rule met</span> · ' + esc(r.gate_why) : '<span class="err">Rule not met</span> · ' + esc(r.gate_why);
    $("tOut").innerHTML = r.evidence.length ? r.evidence.map(e => `<li><span class="sg sg-${esc(e.status)}">${esc(e.status)}</span><b>${esc(e.label)}</b> <span class="m">${esc(e.confidence)}${e.marker ? " · proof marker" : ""} · ${esc(e.reason)}</span><br><span class="q">“${esc(e.snippet)}”</span></li>`).join("") : "<li>No signal phrases found in this text.</li>";
  } catch (e) { $("tGate").textContent = e.message; }
};
(async () => { await loadMe(); nav("/profiles"); await loadList(); const id = +(params.get("id") || 0) || (P[0] && P[0].id); if (id) open(id); })();
