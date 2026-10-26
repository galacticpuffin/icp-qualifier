from icpq.icp.schema import compile_icp, parse_expr, eval_expr, validate
from icpq.engine import extract
from icpq.ingest import group, linked
from icpq.util import parse_number, domain_from
import pytest


def cfg(**k):
    base = {"signals": [{"id": "a", "label": "A", "patterns": ["alpha thing"], "requirement": "mandatory", "markers": ["alpha thing now"]},
                        {"id": "b", "label": "B", "patterns": ["beta"], "requirement": "mandatory"}]}
    base.update(k)
    return base


def test_expression():
    t = parse_expr("a AND (b OR NOT c)", {"a", "b", "c"})
    assert eval_expr(t, {"a", "b"}) and not eval_expr(t, {"a", "c"})
    with pytest.raises(ValueError):
        parse_expr("a AND zz", {"a"})


def test_validate_and_gate():
    assert validate({"signals": []})
    icp = compile_icp(cfg(gate={"mode": "any_mandatory"}))
    assert icp.gate({"a"})[0] and not compile_icp(cfg()).gate({"a"})[0]


def test_negative_context_and_offsite():
    icp = compile_icp(cfg(negative_context=["scam"]))
    acct = {"name": "Foo", "domain": "foo.com"}
    ev = extract.grade(icp, extract.find(icp, "Beware the scam: alpha thing", "https://foo.com/x", acct), acct)
    assert ev[0]["status"] == "REJECTED"
    ev = extract.grade(icp, extract.find(icp, "We do alpha thing now", "https://other.com/x", acct), acct)
    assert ev[0]["status"] != "VERIFIED"
    ev = extract.grade(icp, extract.find(icp, "We do alpha thing now", "https://foo.com/x", acct), acct)
    assert ev[0]["status"] == "VERIFIED" and ev[0]["marker"]


def test_parse_and_grouping():
    assert parse_number("$12.5M") == 12.5e6 and parse_number("201-500") == 500 and parse_number("") is None
    assert domain_from("bob@gmail.com") == "" and domain_from("https://www.Acme.com/x") == "acme.com"
    assert linked("University of Wyoming", ["uwyo"])
    comps = group([{"row": 2, "name": "Acme Corp", "domain": "acme.com"}, {"row": 3, "name": "Acme Corp - Denver", "domain": "acme.com"},
                   {"row": 4, "name": "Acme Corp", "domain": "acme.com"}])
    rels = sorted(c["relation"] for c in comps)
    assert rels == ["", "UNIT"] and sum(len(c["members"]) for c in comps) == 3
