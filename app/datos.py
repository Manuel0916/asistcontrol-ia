"""
PASO 1 — LEER LOS DATOS DE MONGODB

Trae todas las asistencias de la colección y las deja en una tabla (DataFrame de pandas)
limpia, con una fila por asistencia:

    alumno | clase | fecha | dia_semana (0=lunes) | mes (1-12) | ausente (1/0)
"""
import pandas as pd
from pymongo import MongoClient

from . import config

DIAS = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]


def _coleccion():
    cliente = MongoClient(config.MONGO_URI, serverSelectionTimeoutMS=10000)
    return cliente[config.MONGO_DB][config.MONGO_COLECCION]


def cargar_asistencias() -> pd.DataFrame:
    filas = list(_coleccion().find(
        {}, {"_id": 0, "nombre": 1, "clase": 1, "fechahora": 1, "fechaHora": 1, "estado": 1}))
    if not filas:
        raise ValueError("La colección de MongoDB está vacía: no hay datos para entrenar.")

    df = pd.DataFrame(filas)
    # Algunos registros guardan la fecha como "fechaHora" (con H mayúscula)
    if "fechaHora" in df:
        df["fechahora"] = df.get("fechahora").fillna(df["fechaHora"]) if "fechahora" in df else df["fechaHora"]
    df = df.dropna(subset=["nombre", "clase", "fechahora", "estado"])

    # Fecha en hora de Colombia. El día y el mes se calculan DE LA FECHA REAL
    # (el campo "mes" guardado en Mongo no siempre coincide con la fecha).
    fechas = pd.to_datetime(df["fechahora"], utc=True).dt.tz_convert(config.ZONA_HORARIA)
    df["fecha"] = fechas.dt.tz_localize(None)
    df["dia_semana"] = fechas.dt.dayofweek
    df["mes"] = fechas.dt.month

    df["alumno"] = df["nombre"].astype(str).str.strip()
    df["clase"] = normalizar_clases(df["clase"])
    df["ausente"] = (df["estado"].astype(str).str.strip().str.lower() == "ausente").astype(int)

    return df[["alumno", "clase", "fecha", "dia_semana", "mes", "ausente"]] \
        .sort_values("fecha", kind="stable").reset_index(drop=True)


def normalizar_clases(clases: pd.Series) -> pd.Series:
    """'matematicas-A' y 'Matematicas-A' son la misma materia: se usa la escritura más común."""
    limpias = clases.astype(str).str.strip()
    clave = limpias.str.lower()
    mas_comun = limpias.groupby(clave).agg(lambda s: s.value_counts().index[0])
    return clave.map(mas_comun)
