# TASKS.md
> Prioriterad uppgiftslista för valuation-mvp.
> Uppdateras löpande av Claude Code.

## Prio 1 — Kritiskt
- [ ] Wrappa `_persist_valuation` dict-parsing i try/except så att oväntade nycklar aldrig crashar bakgrundsuppgiften
- [ ] Sätt upp lokal PostgreSQL (Postgres.app, Homebrew eller Railway) så att DB-save faktiskt fungerar
- [ ] Lägg till GitHub-remote och pusha projektet (remote added, auth pending)

## Prio 2 — Viktigt
- [ ] Ersätt Prisjakt-stub med fungerande prishistorikkälla (Prisjakt blockerar server-side)
- [ ] Lägg till .env.example med alla env-variabler (utan värden) för onboarding
- [ ] Integrationstester som verifierar hela flödet mot riktig DB
- [ ] Verifiera Railway-deployment end-to-end

## Prio 3 — Förbättringar
- [ ] Feedback-loop: visa historiska värderingar per produkt
- [ ] Cron-worker för automatiska prisuppdateringar (PriceSnapshot)
- [ ] Rate-limiting på POST /value
- [ ] Bildvalidering (filtyp, storlek) innan vision-anrop
- [ ] Admin-dashboard: autentisering

## Avklarat
- [x] Checkpoint-commit 2026-03-25
- [x] Säkerhetsskanning (.env, API-nycklar)
- [x] .claude/settings.json med permissions
- [x] GitHub workflow: remote, branches (develop/staging/main), CONTRIBUTING.md, deny-list updated
