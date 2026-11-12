"""Evidence-only answer formatting tests."""

import asyncio
from datetime import UTC, datetime

import llm


def test_evidence_formatter_names_person_item_and_time():
    answer = llm._format_evidence_response([
        {
            "event_type": "object_picked_up",
            "timestamp": datetime(2026, 11, 11, 16, 30, tzinfo=UTC),
            "person_label": "John",
            "object_category": "keys",
            "location_label": "kitchen",
        }
    ])
    assert answer == "At 04:30 PM, John picked up keys at kitchen."


def test_synthesis_falls_back_to_recorded_evidence(monkeypatch):
    async def unavailable(system: str, user: str) -> str:
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(llm, "_complete", unavailable)
    answer = asyncio.run(
        llm.synthesize_response(
            "who picked up my keys?",
            [{
                "event_type": "object_picked_up",
                "timestamp": datetime(2026, 11, 11, 16, 30, tzinfo=UTC),
                "person_label": "John",
                "object_label": "blue keys",
                "location_label": "kitchen",
            }],
        )
    )
    assert "John picked up blue keys" in answer


def test_completion_fails_closed_without_available_provider(monkeypatch):
    async def unavailable(system: str, user: str) -> str:
        raise RuntimeError("ollama unavailable")

    async def openai_unavailable(system: str, user: str) -> str:
        raise RuntimeError("openai unavailable")

    monkeypatch.setattr(llm, "_ollama_complete", unavailable)
    monkeypatch.setattr(llm, "_openai_complete", openai_unavailable)
    monkeypatch.setattr(llm, "_OPENAI_KEY", "# fallback disabled")

    try:
        asyncio.run(llm._complete("system", "user"))
    except RuntimeError as exc:
        assert "Ollama unavailable" in str(exc)
    else:
        raise AssertionError("completion should fail closed")
