"""Small shared helpers: domains, names, time, JSON."""
import json
import re
import urllib.parse
from datetime import UTC, datetime


def now():
    return datetime.now(UTC).isoformat(timespec="seconds")


def ago_iso(hours):
    return datetime.fromtimestamp(datetime.now(UTC).timestamp() - hours * 3600, UTC).isoformat(timespec="seconds")


def host(url):
    """'https://www.Example.com:443/x' -> 'example.com' (also accepts a bare domain)."""
    u = (url or "").strip()
    if not u:
        return ""
    h = urllib.parse.urlparse(u if "//" in u else "http://" + u).netloc.lower().split("@")[-1].split(":")[0]
    return re.sub(r"^www\d?\.", "", h).strip(".")


SECOND_LEVEL = ("co", "com", "org", "gov", "ac", "edu", "net")


def registrable(h):
    p = (h or "").split(".")
    if len(p) >= 3 and len(p[-1]) == 2 and p[-2] in SECOND_LEVEL:
        return ".".join(p[-3:])
    return ".".join(p[-2:])


def same_site(url, domain):
    h, d = host(url), host(domain)
    return bool(h and d) and (h == d or h.endswith("." + d) or registrable(h) == registrable(d))


FREEMAIL = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com", "icloud.com", "live.com", "msn.com",
            "protonmail.com", "proton.me", "comcast.net", "me.com", "mail.com", "gmx.com"}


def domain_from(value):
    """A website, URL or e-mail address -> registrable host, or '' (free-mail domains are not company websites)."""
    v = str(value or "").strip()
    if not v or v.lower() in ("nan", "none", "n/a", "-", "—", "0"):
        return ""
    if "@" in v and "/" not in v:
        v = v.split("@")[-1]
    h = host(v)
    if not h or "." not in h or " " in h or h in FREEMAIL:
        return ""
    return h


SUFFIX = re.compile(r"\b(inc|llc|ltd|l\.l\.c|corp|corporation|co|company|the|lp|llp|pc|pllc|plc|incorporated|gmbh|ag|sa|bv)\b\.?", re.IGNORECASE)


def norm_name(s):
    return re.sub(r"[^a-z0-9]", "", SUFFIX.sub("", str(s or "").lower()))


GENERIC_WORDS = {"inc", "llc", "corp", "company", "group", "services", "service", "the", "and", "associates", "solutions",
                 "systems", "management", "international", "national", "global", "holdings", "partners", "center", "centre"}


def ident_words(name):
    return [w for w in re.findall(r"[a-z0-9]{4,}", (name or "").lower()) if w not in GENERIC_WORDS]


QMAP = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', " ": " ", "–": "-", "—": "-", "\u200b": ""})


def norm_text(s):
    return re.sub(r"\s+", " ", (s or "").translate(QMAP)).strip().lower()


def jdump(o):
    return json.dumps(o, separators=(",", ":"), default=str)


def jload(s, default=None):
    try:
        return json.loads(s) if s else default
    except (TypeError, ValueError):
        return default


def parse_number(v):
    """'$12.5M', '1,200', '5k', '10,001+' , '201-500' (upper bound) -> float or None. Unknown stays None (never 0)."""
    s = str(v or "").strip().lower().replace(",", "").replace("$", "").replace("usd", "").strip()
    if not s or s in ("nan", "none", "n/a", "-", "—", "unknown"):
        return None
    m = re.match(r"^(\d+(?:\.\d+)?)\s*([kmbt]|thousand|million|billion)?\s*(?:-|to)\s*(\d+(?:\.\d+)?)\s*([kmbt]|thousand|million|billion)?", s)
    if m:
        return _mult(float(m.group(3)), m.group(4) or m.group(2))
    m = re.match(r"^(\d+(?:\.\d+)?)\s*([kmbt]|thousand|million|billion)?\s*\+?", s)
    if not m:
        return None
    return _mult(float(m.group(1)), m.group(2))


def _mult(x, unit):
    return x * {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6, "b": 1e9, "billion": 1e9, "t": 1e12}.get(unit or "", 1)
