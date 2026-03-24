# GOLDEN_TEST_CASES

QA should always check these cases before sign-off.

## Sony WH-1000XM4
- expected behavior: should prefer the exact XM4 model when evidence is strong
- trust check: should not drift into XM5 unless evidence clearly supports it

## Sony WH-1000XM5
- expected behavior: should distinguish XM5 from XM4
- trust check: should explain ambiguity if the visual evidence is weak

## iPhone 13
- expected behavior: common product with clear photos should often reach `ok`
- trust check: should still refuse valuation if market evidence is weak

## DJI Osmo Action
- expected behavior: should distinguish nearby Osmo family results cautiously
- trust check: `Osmo Pocket`, different generations, and combo variants should not look like clean exact-model support
