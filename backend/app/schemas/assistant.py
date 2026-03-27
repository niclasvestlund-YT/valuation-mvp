"""Schemas for the VALOR Prisassistent conversation layer.

Purely additive — these models are used as optional fields on
ValueEnvelope and never affect the core valuation pipeline.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class QuickReply(BaseModel):
    """A single quick-reply button the frontend can render."""
    label: str                              # Swedish UI label, e.g. "Ja, det stämmer"
    action: str                             # Machine-readable action id
    payload: dict[str, Any] = Field(default_factory=dict)  # Data to send back


class AssistantContext(BaseModel):
    """Conversation state + next-step guidance attached to every ValueEnvelope."""
    phase: str                              # confirming | correcting | complete | unsupported
    prompt: str                             # Swedish user-facing prompt
    quick_replies: list[QuickReply] = Field(default_factory=list)
    guardrail_message: str | None = None    # Set when request is out of scope
