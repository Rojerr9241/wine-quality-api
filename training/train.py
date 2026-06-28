# stdlib
import json
from datetime import datetime
from pathlib import Path

# third-party
import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

DATA_URL = "https://archive.ics.uci.edu/ml/machine-learning-databases/wine-quality/winequality-red.csv"
MODELS_DIR = Path(__file__).parent.parent / "models"


def load_data(url):
    return pd.read_csv(url, sep=";")


def train_pipeline(df, target):
    X = df.drop(target, axis=1)
    y = df[target]

    X_train, X_test, y_train, y_test = train_test_split(
        X.to_numpy(), y.to_numpy(), test_size=0.2, random_state=42
    )

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)  # learns μ, σ from train only — prevents data leakage
    X_test_scaled = scaler.transform(X_test)         # applies the same μ, σ learned from train

    clf = RandomForestClassifier(n_estimators=100, random_state=42)
    clf.fit(X_train_scaled, y_train)

    return clf, scaler, X_test_scaled, y_test, X.columns.to_list()


def save_artifacts(model, scaler, feature_names, accuracy):
    joblib.dump(model, MODELS_DIR / "model.joblib")
    joblib.dump(scaler, MODELS_DIR / "scaler.joblib")

    metadata = {
        "accuracy": accuracy,
        "feature_names": feature_names,
        "trained_at": datetime.now().isoformat(),
        "model_params": model.get_params(),
    }

    with open(MODELS_DIR / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)


def main():
    wine_df = load_data(DATA_URL)
    model, scaler, X_test, y_test, feature_names = train_pipeline(wine_df, "quality")
    y_pred = model.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    save_artifacts(model, scaler, feature_names, accuracy)
    print(classification_report(y_test, y_pred, zero_division=0))


if __name__ == "__main__":
    main()