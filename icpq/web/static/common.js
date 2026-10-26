/* Shared page helpers: API calls with the CSRF token, navigation, workspace switcher. */
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const fmt = n => (n ?? 0).toLocaleString("en-US");
const $ = id => document.getElementById(id);
let ME = null;

async function api(path, opts = {}) {
  const o = {cache: "no-store", ...opts, headers: {...(opts.headers || {})}};
  if (o.body && typeof o.body !== "string" && !(o.body instanceof Blob) && !(o.body instanceof ArrayBuffer)) { o.body = JSON.stringify(o.body); o.headers["Content-Type"] = "application/json"; }
  if ((o.method || "GET") !== "GET" && ME) o.headers["X-CSRF"] = ME.csrf;
  const r = await fetch(path, o);
  if (r.status === 401) { location.href = "/login"; throw new Error("signed out"); }
  const ct = r.headers.get("content-type") || "";
  const data = ct.includes("json") ? await r.json() : await r.blob();
  if (!r.ok) throw new Error((data && data.error) || ("HTTP " + r.status));
  return data;
}

async function loadMe() {
  ME = await api("/api/me");
  return ME;
}

function nav(current) {
  const el = $("nav"); if (!el || !ME) return;
  const links = [["/", "Dashboard"], ["/lists", "Upload & runs"], ["/profiles", "ICP profiles"], ["/settings", "Settings"]];
  el.innerHTML = links.map(([h, l]) => `<a href="${h}"${h === current ? ' aria-current="page"' : ""}>${l}</a>`).join("") +
    `<span class="sp"></span><select id="wsPick" aria-label="Workspace">${ME.workspaces.map(w => `<option value="${w.id}"${w.id === ME.workspace_id ? " selected" : ""}>${esc(w.name)}</option>`).join("")}<option value="new">+ New workspace…</option></select>` +
    (ME.no_auth ? "" : `<button class="link" id="signout" type="button">Sign out</button>`);
  $("wsPick").onchange = async e => {
    if (e.target.value === "new") {
      const n = prompt("Name of the new workspace (its lists, profiles and results are kept completely separate):");
      if (!n) { e.target.value = ME.workspace_id; return; }
      await api("/api/workspaces", {method: "POST", body: {name: n}});
      location.href = "/wizard"; return;
    }
    await api("/api/workspaces/switch", {method: "POST", body: {id: +e.target.value}});
    location.reload();
  };
  if ($("signout")) $("signout").onclick = async () => { await api("/api/logout", {method: "POST"}); location.href = "/login"; };
}

function download(blob, name) {
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = name; document.body.appendChild(a); a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
}
