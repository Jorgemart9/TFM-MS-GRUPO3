"""
inference.py — Inferencia y monitorización de drift para detección de fraude.

Uso:
    python inference.py --input data.csv

Flujo:
  1. Carga modelo y scaler desde models/.
  2. Preprocesa el CSV de entrada (mismo esquema que creditcard.csv).
  3. Genera predicciones y probabilidades.
  4. Divide el input en dos ventanas temporales (50/50) y calcula:
       - Data drift por feature: test KS (p-value < 0.05 → drift).
       - Concept drift: F1, Recall, ROC-AUC por ventana.
  5. Guarda resultados en metrics/drift_metrics.json.
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.stats import ks_2samp
from sklearn.metrics import f1_score, recall_score, roc_auc_score

# ---------------------------------------------------------------------------
# Logging
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
MODELS_DIR = BASE_DIR / "models"
METRICS_DIR = BASE_DIR / "metrics"

KS_ALPHA = 0.05  # umbral de significación para detectar data drift


# ---------------------------------------------------------------------------
# Funciones de carga
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inferencia y monitorización de drift (fraude en tarjetas)."
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Ruta al CSV de datos nuevos (mismo esquema que creditcard.csv).",
    )
    return parser.parse_args()


def load_artifacts():
    """Carga modelo XGBoost y scaler desde disco."""
    model_path = MODELS_DIR / "model.pkl"
    scaler_path = MODELS_DIR / "scaler.pkl"

    for p in (model_path, scaler_path):
        if not p.exists():
            raise FileNotFoundError(
                f"Artefacto no encontrado: {p}. Ejecuta train.py primero."
            )

    model = joblib.load(model_path)
    scaler = joblib.load(scaler_path)
    logger.info("Modelo y scaler cargados desde %s", MODELS_DIR)
    return model, scaler


def load_input(path: Path) -> pd.DataFrame:
    """Carga y valida el CSV de entrada."""
    if not path.exists():
        raise FileNotFoundError(f"Fichero de entrada no encontrado: {path}")

    df = pd.read_csv(path)
    required = {"Time", "Amount"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Columnas requeridas ausentes en el input: {missing}")

    logger.info("Input cargado: %d filas, %d columnas", len(df), df.shape[1])
    return df


# ---------------------------------------------------------------------------
# Preprocesamiento e inferencia
# ---------------------------------------------------------------------------

def preprocess(df: pd.DataFrame, scaler) -> tuple[pd.DataFrame, list[str]]:
    """Escala Amount y devuelve la matriz de features junto con sus nombres."""
    df = df.sort_values("Time").reset_index(drop=True)
    feature_cols = [c for c in df.columns if c not in ("Time", "Class")]

    X = df[feature_cols].copy()
    X["Amount"] = scaler.transform(X[["Amount"]])
    return X, feature_cols


def run_inference(model, X: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Genera predicciones de clase y probabilidades de fraude."""
    y_pred = model.predict(X)
    y_prob = model.predict_proba(X)[:, 1]
    n_fraud = int(y_pred.sum())
    logger.info(
        "Inferencia completada: %d transacciones, %d fraudes detectados (%.3f%%)",
        len(y_pred), n_fraud, 100 * n_fraud / max(len(y_pred), 1),
    )
    return y_pred, y_prob


# ---------------------------------------------------------------------------
# Monitorización
# ---------------------------------------------------------------------------

def split_windows(
    df: pd.DataFrame,
    X: pd.DataFrame,
    y_pred: np.ndarray,
    y_prob: np.ndarray,
) -> tuple[dict, dict]:
    """
    Divide el input en dos ventanas 50/50 (primera y segunda mitad temporal).
    Devuelve un dict por ventana con los arrays necesarios para el análisis.
    """
    mid = len(df) // 2

    def _window(start: int, end: int) -> dict:
        return {
            "df": df.iloc[start:end],
            "X": X.iloc[start:end],
            "y_pred": y_pred[start:end],
            "y_prob": y_prob[start:end],
        }

    w1 = _window(0, mid)
    w2 = _window(mid, len(df))
    logger.info(
        "Ventanas: W1=%d filas, W2=%d filas", len(w1["df"]), len(w2["df"])
    )
    return w1, w2


def concept_drift_metrics(window: dict, has_labels: bool) -> dict:
    """
    Calcula F1, Recall y ROC-AUC para una ventana.
    Si no hay etiquetas reales disponibles, devuelve None en cada métrica.
    """
    if not has_labels:
        return {"f1": None, "recall": None, "roc_auc": None}

    y_true = window["df"]["Class"].values
    y_pred = window["y_pred"]
    y_prob = window["y_prob"]

    # ROC-AUC requiere al menos dos clases en y_true
    try:
        roc = float(roc_auc_score(y_true, y_prob))
    except ValueError:
        roc = None

    return {
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "roc_auc": roc,
    }


def detect_data_drift(
    w1: dict,
    w2: dict,
    feature_cols: list[str],
    alpha: float = KS_ALPHA,
) -> tuple[list[str], dict]:
    """
    Aplica el test KS a cada feature entre W1 y W2.
    Devuelve la lista de features con drift y un dict detallado con los p-values.
    """
    drift_features: list[str] = []
    detail: dict[str, dict] = {}

    for feat in feature_cols:
        stat, p_value = ks_2samp(
            w1["X"][feat].values, w2["X"][feat].values
        )
        has_drift = bool(p_value < alpha)
        detail[feat] = {"ks_statistic": float(stat), "p_value": float(p_value)}
        if has_drift:
            drift_features.append(feat)

    logger.info(
        "Data drift: %d/%d features con drift (p < %.2f)",
        len(drift_features), len(feature_cols), alpha,
    )
    return drift_features, detail


def window_summary(window: dict, concept: dict) -> dict:
    """Construye el resumen de una ventana para el JSON de salida."""
    n_fraud = int(window["y_pred"].sum())
    n_total = len(window["y_pred"])
    return {
        "n_samples": n_total,
        "n_fraud_predicted": n_fraud,
        "fraud_rate": round(n_fraud / max(n_total, 1), 6),
        "concept_drift_metrics": concept,
    }


# ---------------------------------------------------------------------------
# Persistencia
# ---------------------------------------------------------------------------

def save_drift_metrics(payload: dict) -> None:
    """Guarda el dict en metrics/drift_metrics.json."""
    METRICS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = METRICS_DIR / "drift_metrics.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    logger.info("Métricas de drift guardadas en %s", output_path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()

    try:
        model, scaler = load_artifacts()
        df = load_input(args.input)
        X, feature_cols = preprocess(df, scaler)
        y_pred, y_prob = run_inference(model, X)

        has_labels = "Class" in df.columns
        if not has_labels:
            logger.warning(
                "Columna 'Class' no encontrada; las métricas de concept drift serán None."
            )

        w1, w2 = split_windows(df, X, y_pred, y_prob)

        concept_w1 = concept_drift_metrics(w1, has_labels)
        concept_w2 = concept_drift_metrics(w2, has_labels)

        drift_features, drift_detail = detect_data_drift(w1, w2, feature_cols)

        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "window_1": window_summary(w1, concept_w1),
            "window_2": window_summary(w2, concept_w2),
            "data_drift_features": drift_features,
            "n_features_with_drift": len(drift_features),
            "data_drift_detail": drift_detail,
        }

        save_drift_metrics(payload)
        logger.info("Pipeline de inferencia y monitorización completado.")

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
