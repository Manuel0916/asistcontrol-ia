# AsistControl · Servicio de IA (Python)

Predice la **probabilidad de que un alumno falte** a una clase con un modelo **Random Forest**
(scikit-learn), entrenado con el historial de asistencias guardado en **MongoDB**.

```
App Flutter ──► Spring Boot ──(X-API-Key)──► este servicio (FastAPI) ──► MongoDB
```

## Archivos (en el orden en que funcionan)
| Archivo | Qué hace |
|---|---|
| `app/config.py` | Configuración (Mongo, clave, umbrales) por variables de entorno |
| `app/datos.py` | **Paso 1**: lee las asistencias de MongoDB y las limpia |
| `app/caracteristicas.py` | **Paso 2**: calcula lo que mira el modelo (historial de faltas, día, mes, materia) |
| `app/modelo.py` | **Paso 3**: entrena el Random Forest, lo evalúa y predice |
| `app/main.py` | **Paso 4**: la API (rutas que llama Spring Boot) |

## Cómo decide el modelo
Variables (de cada clase se mira solo el historial **anterior**, para no hacer trampa):
- % de faltas del alumno, % de faltas en esa materia, faltas en sus últimas 5 clases.
- Día de la semana, mes y materia.

> **La hora no se usa.** En el historial de Mongo, el campo `hora_num` delata el resultado
> (todas las ausencias tienen hora > 8.7). Con él el modelo daba 100 % de acierto falso.

**Resultados** (5271 asistencias, 20 % reservado para prueba): exactitud 71 %, **AUC 0.60**.
También se probaron una regresión logística (AUC 0.61) y una red neuronal MLP (AUC 0.59):
los tres empatan, lo que indica que el límite está en los datos (mucho azar), no en el modelo.
Se eligió Random Forest porque además explica qué variables pesan más.

## Ejecutar en tu PC
```powershell
cd "F:\proyecto aula\control_asistencias_ia"
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m uvicorn app.main:app --port 8000
```
Documentación interactiva: http://localhost:8000/docs (las rutas piden la cabecera
`X-API-Key: clave-ia-desarrollo`).

## Rutas
| Método | Ruta | Uso |
|---|---|---|
| GET | `/salud` | ¿Está vivo y entrenado? |
| GET | `/modelo` | Métricas, matriz de confusión, importancia de variables |
| POST | `/modelo/entrenar` | Reentrenar con los datos actuales de Mongo |
| GET | `/opciones` | Alumnos y materias |
| POST | `/predecir` | `{alumno, clase, fecha}` → probabilidad, nivel y factores |
| GET | `/prediccion?fecha=&clase=` | Probabilidad de todos los alumnos (panel de riesgo) |

## Variables de entorno (nube)
`MONGO_URI`, `MONGO_DB` (asistcontrol), `IA_API_KEY` (la misma que en Spring Boot).

## Migración (una sola vez)
`herramientas/migrar_a_mongo.py` pasa MySQL + el historial a la base `asistcontrol`
(sin repetir asistencias). Requiere `pip install pymysql`.
