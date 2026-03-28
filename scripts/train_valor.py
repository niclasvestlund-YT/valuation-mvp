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
CANDIDATE_MODELS_DIR = MODELS_DIR / "candidates"
REPORTS_DIR = MODELS_DIR / "reports"
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


def should_include_valuations(args) -> bool:
    """Keep production behavior unchanged while making lab mode safer by default."""
    return args.mode == "production" or args.include_valuations


def should_upsert_training_samples(args) -> bool:
    """Lab runs should stay isolated from DB training-sample side effects."""
    return args.mode == "production" and not args.dry_run


def resolve_lab_validation_size(train_valid_count: int) -> int:
    """Use a small newest-slice validation window for lab-only early stopping."""
    if train_valid_count < 5:
        return 0
    valid_size = max(1, int(train_valid_count * 0.2))
    if train_valid_count - valid_size < 2:
        return 1
    return valid_size


def combine_training_sources(df_obs, df_val, *, include_valuations: bool):
    """Combine ETL outputs and return a small inspectable source summary."""
    import pandas as pd

    if include_valuations and not df_val.empty:
        combined = pd.concat([df_obs, df_val], ignore_index=True)
    else:
        combined = df_obs.copy()

    return combined, {
        "observations": int(len(df_obs)),
        "valuations": int(len(df_val)),
        "valuations_included": bool(include_valuations),
        "combined": int(len(combined)),
    }


def build_model_version(args) -> str:
    """Use separate version naming for lab candidates to avoid touching champion artifacts."""
    date_str = datetime.now().strftime("%Y%m%d")
    if args.mode == "lab":
        return f"valor_lab_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    existing_count = len(list(MODELS_DIR.glob("valor_v*.pkl")))
    return f"valor_v{existing_count + 1}_{date_str}"


def build_artifact_paths(args, model_version: str) -> dict[str, Path | None]:
    """Resolve artifact paths for either production or isolated lab mode."""
    model_filename = f"{model_version}.pkl"
    if args.mode == "lab":
        return {
            "model_path": CANDIDATE_MODELS_DIR / model_filename,
            "latest_path": None,
            "features_path": CANDIDATE_MODELS_DIR / f"{model_version}_features.json",
            "report_path": REPORTS_DIR / f"{model_version}.report.json",
        }

    return {
        "model_path": MODELS_DIR / model_filename,
        "latest_path": MODELS_DIR / "valor_latest.pkl",
        "features_path": MODELS_DIR / "valor_features.json",
        "report_path": REPORTS_DIR / f"{model_version}.report.json",
    }


def _value_counts(series) -> dict[str, int]:
    counts = {}
    for key, value in series.fillna("unknown").value_counts().items():
        counts[str(key)] = int(value)
    return counts


def build_feature_matrix(subset):
    import numpy as np

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


def compute_lab_cv_summary(df, args) -> dict | None:
    """Lab mode only: inspect candidate stability with a small rolling time-series CV summary."""
    from sklearn.base import clone
    from sklearn.metrics import mean_absolute_error
    from sklearn.model_selection import TimeSeriesSplit
    from xgboost import XGBRegressor

    if args.mode != "lab" or len(df) < 10:
        return None

    n_splits = min(3, len(df) - 1)
    if n_splits < 2:
        return None

    scores: list[float] = []
    split_sizes: list[dict[str, int]] = []
    tscv = TimeSeriesSplit(n_splits=n_splits)
    base_model = XGBRegressor(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        verbosity=0,
        tree_method="hist",
        eval_metric="mae",
    )

    for train_idx, test_idx in tscv.split(df):
        train_df = df.iloc[train_idx]
        test_df = df.iloc[test_idx]
        if len(test_df) < 2:
            continue

        X_train = build_feature_matrix(train_df)
        y_train = train_df["price_sek"].values.astype(float)
        X_test = build_feature_matrix(test_df)
        y_test = test_df["price_sek"].values.astype(float)

        model = clone(base_model)
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)
        scores.append(float(mean_absolute_error(y_test, y_pred)))
        split_sizes.append({"train": int(len(train_df)), "test": int(len(test_df))})

    if not scores:
        return None

    return {
        "splits": int(len(scores)),
        "mae_mean": round(sum(scores) / len(scores), 2),
        "mae_min": round(min(scores), 2),
        "mae_max": round(max(scores), 2),
        "split_sizes": split_sizes,
    }


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
    if should_upsert_training_samples(args):
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
    elif args.mode == "lab":
        print("  Lab-läge: observationer skrivs inte till training_sample.")

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
    if should_upsert_training_samples(args):
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
    elif args.mode == "lab":
        print("  Lab-läge: valuations skrivs inte till training_sample.")

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

    df = df.sort_values("observed_at").reset_index(drop=True)
    if args.mode == "lab":
        # Lab mode gets the more advanced train/valid/test split for early stopping.
        test_size = max(2, int(len(df) * 0.2))
        if len(df) - test_size < 3:
            test_size = max(1, len(df) - 2)

        train_valid_df = df.iloc[:-test_size] if test_size < len(df) else df.iloc[:0]
        test_df = df.iloc[-test_size:] if test_size > 0 else df.iloc[:0]

        valid_size = resolve_lab_validation_size(len(train_valid_df))
        if valid_size > 0:
            train_df = train_valid_df.iloc[:-valid_size]
            valid_df = train_valid_df.iloc[-valid_size:]
        else:
            train_df = train_valid_df
            valid_df = train_valid_df.iloc[:0]
    else:
        # Production keeps the simpler existing split until lab candidates prove themselves.
        split_idx = int(len(df) * 0.8)
        train_df = df.iloc[:split_idx]
        valid_df = df.iloc[:0]
        test_df = df.iloc[split_idx:]

    print(f"  Train: {len(train_df)}, Valid: {len(valid_df)}, Test: {len(test_df)}")

    if len(test_df) < 2:
        print("  ✗ Test set för liten")
        if not args.force:
            return None

    X_train = build_feature_matrix(train_df)
    y_train = train_df["price_sek"].values.astype(float)
    X_valid = build_feature_matrix(valid_df) if len(valid_df) else None
    y_valid = valid_df["price_sek"].values.astype(float) if len(valid_df) else None
    X_test = build_feature_matrix(test_df)
    y_test = test_df["price_sek"].values.astype(float)

    print("\n── STEG 4: TRÄNA XGBOOST ──")
    from xgboost import XGBRegressor
    from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error

    model_kwargs = dict(
        n_estimators=500, max_depth=6, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8,
        random_state=42, verbosity=0, tree_method="hist",
        eval_metric="mae",
    )
    if X_valid is not None and y_valid is not None and len(valid_df) > 0:
        model_kwargs["early_stopping_rounds"] = 20

    model = XGBRegressor(**model_kwargs)
    fit_kwargs = {}
    if X_valid is not None and y_valid is not None and len(valid_df) > 0:
        fit_kwargs["eval_set"] = [(X_valid, y_valid)]

    model.fit(X_train, y_train, **fit_kwargs)

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

    cv_summary = compute_lab_cv_summary(df, args)
    if cv_summary:
        print(f"  CV MAE:    {cv_summary['mae_mean']:.0f} kr över {cv_summary['splits']} tids-splits")

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
        "train_start_at": train_df["observed_at"].min().isoformat() if len(train_df) else None,
        "train_end_at": train_df["observed_at"].max().isoformat() if len(train_df) else None,
        "valid_start_at": valid_df["observed_at"].min().isoformat() if len(valid_df) else None,
        "valid_end_at": valid_df["observed_at"].max().isoformat() if len(valid_df) else None,
        "test_start_at": test_df["observed_at"].min().isoformat() if len(test_df) else None,
        "test_end_at": test_df["observed_at"].max().isoformat() if len(test_df) else None,
        "train_source_breakdown": _value_counts(train_df["source_type"]) if "source_type" in train_df.columns else {},
        "valid_source_breakdown": _value_counts(valid_df["source_type"]) if "source_type" in valid_df.columns else {},
        "test_source_breakdown": _value_counts(test_df["source_type"]) if "source_type" in test_df.columns else {},
        "best_iteration": int(model.best_iteration) if getattr(model, "best_iteration", None) is not None else None,
        "lab_cv_summary": cv_summary,
    }


def build_training_report(result: dict, warnings: list[str], args, source_summary: dict, artifact_info: dict) -> dict:
    """Create an inspectable report for either a lab candidate or production run."""
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": args.mode,
        "product": args.product,
        "min_samples": int(args.min_samples),
        "force": bool(args.force),
        "valuations_included": bool(source_summary["valuations_included"]),
        "source_summary": source_summary,
        "metrics": {
            "mae_sek": float(result["mae_sek"]),
            "mape_pct": float(result["mape_pct"]),
            "within_10pct": float(result["within_10pct"]),
            "within_20pct": float(result["within_20pct"]),
            "vs_baseline_mae": float(result["vs_baseline_mae"]),
            "vs_baseline_improvement_pct": float(result["vs_baseline_improvement_pct"]),
        },
        "windows": {
            "train_start_at": result.get("train_start_at"),
            "train_end_at": result.get("train_end_at"),
            "valid_start_at": result.get("valid_start_at"),
            "valid_end_at": result.get("valid_end_at"),
            "test_start_at": result.get("test_start_at"),
            "test_end_at": result.get("test_end_at"),
        },
        "train_source_breakdown": result.get("train_source_breakdown") or {},
        "valid_source_breakdown": result.get("valid_source_breakdown") or {},
        "test_source_breakdown": result.get("test_source_breakdown") or {},
        "best_iteration": result.get("best_iteration"),
        "lab_cv_summary": result.get("lab_cv_summary"),
        "feature_importance": result["feature_importance"],
        "warnings": warnings,
        "artifacts": {
            "model_path": str(artifact_info["model_path"]),
            "features_path": str(artifact_info["features_path"]),
            "report_path": str(artifact_info["report_path"]),
            "latest_path": str(artifact_info["latest_path"]) if artifact_info.get("latest_path") else None,
        },
        "activation": {
            "is_candidate_only": bool(args.mode == "lab"),
            "activated": bool(artifact_info["activated"]),
        },
    }


def step_save(result: dict, warnings: list[str], args, source_summary: dict) -> dict:
    """Save model artifacts and, in production mode only, register/activate the champion."""
    import joblib

    print("\n── STEG 6: SPARA ──")

    MODELS_DIR.mkdir(exist_ok=True)
    CANDIDATE_MODELS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    model_version = build_model_version(args)
    artifact_info = {
        "version": model_version,
        **build_artifact_paths(args, model_version),
        "activated": False,
    }

    if args.dry_run:
        print(f"  [DRY RUN] Skulle sparat {artifact_info['model_path'].name}")
        return artifact_info

    joblib.dump(result["model"], artifact_info["model_path"])
    artifact_info["features_path"].write_text(json.dumps(FEATURE_NAMES, indent=2), encoding="utf-8")

    if artifact_info["latest_path"] is not None:
        shutil.copy2(artifact_info["model_path"], artifact_info["latest_path"])
        print(f"  Sparade: {artifact_info['model_path'].name}")
        print(f"  Kopierade: {artifact_info['latest_path'].name}")
        print(f"  Features: {artifact_info['features_path'].name}")
    else:
        print(f"  Sparade kandidat: {artifact_info['model_path'].name}")
        print(f"  Features: {artifact_info['features_path'].name}")
        print("  Champion oförändrad (lab-läge).")

    # Register in DB
    if args.mode == "production":
        try:
            from sqlalchemy import text
            engine = get_sync_engine()

            improvement = result.get("vs_baseline_improvement_pct", 0)
            if not args.force and improvement < 0:
                print(f"  ⚠ Modell är {improvement}% sämre än baseline — aktiveras INTE.")
                print("  Använd --force för att aktivera ändå.")
                should_activate = False
            else:
                should_activate = True

            with engine.begin() as conn:
                # Deactivate previous champion only when we are actually promoting.
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
                    "mf": artifact_info["model_path"].name,
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
            artifact_info["activated"] = should_activate
            print(f"  Registrerad i DB: is_active={should_activate}")
        except Exception as exc:
            print(f"  ⚠ Kunde inte registrera i DB: {exc}")

    report = build_training_report(result, warnings, args, source_summary, artifact_info)
    artifact_info["report_path"].write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"  Rapport: {artifact_info['report_path'].name}")

    return artifact_info


def main():
    parser = argparse.ArgumentParser(description="VALOR Training Pipeline")
    parser.add_argument(
        "--mode",
        choices=["production", "lab"],
        default="production",
        help="Production updates champion; lab saves an isolated candidate only.",
    )
    parser.add_argument("--dry-run", action="store_true", help="ETL only, no training")
    parser.add_argument("--force", action="store_true", help="Train even with insufficient data")
    parser.add_argument("--min-samples", type=int, default=50, help="Minimum samples required")
    parser.add_argument("--product", type=str, default=None, help="Train on specific product_key")
    parser.add_argument(
        "--include-valuations",
        action="store_true",
        help="Include valuation-derived samples in lab mode. Production already includes them.",
    )
    args = parser.parse_args()

    print("════════════════════════════════════")
    print("  VALOR TRÄNINGSPIPELINE")
    print("════════════════════════════════════")
    if args.mode == "lab":
        print("  Läge: LAB (isolerad kandidat, champion lämnas orörd)")

    engine = get_sync_engine()
    df_obs = step_etl(engine, args)
    df_val = step_etl_valuations(engine, args)

    include_valuations = should_include_valuations(args)
    df, source_summary = combine_training_sources(
        df_obs,
        df_val,
        include_valuations=include_valuations,
    )
    print(
        f"\n  Totalt kombinerade samples: {source_summary['combined']} "
        f"({source_summary['observations']} obs + "
        f"{source_summary['valuations'] if source_summary['valuations_included'] else 0} val)"
    )
    if args.mode == "lab" and not include_valuations and len(df_val) > 0:
        print("  Lab-default: valuations hölls utanför för att undvika självförstärkning.")

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

    artifact_info = step_save(result, warnings, args, source_summary)

    print(f"""
════════════════════════════════════
  VALOR TRÄNINGSRESULTAT
════════════════════════════════════
  Version:       {artifact_info['version']}
  Läge:          {args.mode}
  Samples:       {result['train_count']} train / {result['test_count']} test
  MAE:           {result['mae_sek']:.0f} kr
  MAPE:          {result['mape_pct']:.1f}%
  Inom ±10%:     {result['within_10pct']:.1f}%
  Inom ±20%:     {result['within_20pct']:.1f}%
  Rapport:       {artifact_info['report_path']}
  Varningar:     {warnings or ['Inga']}
════════════════════════════════════""")


if __name__ == "__main__":
    main()
