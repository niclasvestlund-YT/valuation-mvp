#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic

ROOT = Path(__file__).resolve().parents[1]
AUTOMATION_DIR = ROOT / "automation"
DEFAULT_CONFIG_PATH = AUTOMATION_DIR / "review_swarm_config.json"
REVIEW_RUNS_DIR = AUTOMATION_DIR / "review_runs"
LATEST_POINTER = REVIEW_RUNS_DIR / "LATEST"

PLACEHOLDER_VALUES = {
    "",
    "tbd",
    "pending",
    "not recorded",
}

ARTIFACT_TEMPLATES = {
    "developer_output.md": """# Developer Output

Run ID: {run_id}
Task ID: {task_id}
Task title: {task_title}

Files reviewed:
- TBD

Implementation risks:
- TBD

Testability / coupling concerns:
- TBD

Missing tests:
- TBD

Result status: pending

Assumptions:
- TBD

Risks:
- TBD
""",
    "qa_review.md": """# QA Review

Run ID: {run_id}
Task ID: {task_id}
Task title: {task_title}

What was reviewed:
- TBD

Bugs / edge cases:
- TBD

API compatibility issues:
- TBD

Trust concerns:
- TBD

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
""",
    "trust_review.md": """# Trust Review

Run ID: {run_id}
Task ID: {task_id}
Task title: {task_title}

Risk areas reviewed:
- TBD

Potential bad-valuation paths:
- TBD

Refusal / uncertainty regressions:
- TBD

Model confusion risks:
- TBD

Evidence-quality concerns:
- TBD

Verdict: pending
""",
    "manager_summary.md": """# Manager Summary

Run ID: {run_id}
Task ID: {task_id}
Task title: {task_title}

Technical summary:
- TBD

Decision: pending

Reason:
- TBD

Risks still open:
- TBD

EXACT next Codex prompt:
```text
TBD
```
""",
    "product_summary.md": """# Plain-Language Product Summary

Run ID: {run_id}
Task ID: {task_id}
Task title: {task_title}

What changed:
- TBD

Why it matters:
- TBD

What is still uncertain:
- TBD
""",
}


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")


def run_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ")


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "run"


def relative_path(path: Path) -> str:
    return str(path.relative_to(ROOT))


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def safe_read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, payload: dict | list) -> None:
    write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def coerce_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def git_output(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    stdout = (completed.stdout or "").rstrip("\n")
    stderr = (completed.stderr or "").rstrip("\n")
    if stdout:
        return stdout
    if stderr:
        return stderr
    return ""


def changed_files_from_status(status_text: str) -> list[str]:
    files: list[str] = []
    for line in status_text.splitlines():
        if not line.strip():
            continue
        if len(line) > 3:
            files.append(line[3:].strip())
    return files


def artifact_status(path: Path) -> str:
    text = safe_read_text(path).strip()
    if not text:
        return "missing"
    lowered = text.lower()
    if any(marker in lowered for marker in ["verdict: pending", "decision: pending", "result status: pending"]):
        return "pending"
    if "tbd" in lowered:
        return "pending"
    return "filled"


def build_run_id(label: str) -> str:
    return f"{run_stamp()}__{slugify(label)}"


def build_run_paths(run_id: str) -> dict[str, Path]:
    run_dir = REVIEW_RUNS_DIR / run_id
    return {
        "run_dir": run_dir,
        "repo_dir": run_dir / "repo",
        "checks_dir": run_dir / "checks",
        "prompts_dir": run_dir / "prompts",
        "artifacts_dir": run_dir / "artifacts",
        "agent_runs_dir": run_dir / "agent_runs",
        "manifest": run_dir / "manifest.json",
        "summary": run_dir / "one_file_summary.md",
    }


def should_ignore_path(path: str, ignore_prefixes: list[str]) -> bool:
    normalized = path.strip()
    return any(normalized == prefix.rstrip("/") or normalized.startswith(prefix) for prefix in ignore_prefixes)


def filter_changed_files(paths: list[str], ignore_prefixes: list[str]) -> list[str]:
    return [path for path in paths if not should_ignore_path(path, ignore_prefixes)]


def initialize_artifacts(paths: dict[str, Path], roles: list[dict], task: dict, run_id: str) -> dict[str, str]:
    artifact_rel_paths: dict[str, str] = {}
    for role in roles:
        artifact_name = role["artifact"]
        artifact_path = paths["artifacts_dir"] / artifact_name
        if not artifact_path.exists():
            template = ARTIFACT_TEMPLATES.get(
                artifact_name,
                "# Review Artifact\n\nRun ID: {run_id}\nTask ID: {task_id}\nTask title: {task_title}\n\nStatus: pending\n",
            )
            write_text(
                artifact_path,
                template.format(
                    run_id=run_id,
                    task_id=task.get("id", "no_task"),
                    task_title=task.get("title", "No task title"),
                ),
            )
        artifact_rel_paths[artifact_name] = relative_path(artifact_path)
    return artifact_rel_paths


def run_check(check: dict, checks_dir: Path) -> dict:
    started_at = now_utc()
    started_monotonic = monotonic()
    command = list(check["command"])
    log_path = checks_dir / f"{check['id']}.log"

    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        exit_code = completed.returncode
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
    except FileNotFoundError as exc:
        exit_code = 127
        stdout = ""
        stderr = str(exc)

    duration_ms = int((monotonic() - started_monotonic) * 1000)
    log_body = "\n".join(
        [
            f"$ {' '.join(command)}",
            "",
            stdout.rstrip(),
            stderr.rstrip(),
        ]
    ).strip() + "\n"
    write_text(log_path, log_body)

    return {
        "id": check["id"],
        "description": check["description"],
        "command": command,
        "allow_failure": bool(check.get("allow_failure", False)),
        "started_at": started_at,
        "duration_ms": duration_ms,
        "exit_code": exit_code,
        "success": exit_code == 0,
        "log_path": relative_path(log_path),
    }


def build_prompt(role: dict, *, run_id: str, task: dict, changed_files: list[str], check_results: list[dict], paths: dict[str, Path]) -> str:
    focus_lines = "\n".join(f"- {item}" for item in role.get("focus", [])) or "- None"
    changed_lines = "\n".join(f"- {item}" for item in changed_files[:30]) or "- No working tree changes detected"
    check_lines = "\n".join(
        f"- {item['id']}: {'PASS' if item['success'] else 'FAIL'}"
        f" (allow_failure={str(item['allow_failure']).lower()}, log={item['log_path']})"
        for item in check_results
    ) or "- No checks were run"
    artifact_path = paths["artifacts_dir"] / role["artifact"]
    summary_path = paths["summary"]
    manifest_path = paths["manifest"]

    return (
        f"# {role['title']} Prompt\n\n"
        f"Run ID: {run_id}\n"
        f"Task ID: {task.get('id', 'no_task')}\n"
        f"Task title: {task.get('title', 'No task title')}\n"
        f"Created: {now_utc()}\n\n"
        f"## Mission\n\n"
        f"Act as `{role['title']}` for this repository's review swarm.\n"
        f"Your final answer will be saved to `{relative_path(artifact_path)}` by the local runner.\n\n"
        f"## Focus\n\n"
        f"{focus_lines}\n\n"
        f"## Changed Files\n\n"
        f"{changed_lines}\n\n"
        f"## Local Check Results\n\n"
        f"{check_lines}\n\n"
        f"## Shared Context\n\n"
        f"- Manifest: `{relative_path(manifest_path)}`\n"
        f"- One-file summary: `{relative_path(summary_path)}`\n"
        f"- NORTH_STAR: `{task.get('north_star_path', 'not provided')}`\n"
        f"- Golden tests: `{task.get('golden_tests_path', 'not provided')}`\n\n"
        f"## Output Requirements\n\n"
        f"- Put findings first.\n"
        f"- Keep the review concrete and file-referenced.\n"
        f"- Highlight correctness, regressions, trust risks, and missing tests.\n"
        f"- If no findings exist, say that explicitly and note residual risks.\n"
        f"- Return only the artifact content in your final answer.\n"
        f"- Do not modify repository files.\n"
    )


def build_summary(
    *,
    run_id: str,
    label: str,
    task: dict,
    changed_files: list[str],
    check_results: list[dict],
    paths: dict[str, Path],
    roles: list[dict],
    runner_state: dict | None = None,
) -> str:
    required_failures = [item for item in check_results if not item["success"] and not item["allow_failure"]]
    optional_failures = [item for item in check_results if not item["success"] and item["allow_failure"]]
    runner_execution = (runner_state or {}).get("last_execution", {})
    runner_results = runner_execution.get("results", [])

    check_lines = "\n".join(
        f"- {item['id']}: {'PASS' if item['success'] else 'FAIL'}"
        f" | allow_failure={str(item['allow_failure']).lower()}"
        f" | duration_ms={item['duration_ms']}"
        f" | log={item['log_path']}"
        for item in check_results
    ) or "- No checks were run"

    artifact_lines = "\n".join(
        f"- {role['artifact']}: {relative_path(paths['artifacts_dir'] / role['artifact'])}"
        f" ({artifact_status(paths['artifacts_dir'] / role['artifact'])})"
        for role in roles
    )
    runner_lines = "\n".join(
        f"- {item['role_id']}: {item['status']}"
        f" | artifact_written={str(item.get('artifact_written', False)).lower()}"
        f" | duration_ms={item.get('duration_ms', 0)}"
        f" | log={item.get('process_log_path', 'not recorded')}"
        for item in runner_results
    ) or "- Reviewers have not been executed for this run"

    changed_lines = "\n".join(f"- {path}" for path in changed_files[:30]) or "- No working tree changes detected"
    required_status = "PASS" if not required_failures else "FAIL"
    optional_status = "PASS" if not optional_failures else "WARN"

    return (
        f"# Review Swarm Summary\n\n"
        f"Updated: {now_utc()}\n"
        f"Run ID: {run_id}\n"
        f"Label: {label}\n"
        f"Task ID: {task.get('id', 'no_task')}\n"
        f"Task title: {task.get('title', 'No task title')}\n\n"
        f"## At A Glance\n\n"
        f"- Required checks: {required_status}\n"
        f"- Optional checks: {optional_status}\n"
        f"- Changed files count: {len(changed_files)}\n"
        f"- Manifest: {relative_path(paths['manifest'])}\n\n"
        f"## Changed Files\n\n"
        f"{changed_lines}\n\n"
        f"## Check Results\n\n"
        f"{check_lines}\n\n"
        f"## Reviewer Artifacts\n\n"
        f"{artifact_lines}\n\n"
        f"## Reviewer Execution\n\n"
        f"- Provider: {(runner_state or {}).get('provider', 'not configured')}\n"
        f"- Last executed at: {runner_execution.get('executed_at', 'not executed')}\n"
        f"- Requested roles: {', '.join(runner_execution.get('requested_roles', [])) or 'none'}\n"
        f"{runner_lines}\n\n"
        f"## Next Step\n\n"
        f"- Run the prompt files in `{relative_path(paths['prompts_dir'])}` with your preferred reviewer workflow, or use `automation/review_swarm.py execute --run-dir {relative_path(paths['run_dir'])}`.\n"
        f"- Keep this run directory append-only.\n"
        f"- Re-run `automation/review_swarm.py summarize --run-dir {relative_path(paths['run_dir'])}` after reviewers fill the artifacts.\n"
    )


def create_repo_snapshot(repo_dir: Path, ignore_prefixes: list[str]) -> list[str]:
    status_short = git_output("status", "--short")
    diff_stat = git_output("diff", "--stat")
    changed_files_text = git_output("status", "--short")
    filtered_files = filter_changed_files(changed_files_from_status(status_short), ignore_prefixes)
    write_text(repo_dir / "git_status.txt", status_short + ("\n" if status_short else ""))
    write_text(repo_dir / "diff_stat.txt", diff_stat + ("\n" if diff_stat else ""))
    write_text(repo_dir / "changed_files.txt", changed_files_text + ("\n" if changed_files_text else ""))
    write_text(
        repo_dir / "changed_files_filtered.txt",
        ("\n".join(filtered_files) + "\n") if filtered_files else "",
    )
    return filtered_files


def parse_role_ids(raw_value: str | None) -> list[str] | None:
    if not raw_value:
        return None
    roles = [item.strip() for item in raw_value.split(",") if item.strip()]
    return roles or None


def select_roles(roles: list[dict], requested_role_ids: list[str] | None) -> list[dict]:
    if not requested_role_ids:
        return roles

    role_map = {role["id"]: role for role in roles}
    selected: list[dict] = []
    missing: list[str] = []
    seen: set[str] = set()

    for role_id in requested_role_ids:
        role = role_map.get(role_id)
        if role is None:
            missing.append(role_id)
            continue
        if role_id in seen:
            continue
        seen.add(role_id)
        selected.append(role)

    if missing:
        raise SystemExit(f"Unknown role ids: {', '.join(missing)}")

    return selected


def run_codex_reviewer(
    *,
    role: dict,
    role_config: dict,
    prompt_path: Path,
    artifact_path: Path,
    agent_run_dir: Path,
    timeout_seconds: int,
    runner_config: dict,
) -> dict:
    started_at = now_utc()
    started_monotonic = monotonic()
    output_path = agent_run_dir / "response.md"
    stdout_path = agent_run_dir / "stdout.log"
    stderr_path = agent_run_dir / "stderr.log"
    process_log_path = agent_run_dir / "process.log"
    prompt_text = safe_read_text(prompt_path)

    command = [
        runner_config.get("binary", "codex"),
        "exec",
        "--sandbox",
        runner_config.get("sandbox", "read-only"),
        "--color",
        "never",
        "--ephemeral",
        "-C",
        str(ROOT),
        "-o",
        str(output_path),
    ]
    model = role_config.get("model") or runner_config.get("default_model")
    reasoning_effort = role_config.get("reasoning_effort") or runner_config.get("default_reasoning_effort")
    if model:
        command.extend(["-m", model])
    if reasoning_effort:
        command.extend(["-c", f'model_reasoning_effort="{reasoning_effort}"'])
    command.append("-")

    env = os.environ.copy()
    status = "failed"
    exit_code: int | None = None
    stdout = ""
    stderr = ""
    error = ""

    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            input=prompt_text,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
            env=env,
        )
        exit_code = completed.returncode
        stdout = coerce_text(completed.stdout)
        stderr = coerce_text(completed.stderr)
        status = "success" if exit_code == 0 else "failed"
    except FileNotFoundError as exc:
        exit_code = 127
        error = str(exc)
        stderr = error
        status = "missing_binary"
    except subprocess.TimeoutExpired as exc:
        stdout = coerce_text(exc.stdout)
        stderr = coerce_text(exc.stderr)
        error = f"Timed out after {timeout_seconds}s"
        status = "timeout"

    write_text(stdout_path, stdout)
    write_text(stderr_path, stderr)
    process_log = "\n".join(
        [
            f"started_at={started_at}",
            f"role_id={role['id']}",
            f"command={json.dumps(command)}",
            f"timeout_seconds={timeout_seconds}",
            f"status={status}",
            f"exit_code={exit_code if exit_code is not None else 'none'}",
            f"stdout_path={relative_path(stdout_path)}",
            f"stderr_path={relative_path(stderr_path)}",
            f"output_path={relative_path(output_path)}",
            f"error={error or 'none'}",
        ]
    ) + "\n"
    write_text(process_log_path, process_log)

    output_text = safe_read_text(output_path)
    artifact_written = False
    if status == "success":
        if output_text.strip():
            shutil.copyfile(output_path, artifact_path)
            artifact_written = True
        else:
            status = "empty_output"
            error = "Codex returned success but no final message was captured"

    duration_ms = int((monotonic() - started_monotonic) * 1000)
    return {
        "role_id": role["id"],
        "title": role["title"],
        "status": status,
        "exit_code": exit_code,
        "duration_ms": duration_ms,
        "timeout_seconds": timeout_seconds,
        "started_at": started_at,
        "artifact_path": relative_path(artifact_path),
        "artifact_written": artifact_written,
        "prompt_path": relative_path(prompt_path),
        "output_path": relative_path(output_path),
        "stdout_path": relative_path(stdout_path),
        "stderr_path": relative_path(stderr_path),
        "process_log_path": relative_path(process_log_path),
        "error": error or None,
        "command": command,
        "model": model,
        "reasoning_effort": reasoning_effort,
    }


def execute_reviewers(
    *,
    run_dir: Path,
    requested_role_ids: list[str] | None,
    timeout_override_seconds: int | None,
) -> dict:
    manifest_path = run_dir / "manifest.json"
    manifest = load_json(manifest_path)
    config = load_json(ROOT / manifest["config_path"])
    runner_config = config.get("agent_runner", {})
    roles = select_roles(config.get("roles", []), requested_role_ids)
    paths = build_run_paths(manifest["run_id"])
    ensure_dir(paths["agent_runs_dir"])

    provider = runner_config.get("provider", "not_configured")
    execution = {
        "executed_at": now_utc(),
        "requested_roles": [role["id"] for role in roles],
        "results": [],
    }

    for role in roles:
        role_config = runner_config.get("roles", {}).get(role["id"], {})
        if not runner_config.get("enabled", False):
            result = {
                "role_id": role["id"],
                "title": role["title"],
                "status": "skipped",
                "artifact_written": False,
                "duration_ms": 0,
                "prompt_path": relative_path(paths["prompts_dir"] / f"{role['id']}.md"),
                "artifact_path": relative_path(paths["artifacts_dir"] / role["artifact"]),
                "process_log_path": "not recorded",
                "error": "agent_runner.enabled is false in config",
            }
        elif provider != "codex_exec":
            result = {
                "role_id": role["id"],
                "title": role["title"],
                "status": "skipped",
                "artifact_written": False,
                "duration_ms": 0,
                "prompt_path": relative_path(paths["prompts_dir"] / f"{role['id']}.md"),
                "artifact_path": relative_path(paths["artifacts_dir"] / role["artifact"]),
                "process_log_path": "not recorded",
                "error": f"Unsupported agent_runner.provider: {provider}",
            }
        elif not role_config.get("enabled", True):
            result = {
                "role_id": role["id"],
                "title": role["title"],
                "status": "skipped",
                "artifact_written": False,
                "duration_ms": 0,
                "prompt_path": relative_path(paths["prompts_dir"] / f"{role['id']}.md"),
                "artifact_path": relative_path(paths["artifacts_dir"] / role["artifact"]),
                "process_log_path": "not recorded",
                "error": "role is disabled in config",
            }
        else:
            timestamp = run_stamp()
            agent_run_dir = paths["agent_runs_dir"] / f"{timestamp}__{role['id']}"
            ensure_dir(agent_run_dir)
            timeout_seconds = timeout_override_seconds or int(
                role_config.get("timeout_seconds")
                or runner_config.get("default_timeout_seconds", 600)
            )
            result = run_codex_reviewer(
                role=role,
                role_config=role_config,
                prompt_path=paths["prompts_dir"] / f"{role['id']}.md",
                artifact_path=paths["artifacts_dir"] / role["artifact"],
                agent_run_dir=agent_run_dir,
                timeout_seconds=timeout_seconds,
                runner_config=runner_config,
            )
            write_json(agent_run_dir / "result.json", result)

        execution["results"].append(result)

    runner_state = manifest.get("runner", {})
    history = list(runner_state.get("history", []))
    history.append(execution)
    manifest["runner"] = {
        "provider": provider,
        "history": history,
        "last_execution": execution,
    }
    write_json(manifest_path, manifest)
    summarize_run(run_dir)
    return manifest["runner"]


def run_swarm(label: str, config_path: Path, skip_checks: bool) -> Path:
    config = load_json(config_path)
    task_path = ROOT / config.get("task_file", "automation/tasks/current_task.json")
    snapshot_config = config.get("snapshot", {})
    ignore_prefixes = list(snapshot_config.get("ignore_prefixes", []))
    task = load_json(task_path) if task_path.exists() else {
        "id": "no_task",
        "title": "No task file found",
        "north_star_path": "",
        "golden_tests_path": "",
    }

    run_id = build_run_id(label)
    paths = build_run_paths(run_id)
    for key in ["run_dir", "repo_dir", "checks_dir", "prompts_dir", "artifacts_dir", "agent_runs_dir"]:
        ensure_dir(paths[key])

    changed_files = create_repo_snapshot(paths["repo_dir"], ignore_prefixes)
    check_results = []
    if not skip_checks:
        for check in config.get("checks", []):
            result = run_check(check, paths["checks_dir"])
            write_text(paths["checks_dir"] / f"{check['id']}.json", json.dumps(result, ensure_ascii=False, indent=2) + "\n")
            check_results.append(result)

    roles = config.get("roles", [])
    artifact_rel_paths = initialize_artifacts(paths, roles, task, run_id)

    prompt_rel_paths: dict[str, str] = {}
    for role in roles:
        prompt_path = paths["prompts_dir"] / f"{role['id']}.md"
        prompt_text = build_prompt(
            role,
            run_id=run_id,
            task=task,
            changed_files=changed_files,
            check_results=check_results,
            paths=paths,
        )
        write_text(prompt_path, prompt_text)
        prompt_rel_paths[role["id"]] = relative_path(prompt_path)

    summary_text = build_summary(
        run_id=run_id,
        label=label,
        task=task,
        changed_files=changed_files,
        check_results=check_results,
        paths=paths,
        roles=roles,
        runner_state=None,
    )
    write_text(paths["summary"], summary_text)

    manifest = {
        "version": 1,
        "created_at": now_utc(),
        "run_id": run_id,
        "label": label,
        "task": {
            "id": task.get("id"),
            "title": task.get("title"),
            "goal": task.get("goal"),
            "north_star_path": task.get("north_star_path"),
            "golden_tests_path": task.get("golden_tests_path"),
            "constraints": task.get("constraints", []),
        },
        "config_path": relative_path(config_path),
        "repo_snapshot": {
            "git_status_path": relative_path(paths["repo_dir"] / "git_status.txt"),
            "diff_stat_path": relative_path(paths["repo_dir"] / "diff_stat.txt"),
            "changed_files_path": relative_path(paths["repo_dir"] / "changed_files.txt"),
            "changed_files_filtered_path": relative_path(paths["repo_dir"] / "changed_files_filtered.txt"),
            "changed_files": changed_files,
        },
        "checks": check_results,
        "prompts": prompt_rel_paths,
        "artifacts": artifact_rel_paths,
        "runner": {
            "provider": config.get("agent_runner", {}).get("provider", "not_configured"),
            "history": [],
            "last_execution": {},
        },
        "summary_path": relative_path(paths["summary"]),
    }
    write_json(paths["manifest"], manifest)
    write_text(LATEST_POINTER, f"{relative_path(paths['run_dir'])}\n")

    return paths["run_dir"]


def summarize_run(run_dir: Path) -> Path:
    manifest_path = run_dir / "manifest.json"
    manifest = load_json(manifest_path)
    paths = {
        "run_dir": run_dir,
        "artifacts_dir": run_dir / "artifacts",
        "prompts_dir": run_dir / "prompts",
        "manifest": manifest_path,
        "summary": run_dir / "one_file_summary.md",
    }
    config = load_json(ROOT / manifest["config_path"])
    roles = config.get("roles", [])
    summary_text = build_summary(
        run_id=manifest["run_id"],
        label=manifest["label"],
        task=manifest["task"],
        changed_files=manifest.get("repo_snapshot", {}).get("changed_files", []),
        check_results=manifest.get("checks", []),
        paths=paths,
        roles=roles,
        runner_state=manifest.get("runner"),
    )
    write_text(paths["summary"], summary_text)
    return paths["summary"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a local review swarm scaffold for recurring code reviews.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Create a new append-only review run.")
    run_parser.add_argument("--label", default="nightly", help="Short label for the run, for example nightly or pre_merge.")
    run_parser.add_argument(
        "--config",
        default=relative_path(DEFAULT_CONFIG_PATH),
        help="Path to review swarm config JSON, relative to repo root.",
    )
    run_parser.add_argument("--skip-checks", action="store_true", help="Create prompts/artifacts without executing local checks.")
    run_parser.add_argument("--execute-reviewers", action="store_true", help="Run the configured local reviewer CLI after creating the run.")
    run_parser.add_argument("--roles", help="Comma-separated subset of role ids to execute.")
    run_parser.add_argument("--timeout-seconds", type=int, help="Override reviewer timeout for this invocation.")

    summarize_parser = subparsers.add_parser("summarize", help="Rebuild the one-file summary for an existing run.")
    summarize_parser.add_argument("--run-dir", required=True, help="Path to the run directory, relative to repo root.")

    execute_parser = subparsers.add_parser("execute", help="Execute reviewer prompts for an existing run.")
    execute_parser.add_argument("--run-dir", required=True, help="Path to the run directory, relative to repo root.")
    execute_parser.add_argument("--roles", help="Comma-separated subset of role ids to execute.")
    execute_parser.add_argument("--timeout-seconds", type=int, help="Override reviewer timeout for this invocation.")

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "run":
        config_path = (ROOT / args.config).resolve()
        run_dir = run_swarm(label=args.label, config_path=config_path, skip_checks=args.skip_checks)
        if args.execute_reviewers:
            execute_reviewers(
                run_dir=run_dir,
                requested_role_ids=parse_role_ids(args.roles),
                timeout_override_seconds=args.timeout_seconds,
            )
        print(f"run_dir={relative_path(run_dir)}")
        print(f"manifest={relative_path(run_dir / 'manifest.json')}")
        print(f"summary={relative_path(run_dir / 'one_file_summary.md')}")
        print(f"latest_pointer={relative_path(LATEST_POINTER)}")
        return

    if args.command == "summarize":
        run_dir = (ROOT / args.run_dir).resolve()
        summary_path = summarize_run(run_dir)
        print(f"summary={relative_path(summary_path)}")
        return

    if args.command == "execute":
        run_dir = (ROOT / args.run_dir).resolve()
        runner_state = execute_reviewers(
            run_dir=run_dir,
            requested_role_ids=parse_role_ids(args.roles),
            timeout_override_seconds=args.timeout_seconds,
        )
        print(f"run_dir={relative_path(run_dir)}")
        print(f"provider={runner_state.get('provider', 'not_configured')}")
        print(f"executed_at={runner_state.get('last_execution', {}).get('executed_at', 'not recorded')}")
        print(f"summary={relative_path(run_dir / 'one_file_summary.md')}")
        return


if __name__ == "__main__":
    main()
