# stdlib
import json
from datetime import datetime
from pathlib import Path

# third-party
import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

DATA_URL = "https://archive.ics.uci.edu/ml/machine-learning-databases/wine-quality/winequality-red.csv"
MODELS_DIR = Path(__file__).parent.parent / "models"


def load_data(url: str) -> pd.DataFrame:
    return pd.read_csv(url, sep=";")


def train_pipeline(df: pd.DataFrame, target: str):
    X = df.drop(target, axis=1)
    y = df[target]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    pipeline = Pipeline(
        [
            ("scaler", StandardScaler()),
            ("clf", RandomForestClassifier(n_estimators=100, random_state=42)),
        ]
    )

    cv_scores = cross_val_score(pipeline, X_train, y_train, cv=5, scoring="accuracy")
    pipeline.fit(X_train, y_train)

    return pipeline, X_test, y_test, X.columns.to_list(), cv_scores


def save_artifacts(pipeline, feature_names, accuracy):
    joblib.dump(pipeline, MODELS_DIR / "pipeline.joblib")

    metadata = {
        "accuracy": accuracy,
        "feature_names": feature_names,
        "trained_at": datetime.now().isoformat(),
        "model_params": pipeline.named_steps["clf"].get_params(),
    }

    with open(MODELS_DIR / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)


def main():
    wine_df = load_data(DATA_URL)
    pipeline, X_test, y_test, feature_names, cv_scores = train_pipeline(
        wine_df, "quality"
    )
    y_pred = pipeline.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    save_artifacts(pipeline, feature_names, accuracy)
    print(f"Cross-validation scores: {cv_scores}")
    print(
        f"Mean CV accuracy: {cv_scores.mean():.3f} (+/- {cv_scores.std() * 2:.3f})"
    )  # ±2σ ≈ 95% confidence interval
    print(classification_report(y_test, y_pred, zero_division=0))


if __name__ == "__main__":
    main()
