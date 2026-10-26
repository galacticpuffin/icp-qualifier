/* Upload -> map columns -> import -> research runs (start / pause / resume / stop / retry / requalify). */
let UP = null, PROFS = [];
const params = new URLSearchParams(location.search);
const FIELDS = [["name","Company name"],["website","Website / domain"],["email","E-mail (domain used if no website)"],["industry","Industry"],["employees","Employees"],["revenue","Revenue"],["location","Location"],["parent","Parent company"]];
async function upload(file){
  $("gomsg").textContent = ""; $("drop").textContent = "Reading " + file.name + "…";
  try {
    UP = await api("/api/lists/upload", {method: "POST", body: await file.arrayBuffer(), headers: {"X-Filename": file.name, "Content-Type": "application/octet-stream"}});
  } catch (e) { $("drop").textContent = "Couldn't read that file: " + e.message + " — choose another"; return; }
  $("drop").textContent = file.name + " loaded · choose another file";
  $("mapBox").classList.remove("hidden"); $("mapTitle").textContent = "Match your columns"; $("mapRows").textContent = `${fmt(UP.rows)} rows`; $("lname").value = UP.name;
  $("mapGrid").innerHTML = FIELDS.map(([k, l]) => `<label class="f">${l}<select class="in" data-f="${k}"><option value="">— not in this file —</option>${UP.header.map(h => `<option${UP.mapping[k] === h ? " selected" : ""}>${esc(h)}</option>`).join("")}</select></label>`).join("");
  $("sample").innerHTML = `<thead><tr>${UP.header.map(h => `<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>${UP.sample.map(r => `<tr>${r.map(c => `<td>${esc(c)}</td>`).join("")}</tr>`).join("")}</tbody>`;
  $("lprof").innerHTML = PROFS.map(p => `<option value="${p.id}"${+params.get("profile") === p.id ? " selected" : ""}>${esc(p.name)}</option>`).join("") || "<option value=''>Create a profile first</option>";
}
async function importList(start){
  const mapping = {}; document.querySelectorAll("[data-f]").forEach(s => { if (s.value) mapping[s.dataset.f] = s.value; });
  if (!mapping.name && !mapping.website) { $("gomsg").textContent = "Pick at least the company name or the website column."; $("gomsg").className = "small err"; return; }
  $("go").disabled = $("goImport").disabled = true; $("gomsg").className = "small"; $("gomsg").textContent = "Importing…";
  try {
    const pid = +$("lprof").value;
    const r = await api(`/api/lists/${UP.id}/ingest`, {method: "POST", body: {mapping, profile_id: pid || null, name: $("lname").value}});
    const s = r.stats;
    $("gomsg").textContent = `${fmt(s.rows_in_file)} rows → ${fmt(s.companies)} companies (${fmt(s.merged_rows)} duplicate rows merged, ${fmt(s.routed_units)} units routed to a parent, ${fmt(s.no_website)} without a website).`;
    if (start && pid) { await api("/api/runs", {method: "POST", body: {list_id: UP.id, profile_id: pid, mode: "research", threads: +$("threads").value || null}}); $("gomsg").textContent += " Research started."; }
    $("mapBox").classList.add("hidden"); UP = null; refresh();
  } catch (e) { $("gomsg").className = "small err"; $("gomsg").textContent = e.message; }
  $("go").disabled = $("goImport").disabled = false;
}
async function refresh(){
  const L = (await api("/api/lists")).lists;
  const pn = id => (PROFS.find(p => p.id === id) || {}).name || "—";
  $("ltb").innerHTML = L.length ? L.map(l => { const c = l.counts || {}, done = c.done || 0, tot = Object.values(c).reduce((a, b) => a + b, 0), r = l.run;
    const running = r && ["running", "queued"].includes(r.status), paused = r && r.status === "paused";
    return `<tr><td><b>${esc(l.name)}</b><br><span class="faint small">${esc(l.filename)} · ${esc((l.uploaded_at || "").slice(0, 16))}</span></td>
      <td>${fmt(l.rows_in_file)} → ${fmt((l.ingest || {}).companies || 0)}${l.status !== "ready" ? '<br><span class="err small">not imported yet</span>' : ""}</td>
      <td><select class="in" style="width:auto" data-prof="${l.id}">${PROFS.map(p => `<option value="${p.id}"${p.id === l.profile_id ? " selected" : ""}>${esc(p.name)}</option>`).join("")}</select></td>
      <td>${fmt(done)} / ${fmt(tot)} researched<div class="bar" style="margin-top:6px;width:140px"><i style="width:${tot ? (100 * done / tot).toFixed(1) : 0}%"></i></div>${c.failed ? `<span class="err small">${c.failed} failed</span>` : ""}</td>
      <td>${r ? `${esc(r.mode)} · <b>${esc(r.status)}</b><br><span class="faint small">${esc((r.started_at || r.created_at || "").slice(0, 16))}${r.error ? " · " + esc(r.error) : ""}</span>` : '<span class="faint">no run yet</span>'}</td>
      <td class="row">${running ? `<button class="btn" data-a="pause" data-r="${r.id}">Pause</button><button class="link" data-a="stop" data-r="${r.id}">Stop</button>` :
        paused ? `<button class="btn" data-a="resume" data-r="${r.id}">Resume</button><button class="link" data-a="stop" data-r="${r.id}">Stop</button>` :
        `<button class="btn primary" data-m="research" data-l="${l.id}">Research</button><button class="btn" data-m="retry" data-l="${l.id}" title="Re-research RETRY and failed accounts">Retry blocked</button><button class="btn" data-m="requalify" data-l="${l.id}" title="Re-judge with the selected profile from cached pages">Requalify</button>`}
        <a class="link" href="/?l=${l.id}">View</a><button class="link" data-del="${l.id}">Delete</button></td></tr>`; }).join("")
    : '<tr><td colspan="6" class="faint">No lists yet. Upload one above.</td></tr>';
  document.querySelectorAll("[data-m]").forEach(b => b.onclick = async () => { const lid = +b.dataset.l, pid = +document.querySelector(`[data-prof="${lid}"]`).value;
    try { await api("/api/runs", {method: "POST", body: {list_id: lid, profile_id: pid, mode: b.dataset.m}}); refresh(); } catch (e) { alert(e.message); } });
  document.querySelectorAll("[data-a]").forEach(b => b.onclick = async () => { await api(`/api/runs/${b.dataset.r}/${b.dataset.a}`, {method: "POST"}); refresh(); });
  document.querySelectorAll("[data-del]").forEach(b => b.onclick = async () => { if (!confirm("Delete this list and all of its results?")) return; await api("/api/lists/" + b.dataset.del, {method: "DELETE"}); refresh(); });
}
const drop = $("drop"), file = $("file");
drop.onclick = () => file.click(); drop.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); file.click(); } };
file.onchange = () => file.files[0] && upload(file.files[0]);
drop.ondragover = e => { e.preventDefault(); drop.classList.add("on"); }; drop.ondragleave = () => drop.classList.remove("on");
drop.ondrop = e => { e.preventDefault(); drop.classList.remove("on"); if (e.dataTransfer.files[0]) upload(e.dataTransfer.files[0]); };
$("go").onclick = () => importList(true); $("goImport").onclick = () => importList(false);
(async () => { await loadMe(); nav("/lists"); PROFS = (await api("/api/profiles")).profiles;
  if (params.get("new")) $("gomsg").textContent = "Profile saved. Upload a list to qualify with it.";
  await refresh(); setInterval(refresh, 10000); })();
