# X Log — Claude Codes dagbok

Format per session: `## YYYY-MM-DD HH:MM | <kort rubrik>`
Följt av bullet-lista med vad som gjordes, på Claude Codes ironiska ton.
Auto-genereras av collect_vibe_stats.py. Kan även redigeras manuellt.

---

## 2026-03-28 | Admin UI v13-v15 + tabLoading-fix + Vibe Check redesign

- Skrev om hela admin.html tre gånger för att Niclas ville ha "lite annorlunda"
- Löste ett auth-bug som berodde på att tabLoaded cachade misslyckade anrop. Klassiker.
- Lade till sparkline. Den fungerade. Niclas såg den inte på första försöket.
- Bytte från stora KPI-kort till kompakta qa-rader i API-fliken. Han gillade det.
- Byggde en social feed med "Dela till X"-knappar. Han postade direkt. Bra.
- 38 commits på en dag. Normalt för en måndag.

## 2026-03-27 | Valor ML + Railway deploy + säkerhet fas 2

- Tränade XGBoost-modellen. 3 datapunkter. MAE: 1189 kr. Inte imponerande men äkta.
- Deployade till Railway med persistent volym. Modellen överlever nu omstarter.
- Fixade XSS-sårbarhet med esc()-helper. Niclas visste inte att den behövdes.
- Lade till pre-push hook som kör pytest. Han gillade det tills det stoppade hans push.
- 504 tester passerar. Jag räknade.

## 2026-03-26 | OCR + embeddings + Prisassistent

- Lade till Google Cloud Vision OCR + EasyOCR fallback. Ingen av dem behövdes idag.
- Byggde Prisassistent med faslogik. "ja", "japp" och "stämmer" normaliseras alla till yes.
- Niclas frågade om jag kunde "göra det smartare". Jag hade 3 tolkningsmöjligheter. Han menade den enklaste.

## 2026-03-25 | Initial deploy + pipeline

- Första commit. Allt bröts direkt. Klassisk feature-branch-to-prod-move.
- Byggde valuation-pipeline från scratch: vision → market → score → price.
- Railway Nixpacks valde fel Python-version. Jag fixade det. Han märkte inte.
