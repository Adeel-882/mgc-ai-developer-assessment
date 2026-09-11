"""Shared intake features and preprocessing for training and scoring."""

from functools import lru_cache
from pathlib import Path
import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
MODEL_PATH = ROOT / "model" / "lead_model.joblib"
CATEGORICAL_FEATURES = ["source", "city", "area", "property_type"]
NUMERIC_FEATURES = ["budget_pkr_lac", "bedrooms", "agent_experience_years",
                    "is_overseas", "referred_by_existing_client"]
FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES
CITY_ALIASES = {"isb": "islamabad", "rwp": "rawalpindi", "khi": "karachi"}


def prepare_features(data):
    frame = pd.DataFrame(data).reindex(columns=FEATURES).copy()
    for column in CATEGORICAL_FEATURES:
        frame[column] = frame[column].map(lambda value: str(value).strip().lower() if pd.notna(value) and str(value).strip() else np.nan)
    frame["city"] = frame["city"].replace(CITY_ALIASES)
    for column in NUMERIC_FEATURES:
        original = frame[column]
        frame[column] = pd.to_numeric(original.replace("", np.nan), errors="raise")
        if ((frame[column] < 0) | np.isinf(frame[column])).any():
            raise ValueError(f"{column} must be a finite, non-negative number.")
    for column in ["is_overseas", "referred_by_existing_client"]:
        if not frame[column].dropna().isin([0, 1]).all():
            raise ValueError(f"{column} must be 0 or 1.")
    residential = ~frame["property_type"].isin(["plot", "commercial shop"])
    beds = frame.loc[residential, "bedrooms"].dropna()
    if not beds.isin([1, 2, 3, 4, 5]).all():
        raise ValueError("Residential bedrooms must be an integer from 1 to 5.")
    # Missing bedrooms are structural for these property types in the supplied CSV.
    frame.loc[~residential, "bedrooms"] = 0
    return frame


@lru_cache(maxsize=1)
def load_model():
    if not MODEL_PATH.exists():
        raise FileNotFoundError("Model not found. Run: python train_model.py")
    return joblib.load(MODEL_PATH)


def score_lead(details):
    """Return an intake conversion probability; unknown fields are not predictors."""
    if not any(details.get(key) is not None and details.get(key) != "" for key in FEATURES):
        raise ValueError("Enter at least one intake feature.")
    return float(load_model().predict_proba(prepare_features([details]))[0, 1])
