/* Sign-in and first-run setup forms. */
$("f").addEventListener("submit", async e => {
  e.preventDefault(); $("m").textContent = "";
  const setup = !!$("c");
  const body = setup ? {code: $("c").value, name: $("n").value, email: $("e").value, password: $("p").value, workspace: $("w").value} : {email: $("e").value, password: $("p").value};
  try {
    const r = await fetch(setup ? "/api/setup" : "/api/login", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || "failed");
    location.href = setup ? "/wizard" : "/";
  } catch (err) { $("m").textContent = err.message; }
});
