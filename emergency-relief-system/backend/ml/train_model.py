"""Model training pipeline: baseline vs ensemble comparison with honest metrics."""
from __future__ import annotations

import json
import time
from pathlib import Path

import joblib
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split

from .preprocessing import TARGET, clean_dataframe, encode_features, load_dataset

MODEL_CANDIDATES = {
    "LinearRegression": LinearRegression,
    "RandomForestRegressor": lambda: RandomForestRegressor(
        n_estimators=220, max_depth=14, min_samples_leaf=2, random_state=42, n_jobs=-1
    ),
    "GradientBoostingRegressor": lambda: GradientBoostingRegressor(
        n_estimators=250, learning_rate=0.06, max_depth=3, random_state=42
    ),
}


def evaluate(name: str, model, X_test, y_test) -> dict:
    predictions = model.predict(X_test)
    mae = float(mean_absolute_error(y_test, predictions))
    rmse = float(mean_squared_error(y_test, predictions) ** 0.5)
    r2 = float(r2_score(y_test, predictions))
    return {"model": name, "MAE": round(mae, 2), "RMSE": round(rmse, 2), "R2": round(r2, 4)}


def train(dataset_path: str, model_out: str, metrics_out: str) -> dict:
    df = clean_dataframe(load_dataset(dataset_path))
    if len(df) < 30:
        raise ValueError(f"Dataset too small to train ({len(df)} usable rows)")
    X = encode_features(df)
    y = df[TARGET]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    results = {}
    fitted = {}
    for name, factory in MODEL_CANDIDATES.items():
        model = factory()
        start = time.time()
        model.fit(X_train, y_train)
        results[name] = evaluate(name, model, X_test, y_test)
        results[name]["train_seconds"] = round(time.time() - start, 2)
        fitted[name] = model
        print(f"{name:<28} MAE={results[name]['MAE']:>10.2f} "
              f"RMSE={results[name]['RMSE']:>10.2f} R2={results[name]['R2']:.4f}")

    best_name = max(results, key=lambda n: results[n]["R2"])
    best_model = fitted[best_name]

    Path(model_out).parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(best_model, model_out)

    metrics = {
        "trained_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "dataset_rows": int(len(df)),
        "features": list(X.columns),
        "target": TARGET,
        "best_model": best_name,
        "selection_criterion": "highest R² on held-out test split (20%)",
        "results": results,
        "responsible_ai_note": (
            "Metrics are measured on synthetic demo data and describe this dataset only; "
            "forecasts are recommendations requiring human review."
        ),
    }
    Path(metrics_out).write_text(json.dumps(metrics, indent=2))
    print(f"\nBest model: {best_name} (saved to {model_out})")
    return metrics


def main() -> None:
    here = Path(__file__).resolve().parent
    dataset = str(here / "dataset.csv")
    if not Path(dataset).exists():
        from .generate_dataset import generate

        generate().to_csv(dataset, index=False)
        print(f"Dataset not found; generated a fresh one at {dataset}")
    metrics = train(
        dataset,
        model_out=str(here / "model.pkl"),
        metrics_out=str(here / "metrics.json"),
    )
    print(json.dumps({"best_model": metrics["best_model"], "rows": metrics["dataset_rows"]}, indent=2))


if __name__ == "__main__":
    main()
