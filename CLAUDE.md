# Rules

## After every task
Update CONTEXT.md:
- File Map: sync with actual files (add/remove/rename)
- Recent Changes: prepend `YYYY-MM-DD — what changed` (keep max 15 entries, delete oldest)
- Known Issues: add/remove as needed
- Next Up: remove done items
- Skip sections where nothing changed

Include CONTEXT.md in the commit if it changed.

## CONTEXT.md limits
- Total file must stay under 200 lines
- One line per entry, no paragraphs
- No duplicate information across sections

## Security
CONTEXT.md must NEVER contain:
- API keys, tokens, passwords, or secrets
- Production URLs or internal endpoints
- User data or database connection strings
- .env values or references to actual key values

If in doubt, leave it out.

## Skills

When building or reviewing UI for the valuation app, load the design system first:
`skills/ui/SKILL.md` — complete design system: tokens, components, screen specs, copy rules, and pre-ship checklist for the premium Klarna-style valuation UI.

## Commits
Conventional: feat: fix: refactor: docs: chore:
Never commit .env
