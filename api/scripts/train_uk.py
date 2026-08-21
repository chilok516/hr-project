"""Train the 4 UK models on uk_features.csv -> data/models_uk/ (does not touch HK models)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from loguru import logger

from config import DATA_PROCESSED, DATA_MODELS
from src.models.train import RacePredictor

MODELS_UK = DATA_MODELS.parent / "models_uk"


def main():
    MODELS_UK.mkdir(parents=True, exist_ok=True)

    path = DATA_PROCESSED / "uk_features.csv"
    if not path.exists():
        logger.error(f"{path} not found — run build_uk_features.py first")
        return

    df = pd.read_csv(path, low_memory=False)
    df["race_date"] = pd.to_datetime(df["race_date"], errors="coerce")
    df = df.dropna(subset=["race_date"])
    logger.info(f"Training on {len(df)} rows, {df['race_date'].nunique()} dates")

    predictor = RacePredictor(model_dir=MODELS_UK)
    predictor.train_all(df)
    predictor.save_all()

    for name in ["fundamental", "top2", "market", "place"]:
        model = getattr(predictor, name)
        imp = model.get_feature_importance()
        top = ", ".join(f"{r['feature']}({r['importance']:.0f})" for _, r in imp.head(5).iterrows())
        logger.info(f"[{name}] top features: {top}")


if __name__ == "__main__":
    main()
