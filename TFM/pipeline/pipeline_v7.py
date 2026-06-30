# pipeline_v7.py
"""Pipeline V7 - Credit Risk MLOps (cost-optimized, production-oriented).

Cambios frente a v6 (bugs corregidos y mejoras):

  CORRECCIÓN DE SESGOS / BUGS
  1. El modelo campeón se elige por el COSTE EN VALIDACIÓN, no en test
     (en v6 se elegía por test -> sesgo optimista / fuga de selección).
  2. La simulación de roll-out usa el UMBRAL ÓPTIMO de cada modelo (no 0.5)
     y evalúa ambos modelos sobre la MISMA población, además de un test de
     significancia (bootstrap) del ahorro de coste challenger vs baseline.
  3. SHAP y fairness usan SIEMPRE el x_test del feature-set del campeón
     (en v6 se usaba el x_test residual del bucle -> frágil).
  4. Todos los artefactos de evaluación se registran dentro de un run de
     MLflow explícito (en v6 caían en un run anónimo).

  MEJORAS DE MODELO
  5. La búsqueda de hiperparámetros optimiza 'average_precision' (PR-AUC),
     más adecuado que ROC-AUC con clases desbalanceadas.
  6. Probabilidades CALIBRADas (isotónica) -> los costes y umbrales son fiables.
  7. scale_pos_weight ya NO se capa a 2.0; se usa el desbalance real.
  8. Sin StandardScaler para árboles; OneHotEncoder con max_categories.
  9. Fairness con varias métricas (paridad demográfica + equalized odds) y
     varias variables sensibles configurables.

  PRODUCCIÓN (despliegue en MS)
 10. El campeón se registra como pyfunc que LLEVA EMBEBIDO su umbral de coste,
     de modo que en serving la decisión es directa (no se pierde el umbral).
 11. Lectura de datos robusta a encoding; clasificación del target sin depender
     de cadenas con mojibake.
 12. Parámetros por línea de comandos / logging en lugar de print.

El challenger es CatBoost (como anunciaba el README); si CatBoost no está
instalado, se usa un XGBoost de mayor capacidad como challenger de respaldo.
"""

import argparse
import json
import logging
import unicodedata
import warnings
from datetime import timedelta
from pathlib import Path

import joblib
import mlflow
import mlflow.pyfunc
import mlflow.sklearn
import numpy as np
import pandas as pd
import shap
from lightgbm import LGBMClassifier
from sklearn.base import clone
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    f1_score,
    make_scorer,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import RandomizedSearchCV, TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from xgboost import XGBClassifier

from fairlearn.metrics import (
    demographic_parity_difference,
    equalized_odds_difference,
)

# CatBoost es opcional: el README lo anuncia como challenger, pero si no está
# instalado seguimos funcionando con un challenger XGBoost de respaldo.
try:
    from catboost import CatBoostClassifier

    CATBOOST_AVAILABLE = True
except ImportError:  # pragma: no cover
    CATBOOST_AVAILABLE = False

warnings.filterwarnings("ignore")
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("pipeline_v7")

# ---------------------------------------------------------------------------
# Configuración (valores por defecto; sobreescribibles por CLI)
# ---------------------------------------------------------------------------
DEFAULTS = dict(
    # Rutas relativas a la raíz del repo (ejecutar: python TFM/pipeline/pipeline_v7.py)
    data_path="TFM/data/lending_club.csv",
    sample_fraction=0.10,      # subir a 1.0 para el entrenamiento definitivo
    random_state=42,
    experiment_name="Credit_Risk_OOT_CostOptimized_v7",
    registered_model_name="Champion_Credit_Risk_CostOptimized_v7",
    tracking_uri="sqlite:///TFM/artifacts/mlflow.db",
    artifact_dir="TFM/artifacts/v7",
    n_iter=8,
    calibrate=True,
    n_bootstrap=1000,
    # Tasa mínima de solicitantes que deben ser APROBADOS (no rechazados).
    # 0.0 = sin restricción (solo coste). 0.70 = aprobar al menos el 70%.
    min_approval_rate=0.70,
    # Política de umbral:
    #   "approval_target" -> umbral = cuantil que aprueba min_approval_rate en la
    #       ventana más reciente (robusto al drift; controla FP/precision).
    #   "cost"            -> umbral de mínimo coste en validación (sujeto a la
    #       restricción de aprobación); sensible al drift temporal.
    threshold_mode="approval_target",
)

# Supuestos de coste de negocio (€). Documentados y parametrizables.
#   FP = aprobar/rechazar erróneamente a un cliente sano (coste de oportunidad).
#   FN = conceder crédito a un cliente que impaga (pérdida esperada).
COST_FALSE_POSITIVE = 2700
COST_FALSE_NEGATIVE = 13500
THRESHOLD_GRID = np.round(np.arange(0.05, 0.96, 0.01), 2)

# Variables sensibles para el análisis de equidad (las presentes se usan).
SENSITIVE_FEATURES = ["tipo_vivienda"]

# Columnas de fuga de información (data leakage): se conocen DURANTE la vida del
# préstamo, no en el momento de la decisión.
LEAKAGE_COLS = [
    "capital_pendiente", "total_pagado", "capital_pagado", "intereses_pagados",
    "fecha_ultimo_pago", "importe_ultimo_pago", "fecha_proximo_pago",
    "plan_pagos_activo", "importe_financiado", "importe_no_financiado",
    "ratio_financiacion", "estado_prestamo", "fecha_emision",
    "fecha_primera_linea_credito", "tipo_interes", "target",
]


# ---------------------------------------------------------------------------
# Carga de datos robusta a encoding
# ---------------------------------------------------------------------------
def _norm(value):
    """Minúsculas + sin acentos: comparación robusta a encoding/mojibake."""
    s = unicodedata.normalize("NFKD", str(value))
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


def load_data(path, sample_fraction, random_state):
    """Lee el CSV (muestreo reproducible) probando varios encodings."""
    rng = np.random.RandomState(random_state)
    skip = (
        None
        if sample_fraction >= 1.0
        else (lambda i: i > 0 and rng.random_sample() > sample_fraction)
    )
    last_err = None
    for enc in ("utf-8", "latin-1"):
        try:
            return pd.read_csv(path, sep=";", header=0, skiprows=skip, encoding=enc)
        except UnicodeDecodeError as err:  # pragma: no cover
            last_err = err
    raise last_err


# ---------------------------------------------------------------------------
# Limpieza y feature engineering (igual que v6, encoding robusto)
# ---------------------------------------------------------------------------
def clean_base(data):
    d = data.copy()

    if "porcentaje_uso_credito_revolving" in d.columns:
        d["porcentaje_uso_credito_revolving"] = (
            d["porcentaje_uso_credito_revolving"].astype(str).str.replace("%", "", regex=False)
        )
        d["porcentaje_uso_credito_revolving"] = pd.to_numeric(
            d["porcentaje_uso_credito_revolving"], errors="coerce"
        ).fillna(0)

    if "plazo_prestamo" in d.columns:
        d["plazo_prestamo"] = d["plazo_prestamo"].astype(str).str.extract(r"(\d+)").astype(float)

    if "antiguedad_laboral" in d.columns:
        d["antiguedad_no_informada"] = d["antiguedad_laboral"].isna().astype(int)
        d["antiguedad_laboral"] = (
            d["antiguedad_laboral"].fillna("No informada").astype(str)
            .str.replace("años", "", regex=False)
            .str.replace("aos", "", regex=False)
            .str.strip()
            .str.replace("+", "", regex=False)
            .str.replace("< 1", "0", regex=False)
        )
        d["antiguedad_laboral"] = pd.to_numeric(d["antiguedad_laboral"], errors="coerce")

    if "fecha_emision" in d.columns:
        d["fecha_emision"] = pd.to_datetime(d["fecha_emision"], dayfirst=True, errors="coerce")

    if "fecha_primera_linea_credito" in d.columns:
        d["fecha_primera_linea_credito"] = pd.to_datetime(
            d["fecha_primera_linea_credito"], errors="coerce"
        )

    if "fecha_emision" in d.columns and "fecha_primera_linea_credito" in d.columns:
        d["meses_historial_credito"] = (
            d["fecha_emision"] - d["fecha_primera_linea_credito"]
        ).dt.days / 30
        d.loc[d["meses_historial_credito"] < 0, "meses_historial_credito"] = 0

    if "grado_riesgo" in d.columns:
        g = d["grado_riesgo"].astype(str).str.upper()
        condiciones = [g.isin(["A", "B"]), g.isin(["C", "D"]), g.isin(["E", "F", "G"])]
        elecciones = ["Riesgo_Bajo", "Riesgo_Medio", "Riesgo_Alto"]
        d["grado_riesgo"] = np.select(condiciones, elecciones, default="Desconocido")

    return d


def add_financial_ratios(data):
    d = data.copy()
    d["ratio_endeudamiento"] = d["cuota_mensual"] / ((d["ingresos_anuales"] / 12) + 0.001)
    d["peso_prestamo_ingresos"] = d["importe_solicitado"] / (d["ingresos_anuales"] + 0.001)
    d["ratio_historial_antiguedad"] = d["meses_historial_credito"] / (d["antiguedad_laboral"] + 0.001)
    d["liquidez_residual_mensual"] = (d["ingresos_anuales"] / 12) - d["cuota_mensual"]
    d["ratio_deuda_total_ingresos"] = (
        d["cuota_mensual"] + d["lineas_credito_abiertas"] * 150
    ) / ((d["ingresos_anuales"] / 12) + 0.001)
    return d.replace([np.inf, -np.inf], np.nan)


def build_target(df):
    """Filtra préstamos maduros y crea el target binario sin depender de mojibake."""
    n = df["estado_prestamo"].map(_norm)
    is_paid = n.str.contains("pagado completamente", na=False)
    is_default = (
        n.str.contains("incobrable", na=False)
        | n.str.contains("default", na=False)
        | n.str.contains("retraso de 31 a 120", na=False)
    )
    closed = df[is_paid | is_default].copy()
    closed["target_real"] = is_default[is_paid | is_default].astype(int).values
    return closed


# ---------------------------------------------------------------------------
# Coste / umbral / métricas
# ---------------------------------------------------------------------------
def per_client_cost(y_true, y_pred):
    """Coste € por cliente: FP -> COST_FP, FN -> COST_FN, acierto -> 0."""
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    cost = np.zeros(len(y_true), dtype=float)
    cost[(y_pred == 1) & (y_true == 0)] = COST_FALSE_POSITIVE
    cost[(y_pred == 0) & (y_true == 1)] = COST_FALSE_NEGATIVE
    return cost


def optimize_threshold(y_true, y_prob, min_approval_rate=0.0):
    """Umbral de mínimo coste sujeto a una tasa mínima de aprobación.

    Predicción 1 = 'default previsto' -> se RECHAZA la solicitud, así que la tasa
    de aprobación es la fracción con prob < umbral. Sin restricción, el coste
    asimétrico (FN >> FP) empuja a rechazar a casi todos; este floor evita ese
    punto de operación comercialmente inviable.

    Si ningún umbral de la rejilla cumple la restricción, se devuelve el de
    mayor tasa de aprobación (el más laxo posible) avisando por log.
    """
    rows = []
    for threshold in THRESHOLD_GRID:
        y_pred = (y_prob >= threshold).astype(int)
        cost = per_client_cost(y_true, y_pred).sum()
        approval_rate = float(np.mean(y_pred == 0))
        rows.append({"threshold": float(threshold), "expected_cost": float(cost),
                     "approval_rate": approval_rate})

    feasible = [r for r in rows if r["approval_rate"] >= min_approval_rate]
    if feasible:
        # Mínimo coste; a igualdad de coste, mayor tasa de aprobación.
        best = min(feasible, key=lambda r: (r["expected_cost"], -r["approval_rate"]))
        best["constraint_active"] = bool(min_approval_rate > 0.0)
    else:
        best = max(rows, key=lambda r: r["approval_rate"])
        best["constraint_active"] = True
        log.warning(
            "Ningún umbral alcanza la tasa de aprobación mínima (%.0f%%); "
            "se usa el más laxo (aprobación %.1f%%).",
            min_approval_rate * 100, best["approval_rate"] * 100,
        )
    return best


def threshold_policy_table(y_true, y_prob):
    """Frontera de decisión en TEST: para cada umbral, qué precision/recall/
    tasa de aprobación y coste se obtiene. Permite elegir el punto de operación."""
    y_true = np.asarray(y_true)
    rows = []
    for threshold in THRESHOLD_GRID:
        y_pred = (y_prob >= threshold).astype(int)
        tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
        rows.append({
            "threshold": float(threshold),
            "approval_rate": float(np.mean(y_pred == 0)),
            "precision": float(precision_score(y_true, y_pred, zero_division=0)),
            "recall": float(recall_score(y_true, y_pred, zero_division=0)),
            "fp": int(fp), "fn": int(fn),
            "business_cost": int(fp * COST_FALSE_POSITIVE + fn * COST_FALSE_NEGATIVE),
        })
    return pd.DataFrame(rows)


def score_metrics(y_true, y_prob, threshold):
    y_pred = (y_prob >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    return {
        "roc_auc": float(roc_auc_score(y_true, y_prob)),
        "average_precision": float(average_precision_score(y_true, y_prob)),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "threshold": float(threshold),
        "approval_rate": float(np.mean(y_pred == 0)),
        "rejection_rate": float(np.mean(y_pred == 1)),
        "tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp),
        "business_cost": int(fp * COST_FALSE_POSITIVE + fn * COST_FALSE_NEGATIVE),
    }


def make_preprocessor(x_train):
    # Sin StandardScaler: innecesario para modelos de árbol.
    numeric_cols = x_train.select_dtypes(include=["number"]).columns.tolist()
    categorical_cols = x_train.select_dtypes(include=["object", "category"]).columns.tolist()
    numeric_transformer = SimpleImputer(strategy="median")
    categorical_transformer = Pipeline([
        ("imputer", SimpleImputer(strategy="most_frequent")),
        ("onehot", OneHotEncoder(handle_unknown="ignore", max_categories=20, sparse_output=False)),
    ])
    return ColumnTransformer([
        ("num", numeric_transformer, numeric_cols),
        ("cat", categorical_transformer, categorical_cols),
    ])


# ---------------------------------------------------------------------------
# Candidatos (baseline + challenger real)
# ---------------------------------------------------------------------------
def build_candidates(scale_pos_weight, random_state):
    spw_grid = [1.0, float(np.sqrt(scale_pos_weight)), float(scale_pos_weight)]
    candidates = {
        "XGBoost": {
            "estimator": XGBClassifier(eval_metric="logloss", random_state=random_state, n_jobs=1, tree_method="hist"),
            "params": {
                "classifier__n_estimators": [100, 150, 220],
                "classifier__max_depth": [3, 4],
                "classifier__learning_rate": [0.05, 0.1, 0.15],
                "classifier__subsample": [0.75, 0.9],
                "classifier__colsample_bytree": [0.75, 0.9],
                "classifier__scale_pos_weight": spw_grid,
            },
        },
        "LightGBM": {
            "estimator": LGBMClassifier(random_state=random_state, n_jobs=1, verbosity=-1),
            "params": {
                "classifier__n_estimators": [120, 180, 240],
                "classifier__num_leaves": [15, 31, 45],
                "classifier__learning_rate": [0.03, 0.06, 0.1],
                "classifier__min_child_samples": [60, 120],
                "classifier__subsample": [0.75, 0.9],
                "classifier__colsample_bytree": [0.75, 0.9],
                "classifier__scale_pos_weight": spw_grid,
            },
        },
    }
    if CATBOOST_AVAILABLE:
        candidates["CatBoost_Challenger"] = {
            "estimator": CatBoostClassifier(random_state=random_state, verbose=0, thread_count=1),
            "params": {
                "classifier__iterations": [200, 300, 400],
                "classifier__depth": [4, 6, 8],
                "classifier__learning_rate": [0.03, 0.07, 0.1],
                "classifier__scale_pos_weight": spw_grid,
            },
        }
    else:
        candidates["XGBoost_Challenger"] = {
            "estimator": XGBClassifier(eval_metric="logloss", random_state=random_state, n_jobs=1, tree_method="hist"),
            "params": {
                "classifier__n_estimators": [200, 300, 400],
                "classifier__max_depth": [4, 6, 8],
                "classifier__learning_rate": [0.03, 0.07, 0.1],
                "classifier__scale_pos_weight": spw_grid,
            },
        }
    return candidates


CHALLENGER_FAMILY = "CatBoost_Challenger" if CATBOOST_AVAILABLE else "XGBoost_Challenger"


# ---------------------------------------------------------------------------
# Calibración de probabilidades
# ---------------------------------------------------------------------------
def calibrate(pipeline, x_train, y_train, random_state):
    """Calibración isotónica con CV sobre train (sin fuga hacia valid/test)."""
    cal = CalibratedClassifierCV(clone(pipeline), method="isotonic", cv=3)
    cal.fit(x_train, y_train)
    return cal


# ---------------------------------------------------------------------------
# Simulación de roll-out + significancia (sustituye al falso "A/B test")
# ---------------------------------------------------------------------------
def rollout_simulation(week_df, x_baseline, x_challenger, baseline_model,
                       challenger_model, thr_base, thr_chal, start_date,
                       weeks, weekly_pct, random_state):
    """Roll-out progresivo: cada cliente se asigna al challenger con prob=pct.

    Ambos modelos usan SU umbral óptimo. Se comparan, sobre la misma población
    semanal, el coste realizado del despliegue mixto vs. el coste 'solo baseline'.
    """
    rng = np.random.RandomState(random_state)
    prob_base = baseline_model.predict_proba(x_baseline)[:, 1]
    prob_chal = challenger_model.predict_proba(x_challenger)[:, 1]
    pred_base = (prob_base >= thr_base).astype(int)
    pred_chal = (prob_chal >= thr_chal).astype(int)
    y_true = week_df["target_real"].to_numpy()

    rows = []
    current_pct = 0.0
    for week in range(weeks):
        current_pct = min(1.0, current_pct + weekly_pct)
        wk_start = start_date + timedelta(weeks=week)
        wk_end = wk_start + timedelta(weeks=1)
        mask = (week_df["fecha_emision"] >= wk_start) & (week_df["fecha_emision"] < wk_end)
        idx = np.where(mask.to_numpy())[0]
        if idx.size == 0:
            continue
        to_challenger = rng.random_sample(idx.size) < current_pct
        pred_mix = np.where(to_challenger, pred_chal[idx], pred_base[idx])
        cost_mix = per_client_cost(y_true[idx], pred_mix).sum()
        cost_base_only = per_client_cost(y_true[idx], pred_base[idx]).sum()
        rows.append({
            "week": week + 1,
            "challenger_pct": current_pct,
            "n": int(idx.size),
            "business_cost": int(cost_mix),
            "baseline_only_cost": int(cost_base_only),
        })
    return pd.DataFrame(rows)


def bootstrap_cost_savings(y_true, pred_base, pred_chal, n_boot, random_state):
    """Ahorro por cliente (baseline - challenger) con IC 95% por bootstrap."""
    rng = np.random.RandomState(random_state)
    diff = per_client_cost(y_true, pred_base) - per_client_cost(y_true, pred_chal)
    n = len(diff)
    boot = np.array([diff[rng.randint(0, n, n)].sum() for _ in range(n_boot)])
    return {
        "total_savings": float(diff.sum()),
        "ci95_low": float(np.percentile(boot, 2.5)),
        "ci95_high": float(np.percentile(boot, 97.5)),
        "significant": bool(np.percentile(boot, 2.5) > 0 or np.percentile(boot, 97.5) < 0),
    }


# ---------------------------------------------------------------------------
# SHAP & Fairness
# ---------------------------------------------------------------------------
def compute_shap(pipeline, x_sample, output_dir):
    import matplotlib.pyplot as plt

    pre = pipeline.named_steps["preprocessor"]
    clf = pipeline.named_steps["classifier"]
    x_t = pre.transform(x_sample)
    if hasattr(x_t, "toarray"):
        x_t = x_t.toarray()
    feature_names = pre.get_feature_names_out()
    explainer = shap.TreeExplainer(clf)
    shap_vals = explainer.shap_values(x_t)
    shap.summary_plot(shap_vals, x_t, feature_names=feature_names, show=False)
    path = output_dir / "shap_summary.png"
    plt.savefig(path, bbox_inches="tight")
    plt.close()
    return path


def fairness_report(y_true, y_pred, x, sensitive_features, output_dir):
    rows = []
    for feat in sensitive_features:
        if feat not in x.columns:
            continue
        rows.append({
            "sensitive_feature": feat,
            "demographic_parity_diff": float(
                demographic_parity_difference(y_true, y_pred, sensitive_features=x[feat])
            ),
            "equalized_odds_diff": float(
                equalized_odds_difference(y_true, y_pred, sensitive_features=x[feat])
            ),
        })
    df = pd.DataFrame(rows)
    path = output_dir / "fairness_report.csv"
    df.to_csv(path, index=False)
    return df, path


# ---------------------------------------------------------------------------
# pyfunc con umbral embebido (para serving en MS)
# ---------------------------------------------------------------------------
class ThresholdClassifier(mlflow.pyfunc.PythonModel):
    """Envuelve el modelo calibrado y aplica el umbral óptimo de coste."""

    def load_context(self, context):
        self._model = joblib.load(context.artifacts["model"])
        self._threshold = json.loads(Path(context.artifacts["threshold"]).read_text())["threshold"]

    def predict(self, context, model_input):
        prob = self._model.predict_proba(model_input)[:, 1]
        decision = (prob >= self._threshold).astype(int)
        return pd.DataFrame({"probability": prob, "decision": decision})


# ---------------------------------------------------------------------------
# Entrenamiento
# ---------------------------------------------------------------------------
def train_all(train_df, valid_df, cfg, artifact_dir):
    """Entrena cada candidato en cada feature-set. Selección por coste en VALID."""
    base_drop = [c for c in LEAKAGE_COLS if c in train_df.columns]
    experiments = {
        "without_grade_risk": base_drop + (["grado_riesgo"] if "grado_riesgo" in train_df.columns else []),
        "with_grade_risk_review": base_drop,
    }
    scale_pos = len(train_df[train_df.target_real == 0]) / max(1, len(train_df[train_df.target_real == 1]))
    candidates = build_candidates(scale_pos, cfg["random_state"])
    pr_auc_scorer = make_scorer(average_precision_score, response_method="predict_proba")

    results = []
    for fs_name, drop_cols in experiments.items():
        x_train = train_df.drop(columns=drop_cols + ["target_real"])
        y_train = train_df["target_real"]
        x_valid = valid_df.drop(columns=drop_cols + ["target_real"])
        y_valid = valid_df["target_real"]
        preprocessor = make_preprocessor(x_train)

        for model_name, c in candidates.items():
            run_name = f"{model_name}_{fs_name}_v7"
            log.info("Entrenando %s", run_name)
            pipe = Pipeline([("preprocessor", clone(preprocessor)), ("classifier", c["estimator"])])
            search = RandomizedSearchCV(
                pipe, param_distributions=c["params"], n_iter=cfg["n_iter"],
                cv=TimeSeriesSplit(n_splits=3), scoring=pr_auc_scorer, n_jobs=1,
                random_state=cfg["random_state"], verbose=0,
            )
            with mlflow.start_run(run_name=run_name):
                search.fit(x_train, y_train)
                model = search.best_estimator_

                # Umbral óptimo sobre VALIDACIÓN (con restricción de aprobación);
                # coste de selección = VALID.
                valid_prob = model.predict_proba(x_valid)[:, 1]
                thr = optimize_threshold(y_valid, valid_prob, cfg["min_approval_rate"])["threshold"]
                valid_metrics = score_metrics(y_valid, valid_prob, thr)

                mlflow.log_params(search.best_params_)
                mlflow.log_param("model_family", model_name)
                mlflow.log_param("feature_set", fs_name)
                mlflow.log_metrics({f"valid_{k}": v for k, v in valid_metrics.items()})
                mlflow.log_metric("cv_best_pr_auc", float(search.best_score_))

                results.append({
                    "run_name": run_name, "model_family": model_name,
                    "feature_set": fs_name, "drop_cols": drop_cols,
                    "threshold": thr, "valid": valid_metrics,
                    "best_params": search.best_params_, "model": model,
                })
    return results, experiments


# ---------------------------------------------------------------------------
# Preparación de un modelo desplegable (calibración + umbral + test)
# ---------------------------------------------------------------------------
def prepare_model(entry, train_df, valid_df, test_df, experiments, cfg):
    """Calibra el modelo, fija el umbral óptimo en VALID y evalúa en TEST."""
    drop = experiments[entry["feature_set"]]
    x_train = train_df.drop(columns=drop + ["target_real"])
    y_train = train_df["target_real"]
    x_valid = valid_df.drop(columns=drop + ["target_real"])
    y_valid = valid_df["target_real"]
    x_test = test_df.drop(columns=drop + ["target_real"])
    y_test = test_df["target_real"]

    model = calibrate(entry["model"], x_train, y_train, cfg["random_state"]) if cfg["calibrate"] else entry["model"]
    prob_valid = model.predict_proba(x_valid)[:, 1]
    prob_test = model.predict_proba(x_test)[:, 1]

    if cfg["threshold_mode"] == "approval_target":
        # Umbral = cuantil que aprueba la fracción objetivo en la ventana más
        # reciente (TEST/2019). En producción se recalcula por lote/ventana para
        # mantener estable la tasa de aprobación a pesar del drift temporal.
        thr = float(np.quantile(prob_test, cfg["min_approval_rate"]))
    else:
        thr = optimize_threshold(y_valid, prob_valid, cfg["min_approval_rate"])["threshold"]

    return {
        "entry": entry,
        "model": model,              # calibrado (probabilidades fiables)
        "raw_model": entry["model"],  # sin calibrar (árbol para SHAP)
        "threshold": thr,
        "x_test": x_test,
        "pred_test": (prob_test >= thr).astype(int),
        "test": score_metrics(y_test, prob_test, thr),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(cfg):
    artifact_dir = Path(cfg["artifact_dir"])
    artifact_dir.mkdir(exist_ok=True)
    mlflow.set_tracking_uri(cfg["tracking_uri"])
    mlflow.set_experiment(cfg["experiment_name"])

    log.info("Cargando %.0f%% de %s", cfg["sample_fraction"] * 100, cfg["data_path"])
    df = clean_base(load_data(cfg["data_path"], cfg["sample_fraction"], cfg["random_state"]))
    closed = add_financial_ratios(build_target(df))

    train_df = closed[closed.fecha_emision < "2018-01-01"].copy()
    valid_df = closed[(closed.fecha_emision >= "2018-01-01") & (closed.fecha_emision < "2019-01-01")].copy()
    test_df = closed[closed.fecha_emision >= "2019-01-01"].copy()
    data_quality_score = float(100 * (1 - closed.isna().mean().mean()))

    results, experiments = train_all(train_df, valid_df, cfg, artifact_dir)
    y_test = test_df["target_real"]

    # --- Selección por COSTE EN VALIDACIÓN (no test). Baseline=incumbente
    #     (XGBoost/LightGBM); Challenger=mejor CatBoost; Campeón=el mejor de los dos.
    baseline_entry = min(
        (r for r in results if r["model_family"] != CHALLENGER_FAMILY),
        key=lambda r: r["valid"]["business_cost"],
    )
    challenger_entry = min(
        (r for r in results if r["model_family"] == CHALLENGER_FAMILY),
        key=lambda r: r["valid"]["business_cost"], default=baseline_entry,
    )
    log.info("Baseline: %s | Challenger: %s", baseline_entry["run_name"], challenger_entry["run_name"])

    if cfg["calibrate"]:
        log.info("Calibrando baseline y challenger (isotónica, cv=3)")
    baseline = prepare_model(baseline_entry, train_df, valid_df, test_df, experiments, cfg)
    challenger = prepare_model(challenger_entry, train_df, valid_df, test_df, experiments, cfg)
    # El campeón (modelo a registrar) es el de menor coste en validación.
    champion = min([baseline, challenger], key=lambda m: m["entry"]["valid"]["business_cost"])
    log.info("Campeón registrado: %s", champion["entry"]["run_name"])

    # --- Evaluación (todo dentro de un run explícito) ---
    with mlflow.start_run(run_name="Evaluation_v7"):
        mlflow.log_metrics({f"champion_test_{k}": v for k, v in champion["test"].items()})
        mlflow.log_metric("data_quality_score", data_quality_score)
        mlflow.log_param("min_approval_rate", cfg["min_approval_rate"])
        mlflow.log_param("threshold_mode", cfg["threshold_mode"])

        # Roll-out con umbrales óptimos + significancia: baseline vs challenger
        rollout = rollout_simulation(
            test_df, baseline["x_test"], challenger["x_test"], baseline["model"],
            challenger["model"], baseline["threshold"], challenger["threshold"],
            pd.to_datetime("2019-01-01"), weeks=10, weekly_pct=0.10,
            random_state=cfg["random_state"],
        )
        rollout_path = artifact_dir / "rollout_comparison.csv"
        rollout.to_csv(rollout_path, index=False)
        mlflow.log_artifact(str(rollout_path))

        savings = bootstrap_cost_savings(y_test.to_numpy(), baseline["pred_test"],
                                         challenger["pred_test"], cfg["n_bootstrap"], cfg["random_state"])
        mlflow.log_metrics({f"savings_{k}": float(v) for k, v in savings.items()})

        # SHAP sobre el árbol SIN calibrar del campeón, con su x_test correcto
        shap_dir = artifact_dir / "shap"
        shap_dir.mkdir(exist_ok=True)
        shap_sample = champion["x_test"].sample(n=min(200, len(champion["x_test"])), random_state=cfg["random_state"])
        try:
            compute_shap(champion["raw_model"], shap_sample, shap_dir)
            mlflow.log_artifact(str(shap_dir))
        except Exception as err:  # pragma: no cover
            log.warning("SHAP no disponible para este modelo: %s", err)

        # Fairness con el umbral óptimo (no 0.5) y varias métricas
        fair_dir = artifact_dir / "fairness"
        fair_dir.mkdir(exist_ok=True)
        fair_df, _ = fairness_report(y_test, champion["pred_test"], champion["x_test"], SENSITIVE_FEATURES, fair_dir)
        mlflow.log_artifact(str(fair_dir))

        # Frontera precision/recall/aprobación en TEST (elección de operating point)
        champ_prob_test = champion["model"].predict_proba(champion["x_test"])[:, 1]
        policy = threshold_policy_table(y_test, champ_prob_test)
        policy_path = artifact_dir / "threshold_policy_test.csv"
        policy.to_csv(policy_path, index=False)
        mlflow.log_artifact(str(policy_path))
        # En modo 'cost' el umbral se fija en validación: avisa si el drift hace
        # que en TEST no se alcance la tasa de aprobación objetivo.
        test_approval = champion["test"]["approval_rate"]
        if cfg["threshold_mode"] == "cost" and test_approval < cfg["min_approval_rate"] - 0.01:
            log.warning(
                "Drift: el umbral %.2f aprueba %.1f%% en TEST (objetivo %.0f%%). "
                "Usa --threshold-mode approval_target para fijar la tasa de aprobación.",
                champion["threshold"], test_approval * 100, cfg["min_approval_rate"] * 100,
            )
        log.info("Punto de operación: umbral %.2f, aprobación en test %.1f%%",
                 champion["threshold"], test_approval * 100)

        # Datos para el dashboard
        write_dashboard_data(artifact_dir, champion["test"], baseline["test"],
                             challenger["test"], rollout, savings, fair_df)

    # --- Registro del campeón como pyfunc con umbral embebido ---
    register_champion(champion["model"], champion["threshold"], champion["entry"], champion["test"], cfg, artifact_dir)

    summary = {
        "registered_model_name": cfg["registered_model_name"],
        "sample_fraction": cfg["sample_fraction"],
        "rows": {"sample": int(len(df)), "closed": int(len(closed)),
                 "train": int(len(train_df)), "valid": int(len(valid_df)), "test": int(len(test_df))},
        "cost_assumptions": {"false_positive": COST_FALSE_POSITIVE, "false_negative": COST_FALSE_NEGATIVE},
        "min_approval_rate": cfg["min_approval_rate"],
        "threshold_mode": cfg["threshold_mode"],
        "champion": {"run_name": champion["entry"]["run_name"], "model_family": champion["entry"]["model_family"],
                     "feature_set": champion["entry"]["feature_set"], "threshold": champion["threshold"],
                     "valid": champion["entry"]["valid"], "test": champion["test"]},
        "baseline": {"run_name": baseline["entry"]["run_name"], "test": baseline["test"], "threshold": baseline["threshold"]},
        "challenger": {"run_name": challenger["entry"]["run_name"], "test": challenger["test"], "threshold": challenger["threshold"]},
        "challenger_savings_vs_baseline": savings,
        "all_results": [{k: v for k, v in r.items() if k != "model"} for r in results],
    }
    sum_path = artifact_dir / "model_comparison_summary_v7.json"
    sum_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    log.info("Resumen escrito en %s", sum_path)
    log.info("Coste test campeón: %s € | Ahorro challenger vs baseline: %s (significativo=%s)",
             champion["test"]["business_cost"], int(savings["total_savings"]), savings["significant"])


def write_dashboard_data(artifact_dir, champ_test, base_test, chal_test, rollout, savings, fair_df):
    weeks = rollout["week"].tolist()
    pcts = [round(p * 100) for p in rollout["challenger_pct"].tolist()]
    costs = [round(c / 1e6, 2) for c in rollout["business_cost"].tolist()]
    fairness_diff = "N/A"
    if not fair_df.empty:
        fairness_diff = f'{fair_df["demographic_parity_diff"].iloc[0]:.4f}'

    data = {
        "roc_auc": round(champ_test["roc_auc"], 4),
        "tn": champ_test["tn"], "fp": champ_test["fp"],
        "fn": champ_test["fn"], "tp": champ_test["tp"],
        "costFp": f'€{champ_test["fp"] * COST_FALSE_POSITIVE / 1e6:.2f}M',
        "costFn": f'€{champ_test["fn"] * COST_FALSE_NEGATIVE / 1e6:.2f}M',
        "baseline": {k: round(base_test[k], 4) for k in ["roc_auc", "accuracy", "precision", "recall", "f1"]},
        "challenger": {k: round(chal_test[k], 4) for k in ["roc_auc", "accuracy", "precision", "recall", "f1"]},
        "ab_test_labels": [f"Week {w} ({p}%)" for w, p in zip(weeks, pcts)],
        "ab_test_costs": costs,
        "fairness_diff": fairness_diff,
        "cost_savings_eur": round(savings["total_savings"]),
        "cost_savings_significant": savings["significant"],
        "approval_rate": round(champ_test["approval_rate"], 4),
        "rejection_rate": round(champ_test["rejection_rate"], 4),
    }
    js = "const dashboardData = " + json.dumps(data, ensure_ascii=False, indent=2) + ";\n"
    (artifact_dir / "dashboard_data.js").write_text(js, encoding="utf-8")


def register_champion(model, threshold, champion, champ_test, cfg, artifact_dir):
    log.info("Registrando campeón con umbral embebido (%.2f)", threshold)
    model_path = artifact_dir / "champion_model.pkl"
    thr_path = artifact_dir / "champion_threshold.json"
    joblib.dump(model, model_path)
    thr_path.write_text(json.dumps({"threshold": threshold}), encoding="utf-8")

    mlflow.end_run()
    with mlflow.start_run(run_name="Register_Champion_v7"):
        mlflow.log_metrics({f"champion_test_{k}": v for k, v in champ_test.items()})
        mlflow.log_param("champion_run_name", champion["run_name"])
        mlflow.log_param("champion_model_family", champion["model_family"])
        mlflow.log_param("decision_threshold", threshold)
        mlflow.pyfunc.log_model(
            artifact_path="champion_pyfunc",
            python_model=ThresholdClassifier(),
            artifacts={"model": str(model_path), "threshold": str(thr_path)},
            registered_model_name=cfg["registered_model_name"],
        )


def parse_args():
    p = argparse.ArgumentParser(description="Credit Risk Pipeline V7")
    p.add_argument("--data-path", default=DEFAULTS["data_path"])
    p.add_argument("--sample-fraction", type=float, default=DEFAULTS["sample_fraction"])
    p.add_argument("--random-state", type=int, default=DEFAULTS["random_state"])
    p.add_argument("--n-iter", type=int, default=DEFAULTS["n_iter"])
    p.add_argument("--no-calibrate", action="store_true")
    p.add_argument("--min-approval-rate", type=float, default=DEFAULTS["min_approval_rate"],
                   help="Tasa mínima de solicitantes aprobados (0.0-1.0). 0=sin restricción.")
    p.add_argument("--threshold-mode", choices=["approval_target", "cost"],
                   default=DEFAULTS["threshold_mode"],
                   help="approval_target=fija la tasa de aprobación; cost=mínimo coste.")
    p.add_argument("--tracking-uri", default=DEFAULTS["tracking_uri"])
    p.add_argument("--artifact-dir", default=DEFAULTS["artifact_dir"])
    a = p.parse_args()
    cfg = dict(DEFAULTS)
    cfg.update(
        data_path=a.data_path, sample_fraction=a.sample_fraction,
        random_state=a.random_state, n_iter=a.n_iter,
        calibrate=not a.no_calibrate, min_approval_rate=a.min_approval_rate,
        threshold_mode=a.threshold_mode, tracking_uri=a.tracking_uri,
        artifact_dir=a.artifact_dir,
    )
    return cfg


if __name__ == "__main__":
    main(parse_args())
