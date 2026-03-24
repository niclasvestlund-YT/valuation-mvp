from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.app.schemas.product_identification import VisionServiceError

REPO_ROOT = Path(__file__).resolve().parents[3]
ERROR_LOG_PATH = REPO_ROOT / "logs" / "errors.jsonl"
ERROR_REPORT_PATH = REPO_ROOT / "automation" / "errors" / "latest_error_report.md"
FIX_PROMPT_PATH = REPO_ROOT / "automation" / "errors" / "latest_fix_prompt.md"

STAGE_FILE_HINTS = {
    "upload": [
        "frontend/index.html",
        "backend/app/api/value.py",
    ],
    "image_decode": [
        "backend/app/services/image_preprocess.py",
        "backend/app/services/vision_service.py",
    ],
    "vision": [
        "backend/app/services/vision_service.py",
        "backend/app/schemas/product_identification.py",
    ],
    "market_lookup": [
        "backend/app/services/market_data_service.py",
        "backend/app/integrations/tradera_client.py",
        "backend/app/integrations/serpapi_used_market_client.py",
    ],
    "filtering": [
        "backend/app/services/comparable_scoring.py",
        "backend/app/services/market_data_service.py",
    ],
    "pricing": [
        "backend/app/services/pricing_service.py",
        "backend/app/core/value_engine.py",
    ],
    "response_build": [
        "backend/app/api/value.py",
        "frontend/index.html",
    ],
}

VISION_STAGE_MAP = {
    "no_images_provided": "upload",
    "image_preprocess_failed": "image_decode",
    "missing_openai_api_key": "vision",
    "openai_timeout": "vision",
    "openai_network_error": "vision",
    "openai_retryable_error": "vision",
    "openai_request_failed": "vision",
    "invalid_openai_http_response": "vision",
    "openai_unknown_failure": "vision",
    "invalid_openai_response": "vision",
    "invalid_openai_json": "vision",
}

REASON_STAGE_MAP = {
    "market_lookup_failure": "market_lookup",
    "valuation_pipeline_failure": "pricing",
    "unexpected_pricing_status": "pricing",
    "value_endpoint_failure": "response_build",
    "no_relevant_comparables": "filtering",
    "not_enough_relevant_comparables": "filtering",
    "average_relevance_too_low": "filtering",
    "missing_openai_api_key": "vision",
    "openai_timeout": "vision",
    "openai_network_error": "vision",
    "openai_retryable_error": "vision",
    "openai_request_failed": "vision",
    "invalid_openai_http_response": "vision",
    "openai_unknown_failure": "vision",
    "invalid_openai_response": "vision",
    "invalid_openai_json": "vision",
    "image_preprocess_failed": "image_decode",
    "no_images_provided": "upload",
}


def new_debug_id(prefix: str = "error") -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def build_input_summary(payload: Any) -> dict[str, Any]:
    images = list(getattr(payload, "images", None) or [])
    single_image = getattr(payload, "image", None)
    filename = getattr(payload, "filename", None)
    return {
        "image_count": len(images) + (1 if single_image else 0),
        "has_image_payload": bool(images or single_image),
        "brand_override_present": bool(getattr(payload, "brand", None)),
        "model_override_present": bool(getattr(payload, "model", None)),
        "filename_present": bool(filename),
    }


def infer_error_stage_from_exception(exc: Exception) -> str:
    if isinstance(exc, VisionServiceError):
        return VISION_STAGE_MAP.get(exc.code, "vision")
    return "response_build"


def infer_error_stage_from_payload(payload: dict[str, Any]) -> str:
    for reason in payload.get("reasons", []) or []:
        stage = REASON_STAGE_MAP.get(str(reason))
        if stage:
            return stage

    status = str(payload.get("status") or "")
    if status == "degraded":
        return "pricing"
    if status == "error":
        return "response_build"
    return "response_build"


def attach_error_fields(
    payload: dict[str, Any],
    *,
    error_stage: str,
    technical_message: str | None = None,
) -> dict[str, Any]:
    payload["error_stage"] = error_stage
    payload["user_message"] = payload.get("user_explanation") or payload.get("status_message") or "Något gick fel."

    resolved_technical = technical_message
    if not resolved_technical:
        warnings = [str(warning) for warning in payload.get("warnings", []) if warning]
        if warnings:
            resolved_technical = " | ".join(warnings[:3])

    payload["technical_message"] = trim_text(resolved_technical)
    return payload


def record_error_artifacts(
    *,
    debug_id: str,
    stage: str,
    error_type: str,
    user_message: str,
    technical_message: str | None,
    status: str,
    input_summary: dict[str, Any],
    relevant_filenames: list[str] | None = None,
) -> dict[str, Any]:
    timestamp = datetime.now(UTC).isoformat()
    stage_files = STAGE_FILE_HINTS.get(stage, [])
    deduped_filenames = list(
        dict.fromkeys(
            [name for name in (relevant_filenames or []) if name] + stage_files
        )
    )

    entry = {
        "timestamp": timestamp,
        "debug_id": debug_id,
        "stage": stage,
        "error_type": error_type,
        "user_message": trim_text(user_message),
        "technical_message": trim_text(technical_message),
        "status": status,
        "input_summary": input_summary,
        "relevant_filenames": deduped_filenames,
    }

    error_report = render_error_report(entry)
    fix_prompt = render_fix_prompt(entry)

    ERROR_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with ERROR_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    ERROR_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ERROR_REPORT_PATH.write_text(error_report, encoding="utf-8")
    FIX_PROMPT_PATH.parent.mkdir(parents=True, exist_ok=True)
    FIX_PROMPT_PATH.write_text(fix_prompt, encoding="utf-8")

    return {
        "report_path": relative_path(ERROR_REPORT_PATH),
        "fix_prompt_path": relative_path(FIX_PROMPT_PATH),
        "report_markdown": error_report,
        "fix_prompt_markdown": fix_prompt,
        "relevant_filenames": deduped_filenames,
        "input_summary": input_summary,
        "suggested_investigation": build_suggested_investigation(entry),
    }


def render_error_report(entry: dict[str, Any]) -> str:
    input_summary = entry.get("input_summary") or {}
    reproduction_hints = build_reproduction_hints(entry)
    filenames = entry.get("relevant_filenames") or []
    filename_lines = "\n".join(f"- `{name}`" for name in filenames) or "- `unknown`"
    hint_lines = "\n".join(f"- {hint}" for hint in reproduction_hints) or "- Repeat the failing request once."

    return (
        f"# Latest Error Report\n\n"
        f"- Debug ID: `{entry['debug_id']}`\n"
        f"- Stage: `{entry['stage']}`\n"
        f"- Status: `{entry['status']}`\n"
        f"- Error type: `{entry['error_type']}`\n"
        f"- Timestamp: `{entry['timestamp']}`\n\n"
        f"## User Message\n\n"
        f"{entry['user_message']}\n\n"
        f"## Technical Message\n\n"
        f"{entry.get('technical_message') or 'No technical message captured.'}\n\n"
        f"## Safe Input Summary\n\n"
        f"```json\n{json.dumps(input_summary, ensure_ascii=False, indent=2)}\n```\n\n"
        f"## Reproduction Hints\n\n"
        f"{hint_lines}\n\n"
        f"## Likely Investigation Areas\n\n"
        f"{filename_lines}\n"
    )


def render_fix_prompt(entry: dict[str, Any]) -> str:
    input_summary = entry.get("input_summary") or {}
    reproduction_hints = build_reproduction_hints(entry)
    hint_lines = "\n".join(f"- {hint}" for hint in reproduction_hints) or "- Reproduce the failing request once."
    filenames = entry.get("relevant_filenames") or []
    filename_lines = "\n".join(f"- `{name}`" for name in filenames) or "- `unknown`"

    return (
        "Fix this error in the valuation MVP.\n\n"
        f"User-visible problem:\n- {entry['user_message']}\n\n"
        "Debug context:\n"
        f"- debug_id: `{entry['debug_id']}`\n"
        f"- stage: `{entry['stage']}`\n"
        f"- status: `{entry['status']}`\n"
        f"- technical_message: {entry.get('technical_message') or 'No technical message captured.'}\n\n"
        "Safe reproduction summary:\n"
        f"```json\n{json.dumps(input_summary, ensure_ascii=False, indent=2)}\n```\n\n"
        "Relevant files to inspect:\n"
        f"{filename_lines}\n\n"
        "Suggested investigation area:\n"
        f"- {build_suggested_investigation(entry)}\n\n"
        "Reproduction hints:\n"
        f"{hint_lines}\n\n"
        "Constraints:\n"
        "- Keep the fix lightweight and safe.\n"
        "- Do not log secrets or huge payloads.\n"
        "- Preserve API compatibility unless a small change is clearly necessary.\n\n"
        "Please inspect the failing stage, explain the root cause, implement the smallest safe fix, and summarize changed files and verification.\n"
    )


def build_reproduction_hints(entry: dict[str, Any]) -> list[str]:
    input_summary = entry.get("input_summary") or {}
    hints: list[str] = []
    image_count = input_summary.get("image_count")
    if image_count:
        hints.append(f"Repeat the request with {image_count} uploaded image(s).")
    else:
        hints.append("Repeat the request and confirm whether any image was uploaded.")

    if input_summary.get("brand_override_present") or input_summary.get("model_override_present"):
        hints.append("Check whether manual brand/model override changed the execution path.")

    if input_summary.get("filename_present"):
        hints.append("Use the same file name again to confirm the failure is reproducible.")

    hints.append("Copy this report into Codex and ask it to fix the failing stage.")
    return hints


def build_suggested_investigation(entry: dict[str, Any]) -> str:
    stage = str(entry.get("stage") or "response_build")
    stage_messages = {
        "upload": "Check request validation and missing-image handling between the frontend submit flow and /value route.",
        "image_decode": "Check base64 parsing, MIME handling, HEIC conversion, and Pillow decode/conversion paths.",
        "vision": "Check the vision request, OpenAI response parsing, and retry/error handling in the vision service.",
        "market_lookup": "Check provider queries, network/config handling, normalization, and source availability for market data.",
        "filtering": "Check comparable filtering, relevance scoring, and rejection reasons that may be hiding usable evidence.",
        "pricing": "Check pricing gates, fallback estimate logic, and evidence thresholds in the valuation engine.",
        "response_build": "Check API serialization, envelope enrichment, and frontend error rendering expectations.",
    }
    return stage_messages.get(stage, stage_messages["response_build"])


def trim_text(value: str | None, *, limit: int = 600) -> str | None:
    if value is None:
        return None

    normalized = " ".join(str(value).split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."


def relative_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)
