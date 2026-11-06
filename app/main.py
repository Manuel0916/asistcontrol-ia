"""
PASO 4 — LA API (FastAPI)

Spring Boot llama a estas rutas. Documentación interactiva en http://localhost:8000/docs

  GET  /salud              ¿está vivo el servicio y el modelo entrenado?
  GET  /modelo             métricas, matriz de confusión e importancia de variables
  POST /modelo/entrenar    vuelve a entrenar leyendo MongoDB (botón "Reentrenar")
  GET  /opciones           alumnos y materias para los selectores
  POST /predecir           probabilidad de que UN alumno falte a una clase
  GET  /prediccion         probabilidad para TODOS los alumnos en una fecha (panel de riesgo)
"""
from contextlib import asynccontextmanager
from datetime import date

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from . import config
from .datos import DIAS, MESES
from .modelo import modelo


@asynccontextmanager
async def al_iniciar(app: FastAPI):
    # Al arrancar se entrena con los datos de MongoDB (tarda unos segundos)
    try:
        m = modelo.entrenar()
        print(f"Modelo entrenado con {m['registros']} asistencias · AUC {m['auc']}")
    except Exception as e:  # el servicio arranca igual y se puede reentrenar después
        print(f"No se pudo entrenar al iniciar: {e}")
    yield


app = FastAPI(
    title="AsistControl · Servicio de IA",
    description="Predice la probabilidad de que un alumno falte a clase (Random Forest).",
    version="1.0",
    lifespan=al_iniciar,
)


def verificar_clave(x_api_key: str | None = Header(default=None)):
    """Solo Spring Boot conoce esta clave (cabecera X-API-Key)."""
    if x_api_key != config.API_KEY:
        raise HTTPException(status_code=401, detail="Clave de API inválida")


def requiere_modelo():
    if not modelo.listo:
        raise HTTPException(status_code=503, detail="El modelo aún no está entrenado. Usa POST /modelo/entrenar.")


class SolicitudPrediccion(BaseModel):
    alumno: str
    clase: str
    # Se puede enviar la fecha (la app) o día y mes por separado (formulario web)
    fecha: date | None = None
    dia_semana: str | None = Field(default=None, description="lunes, martes, ...")
    mes: str | None = Field(default=None, description="enero, febrero, ...")


@app.get("/salud")
def salud():
    return {"estado": "ok", "modelo_entrenado": modelo.listo}


@app.get("/modelo", dependencies=[Depends(verificar_clave), Depends(requiere_modelo)])
def ver_modelo():
    return modelo.metricas


@app.post("/modelo/entrenar", dependencies=[Depends(verificar_clave)])
def entrenar():
    try:
        return modelo.entrenar()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.get("/opciones", dependencies=[Depends(verificar_clave), Depends(requiere_modelo)])
def opciones():
    return modelo.opciones()


@app.post("/predecir", dependencies=[Depends(verificar_clave), Depends(requiere_modelo)])
def predecir(s: SolicitudPrediccion):
    if s.fecha is not None:
        dia, mes = s.fecha.weekday(), s.fecha.month
    elif s.dia_semana and s.mes:
        try:
            dia = DIAS.index(_sin_tildes(s.dia_semana))
            mes = MESES.index(s.mes.strip().lower()) + 1
        except ValueError:
            raise HTTPException(status_code=400, detail="Día o mes no válido")
    else:
        raise HTTPException(status_code=400, detail="Envía la fecha, o el día de la semana y el mes")
    return modelo.predecir(s.alumno.strip(), s.clase, dia, mes)


@app.get("/prediccion", dependencies=[Depends(verificar_clave), Depends(requiere_modelo)])
def prediccion_todos(fecha: date | None = None, clase: str | None = None):
    f = fecha or date.today()
    resultado = modelo.predecir_lote(modelo.pares_alumno_clase(clase), f.weekday(), f.month)
    resultado.sort(key=lambda r: r["probabilidad_falta"], reverse=True)
    return resultado


def _sin_tildes(texto: str) -> str:
    return texto.strip().lower().replace("é", "e").replace("á", "a")
