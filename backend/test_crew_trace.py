"""Tests for CrewAI AMP URL allowlisting and operator-queue mapping."""

from __future__ import annotations

import unittest

from backend.approval_service import _row_to_model, _safe_crew_trace_url
from backend.crew import allowed_crew_trace_url

AMP_URL = "https://app.crewai.com/crewai_plus/trace_batches/abc-123"


class CrewTraceUrlTests(unittest.TestCase):
    def test_allows_amp_dashboard_url(self) -> None:
        self.assertEqual(allowed_crew_trace_url(AMP_URL), AMP_URL)
        self.assertEqual(_safe_crew_trace_url(f"  {AMP_URL}  "), AMP_URL)

    def test_rejects_non_amp_urls(self) -> None:
        for raw in (
            None,
            "",
            "javascript:alert(1)",
            "http://app.crewai.com/crewai_plus/trace_batches/abc",
            "https://evil.example/crewai_plus/trace_batches/abc",
        ):
            with self.subTest(raw=raw):
                self.assertIsNone(allowed_crew_trace_url(raw))
                self.assertIsNone(_safe_crew_trace_url(raw))


class ApprovalRowMappingTests(unittest.TestCase):
    def test_row_includes_trace_fields(self) -> None:
        row = {
            "id": "APR-TEST01",
            "action_kind": "billing_credit",
            "subject_id": "ACC-1001",
            "amount": 25.0,
            "reason": "outage credit",
            "status": "pending",
            "operator_note": None,
            "context_json": "{}",
            "created_at": "2026-09-11T15:00:00+00:00",
            "decided_at": None,
            "decided_by": None,
            "trace_id": "trace-local-1",
            "crew_trace_url": AMP_URL,
        }
        model = _row_to_model(row)
        self.assertEqual(model.trace_id, "trace-local-1")
        self.assertEqual(model.crew_trace_url, AMP_URL)

    def test_row_drops_unsafe_crew_url(self) -> None:
        row = {
            "id": "APR-TEST02",
            "action_kind": "billing_credit",
            "subject_id": "ACC-1001",
            "amount": None,
            "reason": "",
            "status": "pending",
            "operator_note": None,
            "context_json": None,
            "created_at": "2026-09-11T15:00:00+00:00",
            "decided_at": None,
            "decided_by": None,
            "trace_id": None,
            "crew_trace_url": "javascript:alert(1)",
        }
        model = _row_to_model(row)
        self.assertIsNone(model.crew_trace_url)


if __name__ == "__main__":
    unittest.main()
