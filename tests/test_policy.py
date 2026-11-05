"""Eq. 2: the cost-sensitive choice among guessing, listing and asking."""
from types import SimpleNamespace

import pytest

from campusscope import policy


@pytest.fixture(autouse=True)
def fixed_prior(monkeypatch):
    monkeypatch.setattr(policy, "_prior", {"田径球场": {"zgc": 0.83, "tz": 0.17}})


def facts(*values):
    return [SimpleNamespace(value=v) for v in values]


def test_figure2_costs_list_both_campuses():
    # S1: two applicable facts per campus, values differ
    branches = {"zgc": facts("10:00—18:00", "正常开放"), "tz": facts("8:00—22:00", "2月10日—2月24日暂停开放")}
    action, best, costs = policy.decide(branches, "田径球场")
    assert best == "zgc"
    assert costs["assume"] == pytest.approx(10 * (1 - 0.83))      # guess: 1.7
    assert costs["enumerate"] == pytest.approx(0.4 * (4 - 2))      # list: 0.8
    assert costs["ask"] == 1.0
    assert action == "enumerate"


def test_no_frontier_when_the_branches_agree():
    assert policy.decide({"zgc": facts("8:00"), "tz": facts("8:00")}, "田径球场")[0] == "answer"


def test_many_branches_make_asking_cheapest():
    branches = {"zgc": facts(*"abcdef"), "tz": facts(*"ghijkl")}
    assert policy.decide(branches, "田径球场")[0] == "ask"                    # list 2.4, guess 1.7, ask 1
    assert policy.decide(branches, "田径球场", can_ask=False)[0] == "assume"   # after two asks: guess 1.7 < list 2.4


def test_lambda_limits():
    branches = {"zgc": facts("a"), "tz": facts("b")}
    assert policy.decide(branches, "田径球场", lam=0.0, beta=1e9)[0] == "assume"     # what a plain RAG does
    assert policy.decide(branches, "田径球场", lam=1e9, beta=1e9)[0] == "ask"
