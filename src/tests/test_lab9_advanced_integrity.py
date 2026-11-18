"""M7 extra traps beyond lab9.traps: each one is a way to turn a red report green by editing the
report or the spec instead of the agent. integrity_check must flag every one, and must stay quiet
on an honest report. Run: python -m pytest -q -m student -o addopts= -k advanced"""
import copy

import pytest

pytestmark = pytest.mark.student

ROWS = [{"item_id": f"E-{i:03d}", "seed": s, "pass_rate": i != 3 or s != 2,
         "slices": ["money_movement"] if i < 2 else []}
        for i in range(4) for s in (1, 2)]
SPEC = {"eval_set_version": "v2", "seeds": [1, 2], "pass_k": [1, 2],
        "metrics": [{"id": "pass_rate", "kind": "capability", "blocking": True,
                     "threshold": {"min": 0.8, "no_significant_drop": True}}],
        "slices": [{"name": "money_movement", "metric": "pass_rate", "min": 0.95,
                    "no_significant_drop": True, "blocking": True}]}


def report(rows=None, **over):
    from lab9.eval import aggregate

    rows = copy.deepcopy(ROWS if rows is None else rows)
    rep = {"manifest": {"eval_set_sha": "x", "items": 4, "seeds": [1, 2]}, "rows": rows,
           "evaluator_failures": [],
           "metrics": aggregate([dict(r, cost=1.0) for r in rows], ["pass_rate"], k_values=[1, 2])}
    rep.update(over)
    return rep


@pytest.fixture(scope="module")
def gate():
    from lab9 import gate

    return gate


def test_honest_report_is_trusted(gate):
    assert gate.integrity_check(report(), report(), SPEC, SPEC) == []


def test_duplicated_row_replacing_a_failing_one(gate):
    rows = copy.deepcopy(ROWS)
    rows[7] = copy.deepcopy(rows[6])            # E-003@2 (fail) replaced by a copy of E-003@1 (pass)
    assert gate.integrity_check(report(rows), report(), SPEC)


def test_evaluator_failures_on_a_green_run(gate):
    rep = report(evaluator_failures=["E-001@1:ReplyMatchesLedger:KeyError"])
    assert gate.integrity_check(rep, report(), SPEC)


def test_hand_edited_headline_metric(gate):
    rep = report()
    rep["metrics"]["pass_rate"] = 1.0           # rows still say 0.875
    assert gate.integrity_check(rep, report(), SPEC)


def test_hand_edited_pass_hat(gate):
    rep = report()
    rep["metrics"]["pass_hat_2"] = 1.0
    assert gate.integrity_check(rep, report(), SPEC)


def test_item_relabelled_out_of_a_slice(gate):
    rows = copy.deepcopy(ROWS)
    for r in rows:
        if r["item_id"] == "E-000":
            r["slices"] = []
    assert gate.integrity_check(report(rows), report(), SPEC)


def test_row_verdict_turned_into_a_string(gate):
    rep = report()
    rep["rows"][7]["pass_rate"] = "skipped"     # metrics left as they were
    assert gate.integrity_check(rep, report(), SPEC)


def test_infinite_metric(gate):
    rep = report()
    rep["metrics"]["cost_per_success"] = float("inf")
    assert gate.integrity_check(rep, report(), SPEC)


@pytest.mark.parametrize("loosen", [
    lambda s: s["slices"].clear(),                                       # slice removed
    lambda s: s["slices"][0].pop("no_significant_drop"),                 # slice CI check dropped
    lambda s: s["slices"][0].__setitem__("blocking", False),             # slice made advisory
    lambda s: s["metrics"][0].__setitem__("blocking", False),            # metric made advisory
    lambda s: s["metrics"].clear(),                                      # metric removed
    lambda s: s.__setitem__("seeds", [1]),                               # fewer seeds
])
def test_ratchet_flags_looser_spec(gate, loosen):
    loose = copy.deepcopy(SPEC)
    loosen(loose)
    assert gate.integrity_check(report(), report(), loose, SPEC)


def test_ratchet_allows_stricter_spec_and_new_version(gate):
    strict = copy.deepcopy(SPEC)
    strict["metrics"][0]["threshold"]["min"] = 0.85
    assert gate.integrity_check(report(), report(), strict, SPEC) == []
    new_version = copy.deepcopy(SPEC)
    new_version["eval_set_version"] = "v3"
    new_version["slices"] = []
    assert gate.integrity_check(report(), report(), new_version, SPEC) == []
