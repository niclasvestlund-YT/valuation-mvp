#!/usr/bin/env python3
"""
VALOR Training Pipeline — ETL + XGBoost training for price prediction.

Usage:
  python scripts/train_valor.py
  python scripts/train_valor.py --dry-run
  python scripts/train_valor.py --force --min-samples 20
  python scripts/train_valor.py --product sony_wh-1000xm4
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")


MODELS_DIR = Path(os.getenv("VALOR_MODEL_DIR", str(PROJECT_ROOT / "models")))
CONDITION_MAP = {
    "like_new": 1.0, "excellent": 0.9, "good": 0.8, "used": 0.6,
    "fair": 0.5, "poor": 0.3, "unknown": 0.5,
}
FEATURE_NAMES = [
    "condition_encoded", "month_of_year", "days_since_observation",
    "price_to_new_ratio", "is_sold_int", "listing_type_fixed",
    "listing_type_auction", "source_valuation", "source_crawler",
    "source_agent",
]


def get_sync_engine():
    """Create a sync engine for the training script."""
    from sqlalchemy import create_engine
    db_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:dev@localhost:5432/valuation")
    sync_url = db_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
    return create_engine(sync_url)


def step_etl(engine, args) -> "pd.DataFrame":
    """Step 1: Extract observations, compute quality scores, upsert training samples."""
    import pandas as pd
    from sqlalchemy import text

    print("\n── STEG 1: ETL ──")

    where_clause = ""
    params = {}
    if args.product:
        where_clause = "WHERE product_key = :pk"
        params = {"pk": args.product}

    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT id, product_key, price_sek, condition, source,
                   observed_at, is_sold, listing_type, final_price,
                   suspicious, price_to_new_ratio, new_price_at_observation
            FROM price_observation
            {where_clause}
            ORDER BY observed_at
        """), params).fetchall()

    if not rows:
        print("  Inga observationer hittade.")
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=[
        "id", "product_key", "price_sek", "condition", "source",
        "observed_at", "is_sold", "listing_type", "final_price",
        "suspicious", "price_to_new_ratio", "new_price_at_observation",
    ])

    print(f"  Totalt observationer: {len(df)}")

    # Compute quality_score
    # Web-agent data needs at least one quality signal beyond price to be included (threshold=0.5).
    # Base 0.2 + price bonus 0.1 + product_key 0.05 = 0.35 floor for web-agent data.
    # Combined with any other signal (is_sold, condition known, etc.) it becomes includable.
    df["quality_score"] = 0.2
    df.loc[df["final_price"] == True, "quality_score"] += 0.3
    df.loc[df["is_sold"] == True, "quality_score"] += 0.2
    df.loc[df["condition"] != "unknown", "quality_score"] += 0.15
    df.loc[df["listing_type"] != "unknown", "quality_score"] += 0.15
    df.loc[df["price_sek"].notna() & (df["price_sek"] > 0), "quality_score"] += 0.1
    df.loc[df["product_key"].notna() & (df["product_key"] != ""), "quality_score"] += 0.05

    # Compute condition_encoded
    df["condition_encoded"] = df["condition"].map(CONDITION_MAP).fillna(0.5)

    # Inclusion criteria
    df["included"] = (
        (df["quality_score"] >= 0.5) &
        (df["suspicious"] == False) &
        (df["price_sek"] >= 200) &
        (df["price_sek"] <= 150_000)
    )
    df["excluded_reason"] = None
    df.loc[df["quality_score"] < 0.5, "excluded_reason"] = "low_quality_score"
    df.loc[df["suspicious"] == True, "excluded_reason"] = "suspicious"
    df.loc[df["price_sek"] < 200, "excluded_reason"] = "price_too_low"
    df.loc[df["price_sek"] > 150_000, "excluded_reason"] = "price_too_high"

    included_count = df["included"].sum()
    excluded_count = len(df) - included_count
    print(f"  Inkluderade: {included_count}")
    print(f"  Exkluderade: {excluded_count}")
    print(f"  [etl.summary] source=price_observation total_read={len(df)} "
          f"included={included_count} excluded_quality={excluded_count} threshold=0.5")

    # Compute derived features
    now = datetime.now(timezone.utc)
    df["days_since_observation"] = df["observed_at"].apply(
        lambda x: min((now - x.replace(tzinfo=timezone.utc) if x.tzinfo is None else now - x).days, 365) if x else 0
    )
    df["month_of_year"] = df["observed_at"].apply(lambda x: x.month if x else 1)
    df["price_to_new_ratio"] = df["price_to_new_ratio"].fillna(0.6).clip(0.1, 1.0)

    # Upsert to training_samples
    if not args.dry_run:
        from sqlalchemy import text as sql_text
        with engine.begin() as conn:
            for _, row in df.iterrows():
                source_id = f"obs_{row['id']}"
                try:
                    conn.execute(sql_text("""
                        INSERT INTO training_sample
                            (id, product_key, price_sek, condition, condition_encoded,
                             source_type, source_id, observed_at, listing_type,
                             final_price, is_sold, price_to_new_ratio,
                             new_price_at_observation, days_since_observation,
                             month_of_year, quality_score, included_in_training,
                             excluded_reason)
                        VALUES
                            (:id, :pk, :price, :cond, :ce, :st, :si, :oa, :lt,
                             :fp, :is, :ptr, :npo, :dso, :moy, :qs, :iit, :er)
                        ON CONFLICT (source_id) DO UPDATE SET
                            price_sek = EXCLUDED.price_sek,
                            quality_score = EXCLUDED.quality_score,
                            included_in_training = EXCLUDED.included_in_training,
                            excluded_reason = EXCLUDED.excluded_reason,
                            days_since_observation = EXCLUDED.days_since_observation
                    """), {
                        "id": str(uuid.uuid4()), "pk": row["product_key"],
                        "price": int(row["price_sek"]), "cond": row["condition"],
                        "ce": float(row["condition_encoded"]),
                        "st": "agent", "si": source_id,
                        "oa": row["observed_at"],
                        "lt": row["listing_type"],
                        "fp": bool(row["final_price"]),
                        "is": bool(row["is_sold"]),
                        "ptr": float(row["price_to_new_ratio"]),
                        "npo": int(row["new_price_at_observation"]) if row["new_price_at_observation"] else None,
                        "dso": int(row["days_since_observation"]),
                        "moy": int(row["month_of_year"]),
                        "qs": float(row["quality_score"]),
                        "iit": bool(row["included"]),
                        "er": row["excluded_reason"],
                    })
                except Exception as e:
                    pass  # Duplicate — fine
        print("  Training samples upserted till DB.")

    return df[df["included"]].copy()


def step_etl_valuations(engine, args) -> "pd.DataFrame":
    """Extract training samples from the valuations table.

    Valuations are real user-submitted with confirmed prices.
    Higher base quality than price_observation since they went through
    the full identification + pricing pipeline.
    """
    import pandas as pd
    from sqlalchemy import text

    print("\n── STEG 1b: ETL VALUATIONS ──")

    where_parts = ["status = 'ok'", "estimated_value IS NOT NULL",
                    "estimated_value BETWEEN 200 AND 150000", "confidence >= 0.4"]
    params = {}
    if args.product:
        where_parts.append("product_key = :pk")
        params["pk"] = args.product

    where_clause = "WHERE " + " AND ".join(where_parts)

    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT id, product_key, brand, product_identifier, category,
                   estimated_value, confidence, new_price, condition,
                   num_comparables_used, created_at
            FROM valuations
            {where_clause}
            ORDER BY created_at
        """), params).fetchall()

    if not rows:
        print("  Inga kvalificerande värderingar.")
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=[
        "id", "product_key", "brand", "product_identifier", "category",
        "estimated_value", "confidence", "new_price", "condition",
        "num_comparables_used", "created_at",
    ])

    print(f"  Totalt ok-värderingar: {len(df)}")

    # Guard: skip rows with missing brand or model (product_identifier)
    before_count = len(df)
    df = df[df["brand"].notna() & (df["brand"] != "") &
            df["product_identifier"].notna() & (df["product_identifier"] != "")]
    excluded_no_product_key = before_count - len(df)
    if excluded_no_product_key > 0:
        print(f"  Exkluderade (saknar brand/model): {excluded_no_product_key}")

    # Quality score — higher base than price_observation (0.3 vs 0.2)
    df["quality_score"] = 0.3
    df.loc[df["num_comparables_used"].fillna(0) >= 5, "quality_score"] += 0.2
    df.loc[df["confidence"].fillna(0) >= 0.7, "quality_score"] += 0.2
    df.loc[df["new_price"].notna(), "quality_score"] += 0.15
    df.loc[df["category"].notna(), "quality_score"] += 0.15

    df["included"] = df["quality_score"] >= 0.5

    # Map fields to training_sample schema
    df["price_sek"] = df["estimated_value"]
    df["condition_encoded"] = df["condition"].map(CONDITION_MAP).fillna(0.5)
    df["source_type"] = "valuation"
    df["is_sold"] = True  # valuations represent market-clearing prices
    df["final_price"] = True
    df["listing_type"] = "fixed"
    df["observed_at"] = df["created_at"]
    df["price_to_new_ratio"] = (df["estimated_value"] / df["new_price"].replace(0, None)).fillna(0.6).clip(0.1, 1.0)
    df["excluded_reason"] = None
    df.loc[df["quality_score"] < 0.5, "excluded_reason"] = "low_quality_score"

    now = datetime.now(timezone.utc)
    df["days_since_observation"] = df["created_at"].apply(
        lambda x: min((now - x.replace(tzinfo=timezone.utc) if x.tzinfo is None else now - x).days, 365) if x else 0
    )
    df["month_of_year"] = df["created_at"].apply(lambda x: x.month if x else 1)

    included_count = df["included"].sum()
    excluded_quality = len(df) - included_count
    print(f"  Inkluderade: {included_count}")
    print(f"  Exkluderade: {excluded_quality}")
    print(f"  [etl.summary] source=valuations total_read={len(df)} "
          f"included={included_count} excluded_quality={excluded_quality} "
          f"excluded_missing_fields={excluded_no_product_key} threshold=0.5")

    # Upsert to training_sample
    if not args.dry_run:
        from sqlalchemy import text as sql_text
        upserted = 0
        with engine.begin() as conn:
            for _, row in df.iterrows():
                source_id = f"val_{row['id']}"
                try:
                    conn.execute(sql_text("""
                        INSERT INTO training_sample
                            (id, product_key, price_sek, condition, condition_encoded,
                             source_type, source_id, observed_at, listing_type,
                             final_price, is_sold, price_to_new_ratio,
                             new_price_at_observation, days_since_observation,
                             month_of_year, quality_score, included_in_training,
                             excluded_reason)
                        VALUES
                            (:id, :pk, :price, :cond, :ce, :st, :si, :oa, :lt,
                             :fp, :is, :ptr, :npo, :dso, :moy, :qs, :iit, :er)
                        ON CONFLICT (source_id) DO UPDATE SET
                            price_sek = EXCLUDED.price_sek,
                            quality_score = EXCLUDED.quality_score,
                            included_in_training = EXCLUDED.included_in_training,
                            excluded_reason = EXCLUDED.excluded_reason,
                            days_since_observation = EXCLUDED.days_since_observation
                    """), {
                        "id": str(uuid.uuid4()), "pk": row["product_key"] or "unknown",
                        "price": int(row["price_sek"]), "cond": row["condition"] or "unknown",
                        "ce": float(row["condition_encoded"]),
                        "st": "valuation", "si": source_id,
                        "oa": row["observed_at"],
                        "lt": "fixed",
                        "fp": True, "is": True,
                        "ptr": float(row["price_to_new_ratio"]),
                        "npo": int(row["new_price"]) if row["new_price"] else None,
                        "dso": int(row["days_since_observation"]),
                        "moy": int(row["month_of_year"]),
                        "qs": float(row["quality_score"]),
                        "iit": bool(row["included"]),
                        "er": row["excluded_reason"],
                    })
                    upserted += 1
                except Exception:
                    pass
        print(f"  Upserted {upserted} valuation training samples.")

    return df[df["included"]].copy()


def step_validate(df: "pd.DataFrame") -> tuple[list[str], bool]:
    """Step 2: Data quality validation."""
    print("\n── STEG 2: DATAKVALITETSVALIDERING ──")
    warnings = []
    critical = False

    if len(df) == 0:
        warnings.append("KRITISK: Inga inkluderade samples")
        return warnings, True

    # Price variance
    cv = df["price_sek"].std() / df["price_sek"].mean() if df["price_sek"].mean() > 0 else 0
    if cv > 2.0:
        warnings.append(f"Extrem prisvarians (CV={cv:.2f})")

    # Unknown condition rate
    unknown_rate = (df["condition"] == "unknown").mean()
    if unknown_rate > 0.5:
        warnings.append(f"{unknown_rate:.0%} har okänt skick")

    # Products with enough obs
    products_with_enough = (df.groupby("product_key").size() >= 10).sum()
    if products_with_enough < 3:
        warnings.append(f"Bara {products_with_enough} produkter med >=10 obs")

    # Temporal coverage
    if len(df) > 0 and df["observed_at"].max() is not None and df["observed_at"].min() is not None:
        date_range = (df["observed_at"].max() - df["observed_at"].min()).days
        if date_range < 7:
            warnings.append(f"All data inom {date_range} dagar — överfit-risk")

    for w in warnings:
        print(f"  ⚠ {w}")
    if not warnings:
        print("  ✓ Inga varningar")

    return warnings, critical


def step_train(df: "pd.DataFrame", args) -> dict | None:
    """Steps 3-6: Feature engineering, train, evaluate, save."""
    import numpy as np

    min_samples = args.min_samples
    if len(df) < min_samples:
        print(f"\n  ✗ För lite data: {len(df)} < {min_samples} minimum")
        if not args.force:
            return None
        print("  --force: tränar ändå")

    print(f"\n── STEG 3: FEATURES ({len(df)} samples) ──")

    # Time-series split — NOT random
    df = df.sort_values("observed_at").reset_index(drop=True)
    split_idx = int(len(df) * 0.8)
    train_df = df.iloc[:split_idx]
    test_df = df.iloc[split_idx:]

    print(f"  Train: {len(train_df)}, Test: {len(test_df)}")

    if len(test_df) < 2:
        print("  ✗ Test set för liten")
        if not args.force:
            return None

    def build_features(subset):
        return np.column_stack([
            subset["condition_encoded"].values,
            subset["month_of_year"].values,
            np.clip(subset["days_since_observation"].values, 0, 365),
            subset["price_to_new_ratio"].fillna(0.6).clip(0.1, 1.0).values,
            (subset["is_sold"] == True).astype(int).values,
            (subset["listing_type"] == "fixed").astype(int).values,
            (subset["listing_type"] == "auction").astype(int).values,
            (subset.get("source_type", "agent") == "valuation").astype(int).values if "source_type" in subset.columns else np.zeros(len(subset)),
            (subset.get("source_type", "agent") == "crawler").astype(int).values if "source_type" in subset.columns else np.zeros(len(subset)),
            (subset.get("source_type", "agent") == "agent").astype(int).values if "source_type" in subset.columns else np.ones(len(subset)),
        ])

    X_train = build_features(train_df)
    y_train = train_df["price_sek"].values.astype(float)
    X_test = build_features(test_df)
    y_test = test_df["price_sek"].values.astype(float)

    print("\n── STEG 4: TRÄNA XGBOOST ──")
    from xgboost import XGBRegressor
    from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error

    model = XGBRegressor(
        n_estimators=200, max_depth=6, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8,
        random_state=42, verbosity=0,
    )
    model.fit(X_train, y_train)

    # Baseline: naive prediction = mean of training set (standard ML baseline)
    baseline_pred = np.full_like(y_test, y_train.mean())
    baseline_mae = mean_absolute_error(y_test, baseline_pred)

    y_pred = model.predict(X_test)
    mae = mean_absolute_error(y_test, y_pred)
    mape = mean_absolute_percentage_error(y_test, y_pred) * 100
    within_10 = (np.abs(y_pred - y_test) / np.maximum(y_test, 1) <= 0.10).mean() * 100
    within_20 = (np.abs(y_pred - y_test) / np.maximum(y_test, 1) <= 0.20).mean() * 100
    fi = dict(zip(FEATURE_NAMES, [float(x) for x in model.feature_importances_]))

    vs_baseline = round((baseline_mae - mae) / baseline_mae * 100, 1) if baseline_mae > 0 else 0.0

    print(f"  MAE:       {mae:.0f} kr")
    print(f"  MAPE:      {mape:.1f}%")
    print(f"  Inom ±10%: {within_10:.1f}%")
    print(f"  Inom ±20%: {within_20:.1f}%")
    print(f"  Baseline:  {baseline_mae:.0f} kr MAE")
    print(f"  vs baseln: {'+' if vs_baseline > 0 else ''}{vs_baseline}%")

    return {
        "model": model,
        "mae_sek": mae,
        "mape_pct": mape,
        "within_10pct": within_10,
        "within_20pct": within_20,
        "feature_importance": fi,
        "train_count": len(train_df),
        "test_count": len(test_df),
        "vs_baseline_mae": baseline_mae,
        "vs_baseline_improvement_pct": vs_baseline,
    }


def step_save(result: dict, warnings: list[str], args) -> str:
    """Save model to disk and register in DB."""
    import joblib

    print("\n── STEG 6: SPARA ──")

    MODELS_DIR.mkdir(exist_ok=True)

    # Determine version number
    existing_count = len(list(MODELS_DIR.glob("valor_v*.pkl")))
    date_str = datetime.now().strftime("%Y%m%d")
    model_version = f"valor_v{existing_count + 1}_{date_str}"
    model_filename = f"{model_version}.pkl"

    model_path = MODELS_DIR / model_filename
    latest_path = MODELS_DIR / "valor_latest.pkl"
    features_path = MODELS_DIR / "valor_features.json"

    if args.dry_run:
        print(f"  [DRY RUN] Skulle sparat {model_filename}")
        return model_version

    joblib.dump(result["model"], model_path)
    shutil.copy2(model_path, latest_path)
    features_path.write_text(json.dumps(FEATURE_NAMES, indent=2))

    print(f"  Sparade: {model_filename}")
    print(f"  Kopierade: valor_latest.pkl")
    print(f"  Features: valor_features.json")

    # Register in DB
    try:
        from sqlalchemy import text, update
        engine = get_sync_engine()

        improvement = result.get("vs_baseline_improvement_pct", 0)
        if not args.force and improvement < 0:
            print(f"  ⚠ Modell är {improvement}% sämre än baseline — aktiveras INTE.")
            print("  Använd --force för att aktivera ändå.")
            should_activate = False
        else:
            should_activate = True

        with engine.begin() as conn:
            # Deactivate previous
            if should_activate:
                conn.execute(text("UPDATE valor_model SET is_active = false WHERE is_active = true"))

            conn.execute(text("""
                INSERT INTO valor_model
                    (id, model_version, model_filename, training_samples, test_samples,
                     mae_sek, mape_pct, within_10pct, within_20pct,
                     vs_baseline_mae, vs_baseline_improvement_pct,
                     feature_importance, is_active, min_samples_met,
                     data_quality_warnings, notes)
                VALUES
                    (:id, :mv, :mf, :ts, :tes, :mae, :mape, :w10, :w20,
                     :vbm, :vbi, :fi, :act, :msm, :dqw, :notes)
            """), {
                "id": str(uuid.uuid4()), "mv": model_version,
                "mf": model_filename,
                "ts": result["train_count"], "tes": result["test_count"],
                "mae": result["mae_sek"], "mape": result["mape_pct"],
                "w10": result["within_10pct"], "w20": result["within_20pct"],
                "vbm": result.get("vs_baseline_mae"),
                "vbi": result.get("vs_baseline_improvement_pct"),
                "fi": json.dumps(result["feature_importance"]),
                "act": should_activate,
                "msm": result["train_count"] >= args.min_samples,
                "dqw": warnings if warnings else None,
                "notes": f"Trained with {result['train_count']} samples",
            })
        print(f"  Registrerad i DB: is_active={should_activate}")
    except Exception as exc:
        print(f"  ⚠ Kunde inte registrera i DB: {exc}")

    return model_version


def main():
    parser = argparse.ArgumentParser(description="VALOR Training Pipeline")
    parser.add_argument("--dry-run", action="store_true", help="ETL only, no training")
    parser.add_argument("--force", action="store_true", help="Train even with insufficient data")
    parser.add_argument("--min-samples", type=int, default=50, help="Minimum samples required")
    parser.add_argument("--product", type=str, default=None, help="Train on specific product_key")
    args = parser.parse_args()

    print("════════════════════════════════════")
    print("  VALOR TRÄNINGSPIPELINE")
    print("════════════════════════════════════")

    engine = get_sync_engine()
    df_obs = step_etl(engine, args)
    df_val = step_etl_valuations(engine, args)

    # Combine both sources
    import pandas as pd
    df = pd.concat([df_obs, df_val], ignore_index=True) if not df_val.empty else df_obs
    print(f"\n  Totalt kombinerade samples: {len(df)} ({len(df_obs)} obs + {len(df_val)} val)")

    if df.empty:
        print("\n✗ Ingen träningsdata tillgänglig.")
        print("  Kör web-agenten, POST /api/ingest, eller gör värderingar i appen först.")
        sys.exit(0)

    warnings, critical = step_validate(df)

    if args.dry_run:
        print("\n[DRY RUN] Stoppar här — ingen träning.")
        print(f"  Tillgängliga samples: {len(df)}")
        print(f"  Varningar: {warnings or 'Inga'}")
        sys.exit(0)

    if critical and not args.force:
        print("\n✗ Kritiska datakvalitetsfel — avbryter.")
        print("  Använd --force för att träna ändå.")
        sys.exit(1)

    result = step_train(df, args)
    if result is None:
        print("\n✗ Träning avbruten.")
        sys.exit(1)

    version = step_save(result, warnings, args)

    print(f"""
════════════════════════════════════
  VALOR TRÄNINGSRESULTAT
════════════════════════════════════
  Version:       {version}
  Samples:       {result['train_count']} train / {result['test_count']} test
  MAE:           {result['mae_sek']:.0f} kr
  MAPE:          {result['mape_pct']:.1f}%
  Inom ±10%:     {result['within_10pct']:.1f}%
  Inom ±20%:     {result['within_20pct']:.1f}%
  Varningar:     {warnings or ['Inga']}
════════════════════════════════════""")


if __name__ == "__main__":
    main()
