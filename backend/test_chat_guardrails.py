"""Unit tests for Path B grounding and Path C STUB-* ticket guardrails."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.chat_service import (
    filter_grounded_sources,
    is_valid_stub_ticket_id,
    issue_stub_ticket_id,
    map_to_response,
    sanitize_stub_ticket_id,
)
from backend.models import (
    ChatRequest,
    Citation,
    ClassifierOutput,
    EscalationOutput,
    EscalationPacket,
    ResponseOutput,
    RetrieverOutput,
)


def _task(pydantic: object) -> SimpleNamespace:
    return SimpleNamespace(output=SimpleNamespace(pydantic=pydantic, __str__=lambda self: "ok"))


def _crew_result(
    *,
    intent: str = "warranty",
    urgency: str = "low",
    gap: bool = False,
    refused: bool = False,
    sources: list[Citation] | None = None,
    decision: str = "resolve",
    stub: str | None = "TICKET-12345",
    request_human: bool = False,
    reply: str = "Here is the warranty policy.",
) -> dict:
    citations = sources or [
        Citation(title="Find or download a B-Mobile bill", snippet="PDF invoices"),
    ]
    packet = None
    if decision == "escalate":
        packet = EscalationPacket(
            intent=intent,
            urgency=urgency,  # type: ignore[arg-type]
            customer_message="help",
            request_human=request_human,
            citations_attempted=[],
            draft_reply=reply,
            sentiment="neutral",
            risk="medium",
            reason_codes=["request_human"] if request_human else ["retrieval_gap"],
            stub_ticket_id=stub or "TICKET-12345",
        )
    return {
        "tasks": [
            _task(ClassifierOutput(intent=intent, urgency=urgency, entities=[], confidence=0.9)),  # type: ignore[arg-type]
            _task(RetrieverOutput(passages=[], citations=citations, gap=gap)),
            _task(ResponseOutput(reply=reply, sources_used=citations, refused=refused)),
            _task(
                EscalationOutput(
                    decision=decision,  # type: ignore[arg-type]
                    sentiment="neutral",
                    risk="medium",
                    reason_codes=["request_human"] if request_human else [],
                    packet=packet,
                )
            ),
        ]
    }


class StubTicketTests(unittest.TestCase):
    def test_issue_matches_contract(self) -> None:
        stub = issue_stub_ticket_id()
        self.assertTrue(is_valid_stub_ticket_id(stub))

    def test_rejects_llm_ticket_ids(self) -> None:
        for fake in ("TICKET-12345", "TKT-88231-XYZ", "STUB-C001TEST", "", None):
            with self.subTest(fake=fake):
                out = sanitize_stub_ticket_id(fake)
                self.assertTrue(is_valid_stub_ticket_id(out))
                self.assertNotEqual(out, fake)

    def test_keeps_tool_shaped_id(self) -> None:
        self.assertEqual(sanitize_stub_ticket_id("stub-ab12cd34"), "STUB-AB12CD34")


class GroundingTests(unittest.TestCase):
    def test_gap_drops_all_sources(self) -> None:
        claimed = [Citation(title="Use B-Mobile data roaming abroad", snippet="x")]
        self.assertEqual(filter_grounded_sources(claimed, kb_gap=True, allowed_titles=set()), [])

    def test_keeps_only_allowed_titles(self) -> None:
        claimed = [
            Citation(title="Reset your B-Mobile My Account PIN", snippet="a"),
            Citation(title="Invented quantum warranty", snippet="b"),
        ]
        kept = filter_grounded_sources(
            claimed,
            kb_gap=False,
            allowed_titles={"reset your b-mobile my account pin"},
        )
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].title, "Reset your B-Mobile My Account PIN")


class MapToResponseTests(unittest.TestCase):
    def _map(self, result: dict, req: ChatRequest, trace: str = "trace"):
        with patch(
            "backend.chat_service.lookup_kb_allowed_titles",
            return_value=(True, set()),
        ), patch(
            "backend.approval_service.detect_policy_action",
            return_value=None,
        ):
            return map_to_response(result, trace, req)

    def test_path_b_strips_ungrounded_sources(self) -> None:
        result = _crew_result(decision="resolve", gap=False)
        req = ChatRequest(
            message="What is the warranty on your quantum flux capacitor phone case?",
            request_human=False,
        )
        response = self._map(result, req, "trace-b")
        self.assertFalse(response.decision == "resolve" and len(response.sources_used) > 0)
        self.assertEqual(response.sources_used, [])

    def test_path_c_replaces_hallucinated_ticket_id(self) -> None:
        result = _crew_result(
            decision="escalate",
            stub="STUB-A1B2C3D4",
            request_human=True,
            intent="account_support",
            reply="Connecting you with a person.",
        )
        req = ChatRequest(message="I need help with my account please.", request_human=True)
        response = self._map(result, req, "trace-c")
        self.assertEqual(response.decision, "escalate")
        self.assertTrue(is_valid_stub_ticket_id(response.stub_ticket_id))
        self.assertIsNotNone(response.packet)
        self.assertEqual(response.packet.stub_ticket_id, response.stub_ticket_id)
        self.assertTrue(response.packet.stub_ticket_id.startswith("STUB-"))
        self.assertNotEqual(response.stub_ticket_id, "TICKET-12345")
        self.assertNotEqual(response.stub_ticket_id, "STUB-A1B2C3D4")

    def test_request_human_forces_escalate_even_if_crew_resolved(self) -> None:
        result = _crew_result(decision="resolve", request_human=False)
        req = ChatRequest(message="How do I reset my PIN?", request_human=True)
        response = self._map(result, req, "trace-c2")
        self.assertEqual(response.decision, "escalate")
        self.assertIn("request_human", response.reason_codes)
        self.assertTrue(is_valid_stub_ticket_id(response.stub_ticket_id))
        self.assertIsNotNone(response.packet)


if __name__ == "__main__":
    unittest.main()
