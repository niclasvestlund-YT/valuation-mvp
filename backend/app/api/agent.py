"""Agent chat endpoint — answers from own database only, never external APIs."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.app.core.config import settings
from backend.app.prompts.agent_system import AGENT_SYSTEM_PROMPT
from backend.app.services.agent_service import (
    build_context_block,
    build_no_data_context,
    count_comparables,
    parse_user_intent,
)
from backend.app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


class AgentRequest(BaseModel):
    message: str
    conversation_id: str | None = None


class AgentResponse(BaseModel):
    reply: str
    product_key: str | None = None
    data_source: str = "own_database"
    comparables_count: int = 0
    has_data: bool = False


@router.post("/agent/chat", response_model=AgentResponse)
async def agent_chat(req: AgentRequest):
    if not settings.agent_enabled:
        raise HTTPException(status_code=503, detail="Agent is not enabled")

    logger.info("agent.chat_request", extra={"message": req.message[:100]})

    # Step 1: Find the product in OUR database
    intent = await parse_user_intent(req.message)

    # Step 2: Build context from OUR data only
    if intent.product_key:
        context = await build_context_block(intent.product_key)
        has_data = True
        comps_count = await count_comparables(intent.product_key)
    elif intent.candidates:
        context = await build_no_data_context(req.message, intent.candidates)
        has_data = False
        comps_count = 0
    else:
        context = await build_no_data_context(req.message)
        has_data = False
        comps_count = 0

    # Step 3: Send to LLM with system prompt + context
    system_prompt = AGENT_SYSTEM_PROMPT.replace("{{CONTEXT_BLOCK}}", context)

    if settings.use_mock_agent:
        reply = _mock_reply(intent, has_data, comps_count)
    else:
        reply = await _call_openai(system_prompt, req.message)

    logger.info("agent.chat_response", extra={
        "product_key": intent.product_key,
        "has_data": has_data,
        "comps_count": comps_count,
        "reply_length": len(reply),
    })

    return AgentResponse(
        reply=reply,
        product_key=intent.product_key,
        data_source="own_database",
        comparables_count=comps_count,
        has_data=has_data,
    )


async def _call_openai(system_prompt: str, user_message: str) -> str:
    """Call OpenAI chat API. Uses same key as vision service."""
    import requests

    if not settings.openai_api_key:
        return "Agenten är inte konfigurerad (OpenAI API-nyckel saknas)."

    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.agent_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                "temperature": settings.agent_temperature,
                "max_tokens": settings.agent_max_tokens,
            },
            timeout=settings.openai_timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except Exception as exc:
        logger.error("agent.openai_call_failed", extra={"error": str(exc)})
        return "Kunde inte generera svar just nu. Försök igen."


def _mock_reply(intent, has_data: bool, comps_count: int) -> str:
    """Mock response for testing without OpenAI calls."""
    if has_data:
        return (
            f"**{intent.product_key}**\n"
            f"Begagnat marknadsvärde: baserat på {comps_count} jämförelseobjekt.\n"
            f"Datakälla: own_database"
        )
    if intent.candidates:
        names = ", ".join(c.product_key for c in intent.candidates[:3])
        return f"Menade du kanske: {names}? Förtydliga vilken produkt du menar."
    return "Vi har inte tillräckligt med data för den produkten ännu."
