/* Sign-in, sign-up and first-run setup forms. */
const MODE = $("c") ? "setup" : location.pathname === "/signup" ? "signup" : "login";
fetch("/api/setup-state").then(r => r.json()).then(s => { if ($("toSignup") && s.signup) $("toSignup").classList.remove("hidden"); }).catch(() => {});
$("f").addEventListener("submit", async e => {
  e.preventDefault(); $("m").textContent = "";
  const body = MODE === "setup" ? {code: $("c").value, name: $("n").value, email: $("e").value, password: $("p").value, workspace: $("w").value}
    : MODE === "signup" ? {name: $("n").value, email: $("e").value, password: $("p").value, workspace: $("w").value} : {email: $("e").value, password: $("p").value};
  try {
    const r = await fetch("/api/" + MODE, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || "failed");
    location.href = MODE === "login" ? "/" : "/wizard";
  } catch (err) { $("m").textContent = err.message; }
});
