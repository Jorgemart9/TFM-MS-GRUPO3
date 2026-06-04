"""
train.py — Entrenamiento del modelo XGBoost para detección de fraude.

Flujo:
  1. Carga creditcard.csv desde la misma carpeta que este script.
  2. Split temporal 70/30 (ordenado por columna Time).
  3. Escala Amount con StandardScaler; V1-V28 ya vienen normalizadas.
  4. Entrena XGBoost con scale_pos_weight proporcional al desbalanceo.
  5. Evalúa sobre test y guarda métricas en metrics/metrics.json.
  6. Persiste modelo en models/model.pkl y scaler en models/scaler.pkl.
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

# ---------------------------------------------------------------------------
# Configuración de logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent
DATA_PATH = BASE_DIR / "models" / "creditcard.csv"
MODELS_DIR = BASE_DIR / "models"
METRICS_DIR = BASE_DIR / "metrics"

MODEL_VERSION = "v1"


# ---------------------------------------------------------------------------
# Funciones
# ---------------------------------------------------------------------------

def load_data(path: Path) -> pd.DataFrame:
    """Carga el dataset desde *path* y valida columnas mínimas requeridas."""
    logger.info("Cargando datos desde %s", path)
    df = pd.read_csv(path)
    required = {"Time", "Amount", "Class"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Columnas requeridas ausentes en el CSV: {missing}")
    logger.info("Dataset cargado: %d filas, %d columnas", len(df), df.shape[1])
    return df


def temporal_split(df: pd.DataFrame, train_ratio: float = 0.70):
    """Divide el dataframe de forma temporal (ordena por Time)."""
    df_sorted = df.sort_values("Time").reset_index(drop=True)
    cutoff = int(len(df_sorted) * train_ratio)
    train = df_sorted.iloc[:cutoff].copy()
    test = df_sorted.iloc[cutoff:].copy()
    logger.info(
        "Split temporal: train=%d filas (%.1f%%), test=%d filas (%.1f%%)",
        len(train), 100 * len(train) / len(df_sorted),
        len(test), 100 * len(test) / len(df_sorted),
    )
    return train, test


def build_features(
    train: pd.DataFrame,
    test: pd.DataFrame,
):
    """
    Escala Amount con StandardScaler ajustado sobre train.
    Devuelve X_train, X_test, y_train, y_test y el scaler ajustado.
    """
    feature_cols = [c for c in train.columns if c not in ("Time", "Class")]
    scaler = StandardScaler()

    X_train = train[feature_cols].copy()
    X_test = test[feature_cols].copy()

    X_train["Amount"] = scaler.fit_transform(X_train[["Amount"]])
    X_test["Amount"] = scaler.transform(X_test[["Amount"]])

    y_train = train["Class"].values
    y_test = test["Class"].values

    logger.info("Features: %d columnas", len(feature_cols))
    logger.info(
        "Distribución de clases en train — fraude: %d (%.4f%%)",
        y_train.sum(), 100 * y_train.mean(),
    )
    return X_train, X_test, y_train, y_test, scaler


def compute_scale_pos_weight(y_train: np.ndarray) -> float:
    """Calcula scale_pos_weight = negativos / positivos."""
    n_neg = (y_train == 0).sum()
    n_pos = (y_train == 1).sum()
    ratio = n_neg / n_pos
    logger.info(
        "scale_pos_weight = %d/%d = %.2f", n_neg, n_pos, ratio
    )
    return ratio


def train_model(
    X_train: pd.DataFrame,
    y_train: np.ndarray,
    scale_pos_weight: float,
) -> XGBClassifier:
    """Entrena un XGBClassifier con los parámetros base."""
    logger.info("Entrenando XGBoost (scale_pos_weight=%.2f)…", scale_pos_weight)
    model = XGBClassifier(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        scale_pos_weight=scale_pos_weight,
        use_label_encoder=False,
        eval_metric="logloss",
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_train, y_train)
    logger.info("Entrenamiento completado.")
    return model


def evaluate(
    model: XGBClassifier,
    X_test: pd.DataFrame,
    y_test: np.ndarray,
) -> dict:
    """Calcula métricas sobre el conjunto de test."""
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]

    metrics = {
        "accuracy": float(accuracy_score(y_test, y_pred)),
        "precision": float(precision_score(y_test, y_pred, zero_division=0)),
        "recall": float(recall_score(y_test, y_pred, zero_division=0)),
        "f1": float(f1_score(y_test, y_pred, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_test, y_prob)),
    }
    for k, v in metrics.items():
        logger.info("  %-12s %.4f", k, v)
    return metrics


def save_artifacts(
    model: XGBClassifier,
    scaler: StandardScaler,
    metrics: dict,
) -> None:
    """Persiste modelo, scaler y métricas en disco."""
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    METRICS_DIR.mkdir(parents=True, exist_ok=True)

    model_path = MODELS_DIR / "model.pkl"
    scaler_path = MODELS_DIR / "scaler.pkl"
    metrics_path = METRICS_DIR / "metrics.json"

    joblib.dump(model, model_path)
    logger.info("Modelo guardado en %s", model_path)

    joblib.dump(scaler, scaler_path)
    logger.info("Scaler guardado en %s", scaler_path)

    payload = {
        "model_version": MODEL_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **metrics,
    }
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    logger.info("Métricas guardadas en %s", metrics_path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    try:
        df = load_data(DATA_PATH)
        train, test = temporal_split(df, train_ratio=0.70)
        X_train, X_test, y_train, y_test, scaler = build_features(train, test)
        spw = compute_scale_pos_weight(y_train)
        model = train_model(X_train, y_train, scale_pos_weight=spw)
        logger.info("Evaluando modelo en test…")
        metrics = evaluate(model, X_test, y_test)
        save_artifacts(model, scaler, metrics)
        logger.info("Pipeline de entrenamiento completado correctamente.")
    except FileNotFoundError as exc:
        logger.error("Fichero no encontrado: %s", exc)
        sys.exit(1)
    except ValueError as exc:
        logger.error("Error de validación: %s", exc)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        logger.error("Error inesperado: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
