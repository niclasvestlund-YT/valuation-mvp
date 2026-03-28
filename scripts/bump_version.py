#!/usr/bin/env python3
"""
Uppdaterar versionsnumret i frontend/admin.html vid varje commit.
Körs automatiskt av pre-commit hook.
Format: v{major}.{build} där build räknas upp vid varje körning.
"""
import re
from pathlib import Path
from datetime import datetime

html = Path("frontend/admin.html")
content = html.read_text(encoding="utf-8")

# Hitta nuvarande version
match = re.search(r'v(\d+)\.(\d+)', content)
if match:
    major = match.group(1)
    build = int(match.group(2)) + 1
else:
    major, build = "12", 1

today = datetime.now().strftime("%Y-%m-%d")
new_version = f"v{major}.{build}"

# Uppdatera meta-tag
content = re.sub(
    r'<meta name="build-version" content="[^"]*">',
    f'<meta name="build-version" content="{new_version}">',
    content
)

# Uppdatera synlig text i sidebar
content = re.sub(
    r'v\d+\.\d+ · \d{4}-\d{2}-\d{2}',
    f'{new_version} · {today}',
    content
)

html.write_text(content, encoding="utf-8")
print(f"Version bumped to {new_version} · {today}")
