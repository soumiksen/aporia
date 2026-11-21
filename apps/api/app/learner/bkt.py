"""Bayesian Knowledge Tracing, standard update equations (no fitting; see docs/BACKLOG.md).

p_known is the probability the student knows the concept. After each observation:
    posterior = P(known | evidence)            (Bayes with slip and guess)
    p_known'  = posterior + (1 - posterior) * p_learn
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class BKTParams:
    p_init: float = 0.2
    p_learn: float = 0.15
    p_guess: float = 0.2
    p_slip: float = 0.1


DEFAULT_PARAMS = BKTParams()


def predict_correct(p_known: float, params: BKTParams = DEFAULT_PARAMS) -> float:
    """P(next attempt correct) = P(known)(1 - slip) + P(unknown) guess."""
    return p_known * (1 - params.p_slip) + (1 - p_known) * params.p_guess


def update(p_known: float, correct: bool, params: BKTParams = DEFAULT_PARAMS) -> float:
    """The new p_known after one observation."""
    if correct:
        evidence = p_known * (1 - params.p_slip) + (1 - p_known) * params.p_guess
        posterior = p_known * (1 - params.p_slip) / evidence
    else:
        evidence = p_known * params.p_slip + (1 - p_known) * (1 - params.p_guess)
        posterior = p_known * params.p_slip / evidence
    return posterior + (1 - posterior) * params.p_learn
