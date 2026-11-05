"""Cost-sensitive responder (paper Section 2.3, Eq. 2): guess, list or ask over the condition frontier.

Let B be the campus branches of the applicable facts whose values differ (the condition frontier),
P(b | type) a per-type campus prior (data/campus_prior.json; provenance in data/README.md),
lambda = c_wrong / c_ask and beta the reading cost of each extra fact shown. Expected costs, in units of
one clarification turn:
    C(guess b*)  = lambda * (1 - max_b P(b))            answer for the most likely branch
    C(list)      = beta * (sum_b |F_b| - |F_b*|)        show every branch, labeled
    C(ask)       = 1                                    one more turn
The policy takes the cheapest action (ties: list, then ask, then guess). lambda -> inf asks or lists
whenever the frontier is non-empty; lambda -> 0 always guesses, which is what a plain RAG does implicitly.
In the code, "assume" is the guess action and "enumerate" the list action.
"""
import json

from .config import DATA
from .text import squash

DEFAULT_LAMBDA = 10.0     # a wrong answer (a wasted trip) costs 10 clarification turns
DEFAULT_BETA = 0.4        # each extra listed fact costs 0.4 turns
_prior = None


def campus_prior(etype):
    global _prior
    if _prior is None:
        p = DATA / "campus_prior.json"
        _prior = json.loads(p.read_text(encoding="utf8")) if p.exists() else {}
    return _prior.get(etype) or _prior.get("_all") or {"zgc": 0.83, "tz": 0.17}


def differs(branches):
    vals = {b: frozenset(squash(f.value) for f in fs) for b, fs in branches.items()}
    return len(set(vals.values())) > 1


def decide(branches, etype, lam=DEFAULT_LAMBDA, beta=DEFAULT_BETA, can_ask=True):
    """branches: {campus: [facts]} restricted to campus-specific branches (zgc/tz)."""
    if len(branches) < 2 or not differs(branches):
        return "answer", None, {}
    prior = campus_prior(etype)
    best = max(branches, key=lambda b: prior.get(b, 0.0))
    costs = {
        "assume": lam * (1.0 - prior.get(best, 0.0)),
        "enumerate": beta * (sum(len(v) for v in branches.values()) - len(branches[best])),
    }
    if can_ask:
        costs["ask"] = 1.0
    order = ["enumerate", "ask", "assume"]
    action = min(order, key=lambda a: (costs.get(a, float("inf")), order.index(a)))
    return action, best, costs
