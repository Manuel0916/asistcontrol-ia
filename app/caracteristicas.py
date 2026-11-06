"""
PASO 2 — CONSTRUIR LAS CARACTERÍSTICAS (lo que el modelo "mira" para decidir)

Para cada asistencia se calcula el historial del alumno ANTES de esa clase.
Así el modelo aprende como si estuviera prediciendo el futuro, sin hacer trampa
(si usáramos datos posteriores, sería "fuga de información").

  tasa_alumno         % de faltas del alumno en todas sus clases anteriores
  tasa_alumno_clase   % de faltas del alumno en ESA materia
  faltas_ultimas5     cuántas de sus últimas 5 clases de esa materia faltó
  dia_semana, mes      cuándo es la clase
  clase               qué materia (se convierte a columnas 0/1)

NOTA: la hora NO se usa. En los datos históricos de Mongo el campo "hora_num" delata el
resultado (todas las ausencias tienen hora > 8.7); usarlo daría 100 % de acierto falso.
"""
from collections import defaultdict, deque

import pandas as pd

# Suavizado: un alumno nuevo empieza con la tasa promedio y se va ajustando con sus datos.
SUAVIZADO = 5.0

COLUMNAS_NUMERICAS = ["tasa_alumno", "tasa_alumno_clase", "faltas_ultimas5", "dia_semana", "mes"]

# Nombres legibles para mostrar en la app
NOMBRES = {
    "tasa_alumno": "Faltas históricas del alumno",
    "tasa_alumno_clase": "Faltas en la materia",
    "faltas_ultimas5": "Faltas en las últimas 5 clases",
    "dia_semana": "Día de la semana",
    "mes": "Mes",
    "clase": "Materia",
}


class Historial:
    """Lleva la cuenta de faltas de cada alumno mientras se recorren las clases en orden."""

    def __init__(self, tasa_global: float):
        self.tasa_global = tasa_global
        self.total = defaultdict(lambda: [0, 0])          # alumno -> [faltas, clases]
        self.por_clase = defaultdict(lambda: [0, 0])      # (alumno, clase) -> [faltas, clases]
        self.ultimas = defaultdict(lambda: deque(maxlen=5))  # (alumno, clase) -> últimas 5 (1=faltó)

    def _tasa(self, faltas, clases):
        return (faltas + SUAVIZADO * self.tasa_global) / (clases + SUAVIZADO)

    def caracteristicas(self, alumno: str, clase: str) -> dict:
        f, n = self.total[alumno]
        fc, nc = self.por_clase[(alumno, clase)]
        return {
            "tasa_alumno": self._tasa(f, n),
            "tasa_alumno_clase": self._tasa(fc, nc),
            "faltas_ultimas5": sum(self.ultimas[(alumno, clase)]),
            "clases_registradas": nc,
        }

    def registrar(self, alumno: str, clase: str, ausente: int):
        self.total[alumno][0] += ausente
        self.total[alumno][1] += 1
        self.por_clase[(alumno, clase)][0] += ausente
        self.por_clase[(alumno, clase)][1] += 1
        self.ultimas[(alumno, clase)].append(ausente)


def construir_dataset(df: pd.DataFrame):
    """Devuelve (tabla de características, objetivo 'ausente', historial completo al final)."""
    historial = Historial(tasa_global=float(df["ausente"].mean()))
    filas = []
    for fila in df.itertuples(index=False):
        c = historial.caracteristicas(fila.alumno, fila.clase)   # historial ANTES de esta clase
        c.update(dia_semana=fila.dia_semana, mes=fila.mes, clase=fila.clase)
        filas.append(c)
        historial.registrar(fila.alumno, fila.clase, fila.ausente)  # ahora sí se suma
    X = pd.DataFrame(filas)
    return X, df["ausente"].to_numpy(), historial


def a_matriz(X: pd.DataFrame, clases: list[str]) -> pd.DataFrame:
    """Convierte la materia en columnas 0/1 (one-hot) con un orden fijo de columnas."""
    M = X[COLUMNAS_NUMERICAS].astype(float).copy()
    for c in clases:
        M[f"clase={c}"] = (X["clase"] == c).astype(float)
    return M
