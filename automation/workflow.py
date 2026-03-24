#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUTOMATION_DIR = ROOT / "automation"
TASK_FILE = AUTOMATION_DIR / "tasks" / "current_task.json"
OUTPUTS_DIR = AUTOMATION_DIR / "outputs"
REVIEWS_DIR = AUTOMATION_DIR / "reviews"
SUMMARIES_DIR = AUTOMATION_DIR / "summaries"
LOGS_DIR = AUTOMATION_DIR / "logs"


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")


def load_task(task_path: Path) -> dict:
    with task_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def ensure_dirs() -> None:
    for path in [OUTPUTS_DIR, REVIEWS_DIR, SUMMARIES_DIR, LOGS_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def task_paths(task_id: str) -> dict[str, Path]:
    return {
        "developer": OUTPUTS_DIR / f"{task_id}__developer.md",
        "qa": REVIEWS_DIR / f"{task_id}__qa.md",
        "manager": SUMMARIES_DIR / f"{task_id}__manager.md",
        "product": SUMMARIES_DIR / f"{task_id}__product.md",
        "summary": SUMMARIES_DIR / f"{task_id}__one_file_summary.md",
        "log": LOGS_DIR / f"{task_id}.log",
    }


def append_log(task_id: str, message: str) -> None:
    log_path = task_paths(task_id)["log"]
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{now_utc()}] {message}\n")


def write_if_missing(path: Path, content: str) -> None:
    if path.exists():
        return
    path.write_text(content, encoding="utf-8")


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def extract_line_value(text: str, label: str) -> str:
    prefix = f"{label}:"
    for line in text.splitlines():
        if line.strip().lower().startswith(prefix.lower()):
            return line.split(":", 1)[1].strip()
    return "pending"


def stop_status(qa_text: str) -> tuple[str, list[str]]:
    verdict = extract_line_value(qa_text, "Verdict").lower()
    trust_violated = extract_line_value(qa_text, "Trust principle violated").lower()
    confidence_drop = extract_line_value(qa_text, "Confidence decreased significantly").lower()

    reasons: list[str] = []
    if verdict == "fail":
        reasons.append("QA verdict = fail")
    if trust_violated in {"yes", "true"}:
        reasons.append("Trust principle violated")
    if confidence_drop in {"yes", "true"}:
        reasons.append("Confidence decreased significantly")

    if reasons:
        return "STOP - human review required", reasons
    return "CLEAR - iteration may continue", []


def developer_template(task: dict) -> str:
    constraints = "\n".join(f"- {item}" for item in task.get("constraints", []))
    return f"""# Developer Output

Task ID: {task["id"]}
Task title: {task["title"]}
Task goal: {task["goal"]}
NORTH_STAR: {task["north_star_path"]}

Constraints:
{constraints or "- None listed"}

Files changed:
- TBD

Implementation summary:
- TBD

Tests run:
- TBD

Result status: pending

Assumptions:
- TBD

Risks:
- TBD
"""


def qa_template(task: dict) -> str:
    return f"""# QA Review

Task ID: {task["id"]}
Task title: {task["title"]}
NORTH_STAR reference: {task["north_star_path"]}
Golden tests: {task["golden_tests_path"]}

What was reviewed:
- TBD

Bugs / edge cases:
- TBD

API compatibility issues:
- TBD

Trust concerns:
- TBD

Trust principle violated: no
Confidence decreased significantly: no

Golden test results:
- Sony WH-1000XM4: TBD
- Sony WH-1000XM5: TBD
- iPhone 13: TBD
- DJI Osmo Action: TBD

Regressions:
- TBD

Test gaps:
- TBD

Verdict: pending

Learning:
- What worked: TBD
- What failed: TBD
- What should be avoided next time: TBD

Impact level: pending
"""


def manager_template(task: dict) -> str:
    return f"""# Manager Summary

Task ID: {task["id"]}
Task title: {task["title"]}
NORTH_STAR reference: {task["north_star_path"]}

Technical summary:
- TBD

QA verdict: pending

Decision: pending

Reason (based on product goals):
- TBD

Risks still open:
- TBD

Does this move the product closer to goals? TBD

EXACT next Codex prompt:
```text
TBD
```

OPTIONAL next ChatGPT prompt:
```text
TBD
```
"""


def product_template(task: dict) -> str:
    return f"""# Plain-Language Product Summary

Task ID: {task["id"]}
Task title: {task["title"]}

What changed:
- TBD

Why it matters:
- TBD

What a user would notice:
- TBD

If the product became better or safer:
- TBD

What is still uncertain:
- TBD

What this unlocks going forward:
- TBD
"""


def build_summary(task: dict) -> str:
    paths = task_paths(task["id"])
    developer = read_text(paths["developer"])
    qa = read_text(paths["qa"])
    manager = read_text(paths["manager"])
    product = read_text(paths["product"])

    developer_status = extract_line_value(developer, "Result status")
    qa_verdict = extract_line_value(qa, "Verdict")
    manager_decision = extract_line_value(manager, "Decision")
    stop_line, stop_reasons = stop_status(qa)
    stop_reason_text = ", ".join(stop_reasons) if stop_reasons else "None"

    return f"""# One-File Summary

Updated: {now_utc()}
Task ID: {task["id"]}
Task title: {task["title"]}
Task file: {TASK_FILE.relative_to(ROOT)}
NORTH_STAR: {task["north_star_path"]}

## At A Glance

- Developer status: {developer_status}
- QA verdict: {qa_verdict}
- Manager decision: {manager_decision}
- Stop status: {stop_line}
- Stop reasons: {stop_reason_text}

## Artifact Paths

- Developer: {paths["developer"].relative_to(ROOT)}
- QA: {paths["qa"].relative_to(ROOT)}
- Manager: {paths["manager"].relative_to(ROOT)}
- Product: {paths["product"].relative_to(ROOT)}

## Developer Output

{developer}

## QA Review

{qa}

## Manager Summary

{manager}

## Plain-Language Product Summary

{product}
"""


def start(task: dict) -> None:
    ensure_dirs()
    paths = task_paths(task["id"])
    write_if_missing(paths["developer"], developer_template(task))
    write_if_missing(paths["qa"], qa_template(task))
    write_if_missing(paths["manager"], manager_template(task))
    write_if_missing(paths["product"], product_template(task))
    paths["summary"].write_text(build_summary(task), encoding="utf-8")
    append_log(task["id"], "start: created or confirmed task artifacts")


def refresh(task: dict) -> None:
    ensure_dirs()
    paths = task_paths(task["id"])
    paths["summary"].write_text(build_summary(task), encoding="utf-8")
    stop_line, stop_reasons = stop_status(read_text(paths["qa"]))
    append_log(task["id"], f"refresh: summary rebuilt | stop_status={stop_line} | reasons={stop_reasons or ['none']}")


def print_paths(task: dict) -> None:
    for name, path in task_paths(task["id"]).items():
        print(f"{name}: {path.relative_to(ROOT)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Minimal local multi-role workflow helper")
    parser.add_argument("command", choices=["start", "refresh", "paths"], nargs="?", default="start")
    parser.add_argument("--task", default=str(TASK_FILE.relative_to(ROOT)), help="Path to the current task JSON file")
    args = parser.parse_args()

    task_path = (ROOT / args.task).resolve()
    task = load_task(task_path)

    if args.command == "start":
        start(task)
    elif args.command == "refresh":
        refresh(task)
    else:
        ensure_dirs()
        print_paths(task)


if __name__ == "__main__":
    main()
