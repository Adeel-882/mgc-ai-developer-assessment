"""Run once from the repository root: python train_model.py."""

import json
import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from lead_scoring import ROOT, MODEL_PATH, FEATURES, CATEGORICAL_FEATURES, NUMERIC_FEATURES, prepare_features


def canonical_leads(raw):
    if raw["crm_record_hash"].isna().any():
        raise ValueError("A missing CRM hash requires manual duplicate review.")
    duplicates = raw[raw.duplicated("crm_record_hash", keep=False)]
    comparison = [c for c in raw.columns if c not in ["lead_id", "crm_record_hash"]]
    if duplicates.groupby("crm_record_hash")[comparison].nunique(dropna=False).gt(1).any().any():
        raise ValueError("Repeated CRM hashes have conflicting data; review before merging.")
    return raw.sort_values("lead_id").drop_duplicates("crm_record_hash").reset_index(drop=True)


def train():
    raw = pd.read_csv(ROOT / "leads.csv", dtype={"crm_record_hash": str})
    data = canonical_leads(raw)
    train_rows, test_rows = train_test_split(data, test_size=0.2, stratify=data["converted"], random_state=42)
    assert set(train_rows.crm_record_hash).isdisjoint(test_rows.crm_record_hash)
    numeric = Pipeline([("impute", SimpleImputer(strategy="median", add_indicator=True)),
                        ("scale", StandardScaler())])
    categorical = Pipeline([("impute", SimpleImputer(strategy="constant", fill_value="unknown")),
                            ("encode", OneHotEncoder(handle_unknown="ignore"))])
    preprocess = ColumnTransformer([("numeric", numeric, NUMERIC_FEATURES),
                                    ("categorical", categorical, CATEGORICAL_FEATURES)])
    model = Pipeline([("preprocess", preprocess),
                      ("classifier", LogisticRegression(max_iter=1000, random_state=42))])
    model.fit(prepare_features(train_rows), train_rows["converted"])
    probabilities = model.predict_proba(prepare_features(test_rows))[:, 1]
    metrics = {
        "raw_rows": len(raw), "raw_converted": int(raw.converted.sum()),
        "raw_conversion_rate": float(raw.converted.mean()),
        "duplicate_rows_removed": len(raw) - len(data),
        "canonical_rows": len(data), "canonical_converted": int(data.converted.sum()),
        "canonical_conversion_rate": float(data.converted.mean()),
        "train_rows": len(train_rows), "test_rows": len(test_rows),
        "test_converted": int(test_rows.converted.sum()),
        "test_prevalence_baseline": float(test_rows.converted.mean()),
        "average_precision": float(average_precision_score(test_rows.converted, probabilities)),
        "roc_auc": float(roc_auc_score(test_rows.converted, probabilities)),
        "random_state": 42, "features": FEATURES,
    }
    MODEL_PATH.parent.mkdir(exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    (MODEL_PATH.parent / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    train()
