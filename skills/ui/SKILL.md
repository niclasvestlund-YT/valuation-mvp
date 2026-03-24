---
name: ui-premium-valuation
description: Use this skill when building or reviewing UI for the valuation app. Defines the complete design system for a premium, trustworthy, mobile-first valuation experience with fintech-grade polish.
---

# UI Skill: Premium Valuation App (Final)

## What this app is

A tool that helps users photograph a tech product, identify it, and get a realistic second-hand value estimate backed by real market data. The app must earn trust in seconds. Users compare it mentally against checking Tradera, Blocket, and Marketplace themselves.

## Design identity

Think Klarna, Wise, Swish — not generic AI dashboard.

- Warm, light, Scandinavian
- Typographic hierarchy, not card-based
- Fintech confidence with marketplace transparency
- One strong opinion: the estimate is everything, the rest supports it

---

## Design Tokens

### Colors (light, warm base)

```
--bg-base: #F7F5F0             /* app background — warm off-white */
--bg-surface: #EDEAE3           /* cards, panels, inputs */
--bg-surface-raised: #FFFFFF    /* bottom sheets, modals */
--bg-overlay: rgba(44,42,37,0.5) /* dimmed background behind sheets */

--border-subtle: #E8E4DB        /* default borders, dividers */
--border-medium: #D5D0C5        /* emphasized borders, dashed upload */

--text-primary: #2C2A25         /* headings, values, CTAs — near black, warm */
--text-secondary: #5C5850       /* body text, explanations */
--text-muted: #8A8578           /* labels, captions */
--text-faint: #B0AA9E           /* timestamps, section headers, placeholders */

--accent-positive: #34a873      /* relevance high, positive change */
--accent-warning: #d4a017       /* medium relevance, ambiguous state */
--accent-danger: #c4432a        /* error state, negative change */

--value-color: #2C2A25          /* the estimate number — same as primary but role is distinct */
```

No green/blue AI accents. No gradients. No neon. The primary color IS the dark warm charcoal. Color only appears to communicate meaning.

### Typography

```
Font: Inter (Google Fonts, fallback: system-ui, -apple-system)

--text-xs: 0.6875rem / 1rem      (11px — badges, timestamps, section headers)
--text-sm: 0.8125rem / 1.25rem   (13px — captions, source lines, muted copy)
--text-base: 0.875rem / 1.375rem (14px — body, comparables, reasoning)
--text-lg: 0.9375rem / 1.5rem    (15px — emphasized body, range text)
--text-xl: 1.125rem / 1.375rem   (18px — product name in compact view)
--text-2xl: 1.25rem / 1.5rem     (20px — product name in hero, section titles)
--text-hero: 3.25rem / 1          (52px — estimate value ONLY)
```

Rule: text-hero is ONLY for the estimate number. Nothing else on any screen may use it.

### Spacing

```
4px — micro gaps (inside badges, between icon and text)
8px — tight gaps (between chips, between list rows internally)
12px — component internal padding
14-16px — standard padding inside cards and sheets
20-24px — between sections
28-32px — between major page blocks
```

### Radius

```
6px — small badges, condition tags
8px — depreciation pills
10-12px — cards, input fields, list containers
14px — buttons, CTAs
16px — upload area, main panels
20px — bottom sheets
50% — circular elements (checkmarks, avatars, icons)
```

### Shadows

```
Bottom sheet: 0 -4px 24px rgba(0,0,0,0.08)
Everything else: no shadow
```

The app relies on surface color and spacing for hierarchy, not shadows.

### Icons

```
NEVER use emoji in the UI. Emoji renders differently across devices
and operating systems, breaking visual consistency.

Library: Lucide (lucide.dev) — clean, thin stroke style
Color: always text-muted (#8A8578) unless icon is inside a button or active state
Size: 20px default, 24px for prominent icons, 14-16px for inline/row icons
Stroke width: 1.5px

Specific mappings:
  Camera/scan: lucide camera
  Edit/correct: lucide pencil
  Checkmark: lucide check (inside filled circle)
  Info/warning: lucide info or alert-circle
  Photo tips: lucide camera, tag, sun
  Navigation: lucide chevron-right (→ arrows in lists)
  Close/remove: lucide x
  Menu: lucide menu

Rule: all icons on a screen must be same size, same color, same stroke width.
If an icon doesn't improve comprehension, remove it.
```

---

## Dual-View Architecture

### Quick View (default — fits one screen, zero scroll)

```
1. Product identity       (photo thumbnail + name + edit icon)
2. Estimate               (THE HERO — largest text on screen)
3. Combined info line     (range · confidence · source count — one line)
4. Value retention bar    (nypris → % behållet — compact)
5. Actions                (Scanna ny + Se detaljer)
6. Quick links            (Sälj på Tradera · Dela estimat)
7. Timestamp              (faint, bottom)
```

Must fit on 375x812 without scrolling. Everything the user needs in 2 seconds.

### Advanced View (expands below, Quick View stays visible)

```
8. Source breakdown       (chips: Tradera: 14, Google Shopping: 4)
9. Price distribution     (horizontal dot plot with IQR band)
10. Comparable listings   (top 5, expandable)
11. Reasoning text        (blockquote style, plain language)
12. Feedback              (Identifierade vi rätt produkt? Ja/Nej)
13. Next steps            (Sälj på Tradera, Lägg upp på Blocket, Dela)
```

Toggled by "Se detaljer" / "Dölj detaljer". State persists during session.

---

## Screen Specifications

### 1. Landing / Upload

The first screen. Must convert browsers to scanners.

```
Header: "VÄRDEKOLL" center, hamburger menu right

Hero text:
  "Vad är din pryl värd idag?" — text-2xl * 1.6, font-weight 700
  "Fota en teknikprodukt. Vi kollar vad den säljs för." — text-lg, text-muted

Upload area:
  bg-surface, border 2px dashed border-medium, radius 20px
  Centered: camera icon (28px) in circular bg-base container
  "Ta ett foto" — text-lg, font-weight 500, text-primary
  "eller välj från biblioteket" — text-sm, text-muted
  Entire area is tappable. Min height 180px.

Tips row (3 items):
  Section header: "TIPS FÖR BÄSTA RESULTAT" — text-xs, text-faint, uppercase, tracking
  3 compact cards: bg-surface, radius 10px, centered SVG icon (24px, stroke text-muted) + 2-line text
  Icons (Lucide): camera — "Hela produkten synlig" / tag — "Modellnr om möjligt" / sun — "Bra ljus, ingen blixt"

Recent scans (if any exist):
  Section header: "SENASTE VÄRDERINGAR" — text-xs, text-faint, uppercase
  List: thumbnail (36x36) + product name + time ago → price, right-aligned
  Tapping opens that result again
  Max 3 items shown

If no history: skip the section entirely, no empty state needed
```

### 2. Scanning / Processing

Progressive reveal, not a spinner.

```
User's photo: full width, 220px height, radius 16px
  Bottom overlay gradient: product name appears as soon as identified
  "Ditt foto" label in bottom-left

Steps (vertical, sequential):
  ✓ Completed: filled dark circle with checkmark + result text
    "Sony WH-1000XM4 identifierad" + "Trådlösa hörlurar · Hög säkerhet"
  ○ Active: border circle with center dot + action text
    "Söker priser på Tradera..." + "14 resultat hittade hittills"
  ○ Waiting: empty border circle + muted text
    "Beräknar estimat"

Each step fills in as real data arrives. Not fake staged loading.
```

### 3. Quick View Result (status: ok)

```
Product row:
  Thumbnail 52x52, radius 12px (user's photo, cropped square)
  Product name: text-xl, font-weight 600
  "Trådlösa hörlurar · Identifierad ✓" — text-xs, text-muted
  Edit icon (pencil, 14px): right-aligned, tapping opens correction sheet

Estimate:
  Label: "BEGAGNAT MARKNADSVÄRDE" — text-xs, text-faint, uppercase, letter-spacing 2px
  Value: "2 950 kr" — text-hero, font-weight 700, text-primary, letter-spacing -2px
  NO card around it. Sits directly on bg-base. Typography does the work.

Combined info line:
  "2 600 – 3 500 kr · Hög konfidens · 18 källor"
  text-base, text-muted. Bold spans for range and count.
  ONE line. Replaces separate confidence bar + source section + range display.

Value retention bar:
  Container: bg-surface, radius 14px, padding 14px 16px
  Top row: "Nypris 3 990 kr → behåller" left, "74%" right (text-lg, bold)
  Bar: 6px height, two segments (dark = retained, light = depreciation)
  Show ONLY if valid new price exists. Hide entirely otherwise.

Actions:
  Two buttons side by side:
    "Scanna ny" — bg text-primary, color bg-base, radius 14px, h-48px
    "Se detaljer" — border border-medium, color text-secondary, radius 14px

Quick links:
  "Sälj på Tradera" · "Dela estimat" — text-xs, underline, text-muted
  Centered, subtle

Timestamp:
  "Estimerat idag 23 mars 2026" — text-xs, text-faint, centered, very bottom
```

### 4. Advanced View (expanded under Quick View)

```
"Dölj detaljer" link: text-xs, underline, text-muted

Source chips:
  Section header: "KÄLLOR" — text-xs, text-faint, uppercase
  Horizontal row: [Tradera: 14] [Google Shopping: 4]
  Each chip: bg-surface, border-subtle, radius-full, text-sm

New price (if valid):
  Container: bg-surface, radius 12px, padding 12px 16px
  Left: "Nypris (Webhallen)" label + price
  Right: depreciation percentage in accent-danger

Price distribution:
  Section header: "PRISFÖRDELNING BLAND JÄMFÖRELSEOBJEKT"
  Container: bg-surface, radius 12px, padding 16px
  Horizontal dot plot:
    Background: thin 3px line from min to max
    IQR band: thicker bar showing middle 50% of prices (darker surface)
    Dots: 7px circles, text-faint color. Dots inside IQR are darker (text-muted)
    Estimate marker: 3px wide vertical line, text-primary, full height, with value label above
    Axis: min price left, max price right, text-xs, text-muted
    Helper: "● i mitten = vanligast" centered, text-xs, text-faint
  Skip entirely if fewer than 3 comparables.

Comparable listings:
  Section header: "SENASTE FÖRSÄLJNINGAR" + "Sorterat efter relevans"
  Rows:
    Left: title (1 line, truncate) + metadata row (source · time · condition tag)
    Right: price (tabular-nums, font-weight 600) + relevance dot
    Condition tag: small pill (bg-surface, text-xs) — "Begagnad", "Fint skick", "Nyskick"
    Relevance: "● hög relevans" green, "● medium" amber, no dot for low
    Divider: 1px border-subtle between rows
    Max 5 shown + "Visa alla X objekt →" link
    Row height: ~52px

Reasoning:
  Section header: "SÅ RÄKNADE VI"
  Style: border-left 2px border-medium, padding-left 16px
  Text: text-base, text-secondary, line-height 1.65, max-width 65ch
  Plain language. Name sources. Name numbers. Name uncertainty.

Feedback:
  Container: bg-surface, radius 12px, padding 16px
  "Identifierade vi rätt produkt?" — text-sm, font-weight 500
  Two buttons: "Ja, stämmer" / "Nej, fel modell"
  NOT about the value — the user can't judge value yet

Next steps:
  Section header: "NÄSTA STEG"
  List container: bg-surface rounded, rows separated by 1px border
  Each row: label left, → arrow right, tappable
  "Sälj på Tradera" / "Lägg upp på Blocket" / "Dela estimat"
```

### 5. Correction Flow

Triggered by tapping the edit icon on the product row.

```
Step 1 — Feedback prompt (visible in Quick View):
  "Identifierade vi rätt produkt?" — bg-surface, radius 12px
  "Tryck här om det inte är en WH-1000XM4"
  Pencil icon right-aligned

Step 2 — Bottom sheet slides up:
  Background dims (bg-overlay)
  Sheet: bg-surface-raised, radius 20px top, shadow
  Handle bar: 36px wide, 4px, centered, bg border-subtle
  Title: "Rätta produkt" — text-2xl, font-weight 600
  Subtitle: "Vi identifierade: Sony WH-1000XM4" — text-sm, text-muted

  "MENADE DU KANSKE" section:
    Smart suggestions based on product family (same brand, adjacent models)
    Each row: product name + context ("Nyare modell · Högre värde") → arrow
    Max 3 suggestions
    Tapping a suggestion immediately triggers re-valuation

  "ELLER SKRIV SJÄLV" section:
    Text input + "Värdera" button side by side
    Placeholder: 'T.ex. "Sony WH-1000XM5"'

  "Avbryt" link: centered, text-xs, underline

Step 3 — Re-valuation result:
  Quick transition: sheet closes, brief scanning animation (1-2 seconds)
  Product name updates with "Rättad" badge (text-xs, bg-surface, radius 6px)
  Pencil icon remains for further correction

  Change indicator: centered pill showing
    Old price (strikethrough, text-muted) → new price (font-weight 600) → delta (+700 kr in accent-positive)

  All data updates: new estimate, new range, new retention %, new sources
```

### 6. Ambiguous Model State

```
Photo with "Otydlig bild" overlay badge (top-right)

"MÖJLIG MATCHNING" label
Product family name: "Sony WH-1000X-serien" — text-2xl
Explanation: "Vi kunde inte avgöra om det är XM4 eller XM5 — det påverkar priset med ca 500 kr."

Photo request section:
  Container: bg-surface, radius 14px
  "Lägg till fler bilder för bättre estimat"
  3 dashed upload slots: "Sidan" / "Modellnr." / "Etikett"
  Each slot: 80px height, bg-base, dashed border, icon + label

Price range comparison (blockquote style):
  "WH-1000XM4 säljs begagnat för ca 2 500–3 200 kr. XM5 säljs för ca 3 200–4 000 kr."

CTA: "Ta fler bilder" — primary button
Escape: "Visa ungefärligt estimat ändå" — text link

NO estimate value shown. NO confidence bar. NO retention bar.
```

### 7. Insufficient Evidence State

```
Photo + confirmed identity badge (product was identified correctly)

Centered empty state:
  Circle icon: info/question mark in bg-surface
  "Inte tillräckligt med data" — text-2xl
  Explanation: "Vi hittade [product] men bara X relevanta annonser."

"DET VI HITTADE" section:
  Transparent list of what data exists
  Tradera: X st (price) / Google Shopping: X st (price) / Nypris: X kr

Suggestion (blockquote):
  "Prova igen om ett par dagar — nya annonser dyker upp hela tiden."
  Direct links to Tradera and Blocket searches for this product

CTA: "Värdera en annan produkt" — primary button
Escape: "Visa grov uppskattning ändå" — text link

NO estimate value shown. NO confidence bar. NO retention bar.
```

### 8. Error and Degraded States

```
Error:
  Simple centered message: "Något gick fel"
  Plain explanation of what happened
  "Försök igen" primary button
  No product data shown

Degraded:
  Product identity shown (if available)
  "Tillfälligt problem med marknadsdatan"
  "Några datakällor svarar inte just nu. Estimatet kan vara mindre tillförlitligt."
  Show estimate IF enough data exists, but with reduced confidence
  "Försök igen senare" secondary action
```

---

## Interaction Details

### Upload behavior
- Tap upload area — native camera/photo picker
- accept="image/*" capture="environment" for mobile camera
- After selecting: thumbnail appears inline, upload starts immediately
- Multiple images: horizontal scroll row of thumbnails below main photo
- Primary image: first selected, slightly larger
- Remove: X button top-right of each thumbnail
- Max 5 images

### Scroll and expansion
- Quick View: no scroll needed on standard phone
- "Se detaljer": smooth height animation, ~300ms ease-out
- Advanced View content fades in as it expands
- "Dölj detaljer": reverse animation
- Estimate card never scrolls out of view in Advanced
- State persists: if expanded once, stays expanded for next scan

### Navigation
- No tabs, no separate pages, no router
- Upload → Scanning → Result is a single-page flow
- Back from result — upload (reset)
- History items on landing — opens that result

---

## Copy Rules

### Do
- "Din [product] är värd" — personal
- "Baserat på 14 sålda" — specific numbers
- "på Tradera och Google Shopping" — name sources
- "Håller värdet bra" — plain context for depreciation
- "Inte tillräckligt med data" — honest when uncertain

### Don't
- "AI-powered" anywhere
- "Vår algoritm", "vår motor"
- "Unlock", "Discover", "Revolutionize"
- Fake precision: round to nearest 50 kr
- "Något gick fel" without saying what

### Section headers
Always: text-xs, text-faint, uppercase, letter-spacing 2px
Examples: "BEGAGNAT MARKNADSVÄRDE", "SENASTE FÖRSÄLJNINGAR", "SÅ RÄKNADE VI", "NÄSTA STEG"

---

## Responsive

### Mobile (<640px) — primary
Single column, full width, padding 0 16px
All specs above are mobile-first

### Tablet (640-1024px)
Center content, max-width 480px
Same layout, more breathing room

### Desktop (>1024px)
Center content, max-width 520px
Never stretch wide. This is a phone-first tool.
Optional: comparables in 2-column grid in Advanced View

---

## Checklist Before Shipping

### Quick View
- [ ] Fits on 375x812 without scrolling
- [ ] Estimate is text-hero — nothing else competes
- [ ] Combined info line is ONE line (range + confidence + sources)
- [ ] Value retention bar hidden if no valid new price
- [ ] Edit icon visible on product row for correction
- [ ] "Se detaljer" button present

### Advanced View
- [ ] Smooth expand/collapse animation
- [ ] Quick View stays visible when expanded
- [ ] Comparables show source name, time, condition, relevance
- [ ] Reasoning is plain language, no AI-speak
- [ ] Dot plot skipped if <3 comparables
- [ ] Feedback asks about identification, not value

### Correction Flow
- [ ] Bottom sheet with smart product suggestions
- [ ] Manual input option available
- [ ] "Rättad" badge appears after correction
- [ ] Change indicator shows old → new → delta
- [ ] Re-correction possible (pencil icon persists)

### States
- [ ] ambiguous_model: NO estimate, shows photo guidance
- [ ] insufficient_evidence: NO estimate, shows what was found
- [ ] degraded: shows warning, estimate only if data supports it
- [ ] error: plain message + retry

### General
- [ ] Works one-handed on 375px screen
- [ ] No element says "AI" in user-facing copy
- [ ] No emoji anywhere — all icons are Lucide SVGs in text-muted color
- [ ] All text contrast passes WCAG AA (4.5:1)
- [ ] Upload area is fully tappable
- [ ] Landing shows scan history if available
- [ ] Loading states show real progress, not fake steps
- [ ] Timestamp visible on every result
- [ ] "Sälj på Tradera" link present in Quick View

---

## Final instruction to Claude

When building or revising UI for this app:
- The estimate is the hero. Everything else is supporting cast.
- Typography creates hierarchy, not cards and borders.
- Warm light surfaces, not dark mode dashboards.
- Name real numbers, real sources, real uncertainty.
- If it looks like every other Claude Code app, start over.

Test: would a Klarna designer feel at home here? If not, simplify and refine.
