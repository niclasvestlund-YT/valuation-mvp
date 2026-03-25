# STATUS — 2026-03-26

## Done this session (🟡 Moat-building)
- market_data_json now persisted to DB; depreciation_estimate saves PriceSnapshot
- valuation-mvp/ dir removed from git (55 files, 4613 lines); .gitignore expanded
- core/thresholds.py: 40+ constants extracted from 3 files into single tuning file
- Confidence calibration logging: calibration.valuation structured log event
- 7 golden tests: Sony XM4/XM5, iPhone 13, DJI Osmo Pocket 3, MacBook Air M2, unknown product, low confidence
- Fixed request/req variable shadowing bug in value.py

## Tests
- 73 passed, 0 failed (was 66, +7 golden)

## Remaining 🟡
- [ ] Integrationstester mot riktig DB (kräver lokal PostgreSQL)

## Next priorities (🟢)
- OCR-steg innan vision
- Bundle-filtrering förbättringar
- New price anchor minimum 2 sources
- Mobil-first redesign
