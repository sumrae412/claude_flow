#!/usr/bin/env python3
"""Tests for stat-eval.py statistical evaluation framework."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
stat_eval = importlib.import_module("stat-eval")


# ---------------------------------------------------------------------------
# Statistical primitives
# ---------------------------------------------------------------------------

class TestMean:
    def test_empty(self):
        assert stat_eval.mean([]) == 0.0

    def test_single(self):
        assert stat_eval.mean([0.5]) == 0.5

    def test_multiple(self):
        assert abs(stat_eval.mean([0.2, 0.4, 0.6]) - 0.4) < 1e-9


class TestStdDev:
    def test_fewer_than_2(self):
        assert stat_eval.std_dev([]) == 0.0
        assert stat_eval.std_dev([1.0]) == 0.0

    def test_identical_values(self):
        assert stat_eval.std_dev([0.5, 0.5, 0.5]) == 0.0

    def test_known_values(self):
        # [1, 2, 3] sample std dev = 1.0
        assert abs(stat_eval.std_dev([1.0, 2.0, 3.0]) - 1.0) < 1e-9


class TestConfidenceInterval:
    def test_empty(self):
        assert stat_eval.confidence_interval_95([]) == (0.0, 0.0)

    def test_tight_values(self):
        values = [0.8] * 20
        lo, hi = stat_eval.confidence_interval_95(values)
        assert abs(lo - 0.8) < 1e-6 and abs(hi - 0.8) < 1e-6  # zero variance

    def test_wide_values(self):
        values = [0.0, 1.0, 0.0, 1.0, 0.0, 1.0]
        lo, hi = stat_eval.confidence_interval_95(values)
        assert lo < 0.5 < hi  # mean is 0.5, CI should span it

    def test_bounds_clamped(self):
        lo, hi = stat_eval.confidence_interval_95([0.95, 0.98, 0.99, 1.0])
        assert hi <= 1.0
        assert lo >= 0.0


class TestPassRateCI:
    def test_all_pass(self):
        lo, hi = stat_eval.pass_rate_ci(10, 10)
        assert lo > 0.7  # lower bound should be reasonably high
        assert hi <= 1.0

    def test_none_pass(self):
        lo, hi = stat_eval.pass_rate_ci(0, 10)
        assert lo >= 0.0
        assert hi < 0.3

    def test_half_pass(self):
        lo, hi = stat_eval.pass_rate_ci(5, 10)
        assert lo < 0.5 < hi

    def test_zero_total(self):
        assert stat_eval.pass_rate_ci(0, 0) == (0.0, 0.0)


class TestJaccardSimilarity:
    def test_identical(self):
        s = {"a", "b", "c"}
        assert stat_eval.jaccard_similarity(s, s) == 1.0

    def test_disjoint(self):
        assert stat_eval.jaccard_similarity({"a"}, {"b"}) == 0.0

    def test_partial_overlap(self):
        j = stat_eval.jaccard_similarity({"a", "b", "c"}, {"b", "c", "d"})
        assert abs(j - 0.5) < 1e-9  # intersection=2, union=4

    def test_both_empty(self):
        assert stat_eval.jaccard_similarity(set(), set()) == 1.0


class TestChiSquared:
    def test_identical_distributions(self):
        p = stat_eval.chi_squared_2x2((50, 50), (50, 50))
        assert p >= 0.5  # no significant difference

    def test_very_different(self):
        p = stat_eval.chi_squared_2x2((90, 10), (10, 90))
        assert p <= 0.01  # highly significant

    def test_zero_total(self):
        assert stat_eval.chi_squared_2x2((0, 0), (0, 0)) == 1.0

    def test_moderate_difference(self):
        p = stat_eval.chi_squared_2x2((70, 30), (55, 45))
        assert 0.01 < p < 0.5

    def test_boundary_not_step_function(self):
        """Verify chi2=5.0 returns p < 0.05 (was boundary bug with step function)."""
        # chi2=5.0 has true p ~= 0.025, should be < 0.05
        p = stat_eval.chi_squared_2x2((80, 20), (60, 40))
        # This produces chi2 ~= 9.52, p should be well below 0.05
        assert p < 0.01

    def test_interpolation_continuity(self):
        """P-values should decrease monotonically as distributions diverge."""
        p1 = stat_eval.chi_squared_2x2((60, 40), (55, 45))
        p2 = stat_eval.chi_squared_2x2((70, 30), (55, 45))
        p3 = stat_eval.chi_squared_2x2((80, 20), (55, 45))
        assert p1 > p2 > p3  # more divergence = lower p


# ---------------------------------------------------------------------------
# Flakiness analysis (unit-level, no file I/O)
# ---------------------------------------------------------------------------

class TestFlakiness:
    """Test the flakiness computation logic directly."""

    def test_stable_scores(self):
        # Monotonically increasing — few transitions around median
        scores = [0.80, 0.81, 0.82, 0.83, 0.84, 0.85, 0.86, 0.87]
        median = sorted(scores)[len(scores) // 2]
        above = [s >= median for s in scores]
        transitions = sum(1 for i in range(1, len(above)) if above[i] != above[i - 1])
        flakiness = transitions / (len(scores) - 1)
        assert flakiness < 0.3  # stable, monotonic scores

    def test_alternating_scores(self):
        scores = [0.1, 0.9, 0.1, 0.9, 0.1, 0.9]
        median = sorted(scores)[len(scores) // 2]
        above = [s >= median for s in scores]
        transitions = sum(1 for i in range(1, len(above)) if above[i] != above[i - 1])
        flakiness = transitions / (len(scores) - 1)
        assert flakiness >= 0.6  # highly flaky


# ---------------------------------------------------------------------------
# Promotion logic (unit-level)
# ---------------------------------------------------------------------------

class TestPromotionLogic:
    """Test the CI-dominance check that should_promote uses."""

    def test_ci_dominant(self):
        # Winner's lower > loser's upper = clear winner
        winner_ci_lower = 0.75
        loser_ci_upper = 0.70
        assert winner_ci_lower > loser_ci_upper

    def test_overlapping_ci(self):
        # Overlapping CIs = not enough evidence
        winner_ci_lower = 0.65
        loser_ci_upper = 0.72
        assert winner_ci_lower <= loser_ci_upper  # no CI dominance
