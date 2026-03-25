# Project Overview: Second-Hand Valuation MVP

This document provides a consolidated, high-level overview of the `valuation-mvp` project. It's designed to give a quick and comprehensive understanding of the application's purpose, architecture, core logic, and design principles.

---

## 1. What This Is

A local MVP for estimating the second-hand value of consumer tech products from photos. It identifies the product via OpenAI Vision, searches Swedish used markets (Tradera, Blocket), and returns a conservative value range. The application prioritizes honest refusal over a misleading number.

**Key Principles:**
- Prefer honesty over always showing a number.
- Explain when more photos are needed.
- Explain when market evidence is too weak.
- Treat new price as secondary context, not the main promise.
- Trust over coverage.
- No valuation is better than a misleading valuation.
- Explain uncertainty clearly.

---

## 2. Technology Stack

-   **Backend:** FastAPI, Python 3.11, uvicorn
-   **Frontend:** Single static HTML/CSS/JS file, served by FastAPI
-   **Database:** PostgreSQL (asyncpg, SQLAlchemy, Alembic for migrations)
-   **Deployment Target:** Railway
-   **Key Dependencies:** `fastapi`, `uvicorn`, `pydantic`, `requests`, `Pillow`, `pillow-heif`, `python-dotenv`, `blocket-api`

---

## 3. Request Flow (High-Level)

1.  **Image Upload:** User uploads one or more images.
2.  **API Endpoint:** Request hits `POST /value` in `api/value.py`.
3.  **Orchestration:** `value_engine.py` orchestrates the process.
4.  **Product Identification:** `vision_service.py` uses OpenAI Vision to identify the product.
5.  **Market Data Lookup:** `market_data_service.py` (Tradera, Blocket) and `new_price_service.py` (Serper.dev) fetch comparable listings and new prices in parallel.
6.  **Comparable Scoring:** `comparable_scoring.py` filters and scores relevance of market listings.
7.  **Pricing:** `pricing_service.py` calculates the valuation.
8.  **Response & Persistence:** `api/value.py` enriches the response envelope and saves the valuation to the database via `BackgroundTasks`.

---

## 4. Core Database Models

The application stores valuation results and price snapshots for historical tracking and feedback.

**`Valuation` Model (`backend/app/db/models.py`):**
-   `id`: Unique ID for each valuation request.
-   `created_at`: Timestamp of the valuation.
-   **Product Info:** `product_name`, `product_identifier`, `brand`, `category`, `vision_confidence`.
-   **Result:** `status` ("ok", "ambiguous_model", etc.), `estimated_value`, `value_range_low`, `value_range_high`, `new_price`, `confidence`.
-   **Data Quality:** `num_comparables_raw`, `num_comparables_used`, `sources_json` (details on fetched/used comparables).
-   **User Feedback:** `feedback` ("correct", "too_high", etc.), `corrected_product`.

**`PriceSnapshot` Model (`backend/app/db/models.py`):**
-   `id`: Unique ID for each snapshot.
-   `created_at`: Timestamp of the snapshot.
-   `product_identifier`: The model ID.
-   `estimated_value`, `value_range_low`, `value_range_high`, `new_price`, `num_comparables`.
-   `sources_json`: Details on comparable sources.
-   `snapshot_date`: Date of the snapshot (e.g., "2026-03-24").
-   `source`: "user_scan" or "cron_worker".

---

## 5. Key Endpoints

-   **`POST /value`**: Main endpoint for submitting images/product details to get a valuation. Returns a `ValueEnvelope` JSON.
-   **`POST /feedback`**: Endpoint for users to submit feedback on a valuation (`valuation_id`, `feedback`, `corrected_product?`).
-   **`GET /`**: Serves the single-page frontend UI (`frontend/index.html`).
-   **`GET /admin`**: Serves the admin dashboard (`frontend/admin.html`).
-   **`GET /health`**: Returns application health status and version.

---

## 6. Key Environment Variables

-   `OPENAI_API_KEY`: For OpenAI Vision API.
-   `TRADERA_APP_ID`, `TRADERA_APP_KEY`: For Tradera's official API.
-   `SERPER_DEV_API_KEY`: Primary source for new-price lookups.
-   `SERPAPI_API_KEY`: Optional fallback for new price and used market supplement.
-   `DATABASE_URL`: PostgreSQL connection string (Railway sets this automatically).
-   `USE_MOCK_VISION`: Set to `true` to bypass actual OpenAI Vision calls for local testing.

---

## 7. Response States

The application communicates its confidence and data availability through distinct status codes:

-   **`ok`**: The app found enough evidence to show an estimated used-value range.
-   **`ambiguous_model`**: The app needs clearer or more complete photos before it can trust the exact model identification. It may return requested additional angles.
-   **`insufficient_evidence`**: The product may be identified correctly, but there is not enough strong second-hand market evidence to support a trustworthy valuation.
-   **`degraded`**: A temporary system issue (e.g., an upstream API failure like Tradera or Vision) prevented a fully reliable valuation result. SerpAPI failures are generally silent and do not trigger this state.
-   **`error`**: The request failed due to a bad upload, decode failure, or an unexpected internal exception.

---

## 8. UI Design Principles (from `skills/ui/SKILL.md`)

The UI aims for a premium, trustworthy, mobile-first experience with fintech-grade polish, inspired by services like Klarna.

-   **Identity:** Warm, light, Scandinavian; typographic hierarchy; fintech confidence with marketplace transparency.
-   **Estimate is Hero:** The estimated value is the most prominent element (`text-hero` typography token).
-   **Color:** Warm off-white base, minimal accent colors used only to communicate meaning (positive, warning, danger). No green/blue AI accents, no gradients, no emoji.
-   **Icons:** Lucide library, clean, thin stroke style, primarily `text-muted` color.
-   **Dual-View:** Quick View (default, zero scroll) for essential info, Advanced View (expandable) for details like source breakdown, price distribution, and comparable listings.
-   **Honest Communication:** Clearly explains why a value was shown or withheld, asks for more photos, or states when market evidence is too weak.

---

## 9. Key Files for Deeper Dive

-   **`backend/app/api/value.py`**: The main API endpoint for valuations and feedback.
-   **`backend/app/core/value_engine.py`**: The central orchestration logic for the entire valuation pipeline.
-   **`backend/app/services/vision_service.py`**: Handles product identification via OpenAI Vision.
-   **`backend/app/services/market_data_service.py`**: Fetches and merges market comparables.
-   **`backend/app/db/crud.py`**: Database Create, Read, Update, Delete operations for `Valuation` and `PriceSnapshot`.
-   **`backend/app/utils/error_reporting.py`**: Structured error logging and artifact generation.
-   **`skills/ui/SKILL.md`**: Detailed UI design system and principles.

---

This `PROJECT_OVERVIEW.md` should serve as your primary context file when interacting with Claude Code.