"""Unit tests for eval profile gates (no LLM)."""

from __future__ import annotations

import unittest

from evals.thresholds import (
    evaluate_gates,
    nearest_rank_percentile,
    profile_config,
    resolve_profile,
)


def _item(item_id: str, category: str, passed: bool, latency_ms: float) -> dict:
    return {
        "id": item_id,
        "category": category,
        "pass": passed,
        "grade": {"pass": passed, "latency_ms": latency_ms, "checks": []},
    }


class PercentileTests(unittest.TestCase):
    def test_empty(self) -> None:
        self.assertIsNone(nearest_rank_percentile([], 95))

    def test_path_a_n3_p95_is_max(self) -> None:
        self.assertEqual(nearest_rank_percentile([6216, 68913, 6275], 95), 68913.0)

    def test_single(self) -> None:
        self.assertEqual(nearest_rank_percentile([1000], 95), 1000.0)


class ProfileResolveTests(unittest.TestCase):
    def test_unknown_falls_back_to_production(self) -> None:
        self.assertEqual(resolve_profile("nope"), "production")

    def test_explicit_mvp(self) -> None:
        self.assertEqual(resolve_profile("mvp"), "mvp")


class GateTests(unittest.TestCase):
    def test_mvp_ignores_live_failures(self) -> None:
        sections = {
            "static": {"pass": True},
            "fixtures": {"pass": True},
            "live": {
                "pass": False,
                "items": [
                    _item("A-001", "path_a_resolve", True, 6000),
                    _item("B-003", "path_b_gap", False, 20000),
                ],
            },
        }
        gates = evaluate_gates(sections, profile_config("mvp"))
        self.assertTrue(gates["course_pass"])
        self.assertFalse(gates["production_ready"])
        self.assertIn("live_items", gates["blockers"])

    def test_mvp_live_pass_but_slow_is_not_production_ready(self) -> None:
        sections = {
            "static": {"pass": True},
            "fixtures": {"pass": True},
            "live": {
                "pass": True,
                "items": [
                    _item("A-001", "path_a_resolve", True, 6216),
                    _item("A-002", "path_a_resolve", True, 68913),
                    _item("A-003", "path_a_resolve", True, 6275),
                ],
            },
        }
        gates = evaluate_gates(sections, profile_config("mvp"))
        self.assertTrue(gates["course_pass"])
        self.assertFalse(gates["production_ready"])

    def test_production_requires_live_and_p95(self) -> None:
        sections = {
            "static": {"pass": True},
            "fixtures": {"pass": True},
            "live": {
                "pass": True,
                "items": [
                    _item("A-001", "path_a_resolve", True, 6000),
                    _item("A-002", "path_a_resolve", True, 8000),
                    _item("A-003", "path_a_resolve", True, 9000),
                    _item("C-001", "path_c_human", True, 65000),
                ],
            },
        }
        gates = evaluate_gates(sections, profile_config("production"))
        self.assertTrue(gates["course_pass"])
        self.assertTrue(gates["production_ready"])
        self.assertEqual(gates["blockers"], [])
        self.assertLess(gates["latency_slo"]["p95_ms"], 30000)

    def test_production_fails_slow_path_a_p95(self) -> None:
        sections = {
            "static": {"pass": True},
            "fixtures": {"pass": True},
            "live": {
                "pass": True,
                "items": [
                    _item("A-001", "path_a_resolve", True, 6216),
                    _item("A-002", "path_a_resolve", True, 68913),
                    _item("A-003", "path_a_resolve", True, 6275),
                ],
            },
        }
        gates = evaluate_gates(sections, profile_config("production"))
        self.assertFalse(gates["course_pass"])
        self.assertFalse(gates["production_ready"])
        self.assertIn("path_a_p95_or_timeout", gates["blockers"])

    def test_offline_production_is_not_ready(self) -> None:
        sections = {"static": {"pass": True}, "fixtures": {"pass": True}}
        gates = evaluate_gates(sections, profile_config("production"))
        self.assertTrue(gates["course_pass"])
        self.assertFalse(gates["production_ready"])
        self.assertIn("live_not_run", gates["blockers"])


if __name__ == "__main__":
    unittest.main()
