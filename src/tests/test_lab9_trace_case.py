"""Regression test from docs/trace_case.md: seeded_regression C-014@11 (FM-05 pre_deducted).

First wrong step: event #5 `proposal` subtracts the earlier refund before calling the host,
which subtracts it again -> ledger 90.000đ instead of 120.000đ.
"""
import pytest

pytestmark = pytest.mark.student


@pytest.fixture(scope="module")
def investigate():
    from lab9.trace_case import investigate

    return investigate


def _kinds(trial):
    return [e.get("kind") for e in trial["events"]]


def test_lab9_fm05_pre_deducted_caught_on_seeded_regression(investigate):
    case = investigate("seeded_regression", "C-014", 11)
    t, label = case["trial"], case["label"]
    assert "proposal" in _kinds(t)                                  # the agent rewrote the quote
    assert t["snapshot"]["refund_vnd"] != label["refund_vnd"]       # ledger is wrong (90.000 vs 120.000)


def test_lab9_fm05_pre_deducted_absent_on_fixed(investigate):
    case = investigate("fixed", "C-014", 11)
    t, label = case["trial"], case["label"]
    assert "proposal" not in _kinds(t)
    assert t["snapshot"]["refund_vnd"] == label["refund_vnd"]
