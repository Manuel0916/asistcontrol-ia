"""
PASO 3 — ENTRENAR Y USAR EL MODELO (Random Forest)

Random Forest = muchos árboles de decisión. Cada árbol aprende reglas como
"si faltó 3 de sus últimas 5 clases y es lunes → probablemente falta".
Para predecir, todos los árboles votan y el % de votos es la probabilidad de faltar.

Cómo sabemos si sirve:
  - Se separa el 20 % de los datos (prueba) y se entrena con el 80 % restante.
  - Se mide qué tan bien acierta en ese 20 % que el modelo NUNCA vio.
  - Luego se vuelve a entrenar con el 100 % para usarlo en la app.
"""
import threading
from datetime import datetime

import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score, precision_score,
                             recall_score, roc_auc_score)
from sklearn.model_selection import train_test_split

from . import config
from .caracteristicas import NOMBRES, a_matriz, construir_dataset
from .datos import DIAS, MESES, cargar_asistencias

MIN_REGISTROS = 100


def _nuevo_bosque():
    return RandomForestClassifier(
        n_estimators=300,      # 300 árboles
        max_depth=8,           # árboles no muy profundos para no memorizar
        min_samples_leaf=10,   # cada hoja con al menos 10 casos: probabilidades más estables
        random_state=42,       # mismo resultado cada vez que se entrena
        n_jobs=-1,
    )


class ModeloAsistencia:
    """Guarda el modelo entrenado, sus métricas y el historial actual de cada alumno."""

    def __init__(self):
        self._lock = threading.Lock()
        self.bosque = None
        self.clases: list[str] = []
        self.historial = None
        self.pares: list[tuple[str, str]] = []
        self.metricas: dict = {}

    @property
    def listo(self) -> bool:
        return self.bosque is not None

    # ------------------------------------------------------------------ entrenamiento
    def entrenar(self) -> dict:
        df = cargar_asistencias()
        if len(df) < MIN_REGISTROS:
            raise ValueError(f"Se necesitan al menos {MIN_REGISTROS} asistencias (hay {len(df)}).")

        X, y, historial = construir_dataset(df)
        clases = sorted(df["clase"].unique())
        M = a_matriz(X, clases)

        # 1) Evaluación honesta: entrenar con 80 %, medir con el 20 % que no vio
        M_ent, M_prueba, y_ent, y_prueba = train_test_split(
            M, y, test_size=0.2, stratify=y, random_state=42)
        evaluador = _nuevo_bosque().fit(M_ent, y_ent)
        prob = evaluador.predict_proba(M_prueba)[:, 1]
        pred = (prob >= config.PROB_ALTA).astype(int)
        tn, fp, fn, tp = confusion_matrix(y_prueba, pred, labels=[0, 1]).ravel()
        auc = roc_auc_score(y_prueba, prob)

        # 2) Modelo final con todos los datos
        bosque = _nuevo_bosque().fit(M, y)

        metricas = {
            "algoritmo": "Random Forest (scikit-learn)",
            "arboles": 300,
            "registros": int(len(df)),
            "registros_entrenamiento": int(len(y_ent)),
            "registros_prueba": int(len(y_prueba)),
            "alumnos": int(df["alumno"].nunique()),
            "clases": clases,
            "tasa_base_ausencia": round(float(y.mean()), 3),
            "umbral_falta": config.PROB_ALTA,
            "accuracy": round(float(accuracy_score(y_prueba, pred)), 3),
            "auc": round(float(auc), 3),
            "precision": round(float(precision_score(y_prueba, pred, zero_division=0)), 3),
            "recall": round(float(recall_score(y_prueba, pred, zero_division=0)), 3),
            "f1": round(float(f1_score(y_prueba, pred, zero_division=0)), 3),
            "matriz_confusion": {
                "asistio_predijo_asiste": int(tn), "asistio_predijo_falta": int(fp),
                "falto_predijo_asiste": int(fn), "falto_predijo_falta": int(tp),
            },
            "importancia": _importancia(bosque, list(M.columns)),
            "entrenado_en": datetime.now().isoformat(timespec="seconds"),
            "advertencia": (
                f"Señal moderada (AUC {auc:.2f}): la asistencia tiene mucho de azar. "
                "Usa las probabilidades como orientación para priorizar, no como certeza."
                if auc < 0.65 else None),
        }

        # Combinaciones alumno–materia que existen (para el panel de riesgo)
        pares = sorted(df.groupby(["alumno", "clase"]).size().index.tolist())

        with self._lock:
            self.bosque, self.clases, self.historial = bosque, clases, historial
            self.pares, self.metricas = pares, metricas
        return metricas

    # ------------------------------------------------------------------ predicción
    def predecir(self, alumno: str, clase: str, dia_semana: int, mes: int) -> dict:
        return self.predecir_lote([(alumno, clase)], dia_semana, mes)[0]

    def predecir_lote(self, pares: list[tuple[str, str]], dia_semana: int, mes: int) -> list[dict]:
        """Predice varias combinaciones alumno–materia en UNA sola pasada por el bosque
        (mucho más rápido que una por una en el servidor gratis de la nube)."""
        if not self.listo:
            raise RuntimeError("El modelo aún no está entrenado.")
        if not pares:
            return []
        with self._lock:
            filas, historiales = [], []
            for alumno, clase in pares:
                clase = self._clase_canonica(clase)
                hist = self.historial.caracteristicas(alumno, clase)
                historiales.append((alumno, clase, hist))
                filas.append({**hist, "dia_semana": dia_semana, "mes": mes, "clase": clase})
            M = a_matriz(pd.DataFrame(filas), self.clases)
            probs = self.bosque.predict_proba(M)[:, 1]

        return [{
            "alumno": alumno,
            "clase": clase,
            "dia_semana": DIAS[dia_semana],
            "mes": MESES[mes - 1],
            "probabilidad_falta": round(float(prob), 3),
            "nivel": nivel(prob),
            "prediccion": "Falta" if prob >= config.PROB_ALTA else "Asiste",
            "factores": {
                "tasa_historica": round(hist["tasa_alumno"], 3),
                "tasa_en_materia": round(hist["tasa_alumno_clase"], 3),
                "faltas_ultimas5": int(hist["faltas_ultimas5"]),
                "clases_registradas": int(hist["clases_registradas"]),
            },
        } for (alumno, clase, hist), prob in zip(historiales, probs)]

    def pares_alumno_clase(self, clase: str | None = None) -> list[tuple[str, str]]:
        """Todas las combinaciones alumno–materia con historial (para el panel de riesgo)."""
        pares = list(self.pares)
        if clase:
            c = clase.strip().lower()
            pares = [p for p in pares if p[1].lower() == c]
        return pares

    def opciones(self) -> dict:
        alumnos = sorted({a for a, _ in self.pares})
        return {"alumnos": alumnos, "clases": self.clases, "dias": DIAS[:7], "meses": MESES}

    def _clase_canonica(self, clase: str) -> str:
        for c in self.clases:
            if c.lower() == clase.strip().lower():
                return c
        return clase.strip()


def nivel(prob: float) -> str:
    if prob >= config.PROB_ALTA:
        return "ALTA"
    if prob >= config.PROB_MEDIA:
        return "MEDIA"
    return "BAJA"


def _importancia(bosque, columnas: list[str]) -> list[dict]:
    """Qué tanto usa el modelo cada variable (las columnas de materia se suman en una)."""
    total: dict[str, float] = {}
    for col, imp in zip(columnas, bosque.feature_importances_):
        clave = "clase" if col.startswith("clase=") else col
        total[clave] = total.get(clave, 0.0) + float(imp)
    orden = sorted(total.items(), key=lambda kv: kv[1], reverse=True)
    return [{"variable": k, "nombre": NOMBRES.get(k, k), "importancia": round(v, 3)} for k, v in orden]


# Instancia única que usa la API
modelo = ModeloAsistencia()

