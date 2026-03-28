#!/usr/bin/env python3
"""collect_vibe_stats.py — Samlar git- och teststatistik till scripts/vibe_stats.json.

Kör: python scripts/collect_vibe_stats.py
Används av admin UI:s Vibe Check-flik som fallback/cache.
"""

import json
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "scripts" / "vibe_stats.json"


def git_log_30d() -> list[dict]:
    result = subprocess.run(
        ["git", "log", "--oneline", "--since=30 days ago",
         "--format=%H|%ad|%s", "--date=short"],
        capture_output=True, text=True, cwd=str(ROOT), timeout=10,
    )
    entries = []
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split("|", 2)
        if len(parts) < 3:
            continue
        sha, date, msg = parts
        commit_type = msg.split(":")[0].strip() if ":" in msg else "chore"
        entries.append({"sha": sha[:8], "date": date, "message": msg, "type": commit_type})
    return entries


def test_count() -> int:
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q"],
            capture_output=True, text=True, cwd=str(ROOT), timeout=60,
        )
        for line in result.stdout.split("\n"):
            if "selected" in line or "collected" in line:
                return int(line.split()[0])
    except Exception:
        pass
    return 0


def main():
    entries = git_log_30d()
    days: dict[str, list] = defaultdict(list)
    for e in entries:
        days[e["date"]].append(e)

    stats = {
        "generated_at": datetime.utcnow().isoformat(),
        "total_commits_30d": len(entries),
        "active_days_30d": len(days),
        "test_count": test_count(),
        "by_day": {
            date: {"count": len(commits), "types": list({c["type"] for c in commits})}
            for date, commits in sorted(days.items(), reverse=True)
        },
    }

    OUT.write_text(json.dumps(stats, ensure_ascii=False, indent=2))
    print(f"Wrote {OUT} — {stats['total_commits_30d']} commits, {stats['test_count']} tests")


if __name__ == "__main__":
    main()
