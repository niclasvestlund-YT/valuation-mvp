#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUTOMATION_DIR = ROOT / "automation"
TASK_FILE = AUTOMATION_DIR / "tasks" / "current_task.json"
DECISIONS_FILE = AUTOMATION_DIR / "history" / "DECISIONS.md"
IMPROVEMENTS_FILE = AUTOMATION_DIR / "history" / "IMPROVEMENTS.md"
OUTPUTS_DIR = AUTOMATION_DIR / "outputs"
REVIEWS_DIR = AUTOMATION_DIR / "reviews"
SUMMARIES_DIR = AUTOMATION_DIR / "summaries"
LOGS_DIR = AUTOMATION_DIR / "logs"

PLACEHOLDERS = {
    "",
    "tbd",
    "pending",
    "none",
    "n/a",
    "na",
    "not recorded",
}
ACCEPT_DECISIONS = {"accept", "accept with follow-up"}


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")


def today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def load_task(task_path: Path) -> dict:
    with task_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def task_paths(task_id: str) -> dict[str, Path]:
    return {
        "developer": OUTPUTS_DIR / f"{task_id}__developer.md",
        "qa": REVIEWS_DIR / f"{task_id}__qa.md",
        "manager": SUMMARIES_DIR / f"{task_id}__manager.md",
        "product": SUMMARIES_DIR / f"{task_id}__product.md",
        "summary": SUMMARIES_DIR / f"{task_id}__one_file_summary.md",
        "log": LOGS_DIR / f"{task_id}.log",
    }


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def extract_line_value(text: str, label: str) -> str:
    prefix = f"{label}:"
    for line in text.splitlines():
        stripped = line.strip()
        # Support "- Label: value" bullet format in addition to "Label: value"
        if stripped.startswith("- "):
            stripped = stripped[2:].strip()
        if stripped.lower().startswith(prefix.lower()):
            return stripped.split(":", 1)[1].strip()
    return ""


def extract_section_bullets(text: str, heading: str) -> list[str]:
    lines = text.splitlines()
    target = f"{heading}:".lower()
    capture = False
    bullets: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not capture and stripped.lower() == target:
            capture = True
            continue

        if not capture:
            continue

        if stripped.startswith("- "):
            bullets.append(stripped[2:].strip())
            continue

        if not stripped:
            if bullets:
                break
            continue

        if bullets:
            break

    return bullets


def is_meaningful(value: str) -> bool:
    return value.strip().lower() not in PLACEHOLDERS


def meaningful_items(values: list[str]) -> list[str]:
    return [value for value in values if is_meaningful(value)]


def meaningful_labeled_items(values: list[str]) -> list[str]:
    kept: list[str] = []
    for value in values:
        if ":" not in value:
            if is_meaningful(value):
                kept.append(value)
            continue

        label, item_value = value.split(":", 1)
        if is_meaningful(item_value):
            kept.append(f"{label.strip()}: {item_value.strip()}")

    return kept


def append_if_missing(path: Path, task_id: str, entry: str) -> bool:
    existing = read_text(path)
    marker = f"- Task ID: {task_id}"
    if marker in existing:
        return False

    with path.open("a", encoding="utf-8") as handle:
        if existing and not existing.endswith("\n"):
            handle.write("\n")
        if existing and not existing.endswith("\n\n"):
            handle.write("\n")
        handle.write(entry.rstrip() + "\n")
    return True


def build_decision_entry(task: dict, manager_text: str, qa_text: str) -> str:
    decision = extract_line_value(manager_text, "Decision") or "pending"
    impact = extract_line_value(qa_text, "Impact level") or "pending"
    qa_verdict = extract_line_value(qa_text, "Verdict") or "pending"
    summary_lines = meaningful_items(extract_section_bullets(manager_text, "Technical summary"))
    summary = "; ".join(summary_lines) if summary_lines else "See task artifacts for technical summary."
    follow_up_lines = meaningful_items(extract_section_bullets(manager_text, "Risks still open"))
    follow_up = "; ".join(follow_up_lines) if follow_up_lines else "None"

    return f"""## {today_utc()} - {task["id"]}
- Task ID: {task["id"]}
- Task: {task["title"]}
- Decision: {decision}
- Impact: {impact}
- QA verdict: {qa_verdict}
- Summary of change: {summary}
- Follow-up: {follow_up}
"""


def build_improvement_entry(task: dict, manager_text: str, qa_text: str) -> str | None:
    impact = (extract_line_value(qa_text, "Impact level") or "pending").lower()
    decision = (extract_line_value(manager_text, "Decision") or "pending").lower()
    worked = extract_line_value(qa_text, "What worked")
    failed = extract_line_value(qa_text, "What failed")
    avoid = extract_line_value(qa_text, "What should be avoided next time")
    risks = meaningful_items(extract_section_bullets(manager_text, "Risks still open"))

    observations = meaningful_items([failed, avoid, *risks])
    if not observations:
        return None

    should_append = impact == "high" or decision == "accept with follow-up"
    if not should_append:
        repeated = read_text(IMPROVEMENTS_FILE)
        should_append = any(observation in repeated for observation in observations)
    if not should_append:
        return None

    worked_text = worked if is_meaningful(worked) else "Not recorded"
    observation_text = "; ".join(observations)
    return f"""## {today_utc()} - {task["id"]}
- Task ID: {task["id"]}
- Idea: Review and improve the weak point surfaced by this task close-out.
- Experiment: {task["title"]}
- Observation: {observation_text}
- Potential impact: {impact}
- Status: open
- Supporting learning: {worked_text}
"""


def append_log(task_id: str, payload: dict) -> None:
    log_path = task_paths(task_id)["log"]
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{now_utc()}] close: {json.dumps(payload, ensure_ascii=False)}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Close out the current task and append durable history")
    parser.add_argument("--task", default=str(TASK_FILE.relative_to(ROOT)), help="Path to current task JSON")
    args = parser.parse_args()

    task = load_task((ROOT / args.task).resolve())
    paths = task_paths(task["id"])
    qa_text = read_text(paths["qa"])
    manager_text = read_text(paths["manager"])

    decision = extract_line_value(manager_text, "Decision") or "pending"
    qa_verdict = extract_line_value(qa_text, "Verdict") or "pending"
    impact = extract_line_value(qa_text, "Impact level") or "pending"
    golden_tests = meaningful_labeled_items(extract_section_bullets(qa_text, "Golden test results"))
    regressions = meaningful_items(extract_section_bullets(qa_text, "Regressions"))

    # Block close-out when golden tests are still all TBD placeholders
    raw_golden = extract_section_bullets(qa_text, "Golden test results")
    if raw_golden and not golden_tests:
        print("ERROR: Golden test results are all TBD or placeholders. Fill them in before closing.")
        raise SystemExit(1)

    decision_saved = False
    improvements_saved = False

    if decision.lower() in ACCEPT_DECISIONS:
        decision_entry = build_decision_entry(task, manager_text, qa_text)
        decision_saved = append_if_missing(DECISIONS_FILE, task["id"], decision_entry)

        improvement_entry = build_improvement_entry(task, manager_text, qa_text)
        if improvement_entry:
            improvements_saved = append_if_missing(IMPROVEMENTS_FILE, task["id"], improvement_entry)

    append_log(
        task["id"],
        {
            "task_id": task["id"],
            "decision": decision,
            "qa_verdict": qa_verdict,
            "impact": impact,
            "golden_tests": golden_tests,
            "regressions": regressions,
        },
    )

    print(f"task_id={task['id']}")
    print(f"decision={decision}")
    print(f"qa_verdict={qa_verdict}")
    print(f"impact={impact}")
    print(f"decision_saved={decision_saved}")
    print(f"improvements_saved={improvements_saved}")
    print(f"decisions_file={DECISIONS_FILE.relative_to(ROOT)}")
    print(f"improvements_file={IMPROVEMENTS_FILE.relative_to(ROOT)}")
    print(f"log_file={paths['log'].relative_to(ROOT)}")
    print(f"golden_tests={golden_tests or ['not recorded']}")
    print(f"regressions={regressions or ['none recorded']}")


if __name__ == "__main__":
    main()
