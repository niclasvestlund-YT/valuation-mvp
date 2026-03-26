# TASKS — valuation-mvp

*Uppdaterad: 2026-03-25 — Ihopslagen från befintlig TASKS.md + deep investigation*
*Uppdateras löpande av Claude Code*

**Status**: Live på Railway. Säkerhetsskanning gjord. GitHub remote satt men auth pending.
**Princip**: Ingen värdering är bättre än en felaktig värdering.

---

## 🔴 Ikväll — Kritiskt (gör först)

- [x] Wrappa `_persist_valuation` dict-parsing i try/except så oväntade nycklar aldrig crashar bakgrundsuppgiften
- [ ] Sätt upp lokal PostgreSQL så DB-save fungerar
- [ ] Fixa GitHub-remote auth och pusha projektet
- [x] Rate limiting på POST /value — installera `slowapi`, 10 req/min per IP *(backend/app/main.py)*
- [x] API-nyckelskydd på /admin *(backend/app/routers/admin.py, .env: ADMIN_SECRET_KEY)*
- [x] Dölj /docs och /redoc i produktion — `docs_url=None, redoc_url=None` *(backend/app/main.py)*

## 🟠 Stabilitet — direkt efter

- [x] Sätt `temperature: 0` på OpenAI vision-anropet *(vision_service.py, `_build_request_payload()`)*
- [x] Cacha vision-resultat per bild-hash (SHA-256) i 1h *(vision_service.py, cache.py)*
- [x] Fixa att Tradera rate-limit ger tyst dataförlust — logga + returnera explicit status *(tradera_client.py:97-100)*
- [x] Bildvalidering (filtyp, storlek) innan vision-anrop — already in image_preprocess.py + value.py validators
- [x] Lägg till .env.example med alla env-variabler (utan värden) för onboarding
- [x] Skapa `staging`-branch (redan skapad; Railway staging-miljö separat steg)
- [ ] Verifiera Railway-deployment end-to-end

## 🟡 Moat-byggande 🏰

- [x] Komplett datainsamling i DB — market_data_json now persisted, depreciation_estimate saves PriceSnapshot
- [x] Radera eller arkivera `valuation-mvp/`-mappen — removed from git, added to .gitignore
- [x] Automatisera golden tests — 7 canonical product tests in tests/test_golden_cases.py
- [ ] Integrationstester som verifierar hela flödet mot riktig DB
- [x] Confidence calibration logging — `calibration.valuation` log event for ok/depreciation_estimate
- [x] Samla alla 25+ thresholds i en config-fil *(core/thresholds.py)* — 40+ constants extracted

## 🟢 Bättre värderingar

- [ ] OCR-steg innan vision (Google Cloud Vision) — skicka hittad text som kontext till prompten
- [x] Förbättra vision-prompts för hörlurar och kameror — already done: XM4/XM5 hints, DJI Osmo, category angles
- [x] Förbättra bundle-filtrering — multi-item listing detection ("2st", "3x", "par") hard-rejects
- [ ] Höj minimikrav för new price anchor från 1 till 2 källor *(value_engine.py:361)*
- [ ] Ersätt Prisjakt-stub med fungerande prishistorikkälla (Prisjakt blockerar server-side)
- [ ] Research nya datakällor — Facebook Marketplace SE, Swappie, Refurbed
- [ ] Flytta hårdkodad produktkunskap från prompten till en JSON-fil

## 🟢 UX

- [ ] Mobil-first redesign — 390px, stor kamera-knapp, prisintervall 48px font
- [ ] Bekräftelsesteg: "Är detta rätt? Sony WH-1000XM4" innan prisberäkning
- [ ] Separera depreciation-estimat visuellt från marknadsbackade värderingar
- [ ] Fixa admin-panel — /admin/data + detaljvy per värdering

## 🔵 Senare

- [ ] Feedback-loop: visa historiska värderingar per produkt
- [ ] Cron-worker för automatiska prisuppdateringar (PriceSnapshot)
- [ ] Cross-encoder reranking för comparables
- [ ] Autentisering (magic link / Google)
- [ ] Spara pryl + portföljvy
- [ ] Prishistorik per pryl
- [ ] Sentry.io
- [ ] GitHub Actions deploy-pipeline

---

## ✅ Klart

- [x] Checkpoint-commit 2026-03-25
- [x] Säkerhetsskanning (.env, API-nycklar)
- [x] .claude/settings.json med permissions
- [x] GitHub workflow: remote, branches (develop/staging/main), CONTRIBUTING.md, deny-list
- [x] PROJECT_OVERVIEW.md
- [x] Arkitekturöversikt
- [x] CLAUDE.md
- [x] Deep investigation
- [x] Förbättrad vision-prompt (chain-of-thought, produktkunskap, DJI Osmo Pocket 3 fix)
- [x] Brand-normalisering (DJI, GoPro, OnePlus etc.)
- [x] GitHub CLI installerat + auth konfigurerat

*Nästa uppdatering: Efter kvällssession*
