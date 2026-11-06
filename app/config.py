"""Configuración del servicio de IA (se cambia con variables de entorno en la nube)."""
import os

# MongoDB: donde están todas las asistencias (historial + las nuevas que guarda Spring Boot)
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "control_asistencia_mongo")
MONGO_COLECCION = os.getenv("MONGO_COLECCION", "asistencias")

# Clave compartida con Spring Boot: solo el backend puede usar este servicio
API_KEY = os.getenv("IA_API_KEY", "clave-ia-desarrollo")

# Zona horaria de las clases (las fechas en Mongo se guardan en UTC)
ZONA_HORARIA = os.getenv("ZONA_HORARIA", "America/Bogota")


# Niveles de riesgo según la probabilidad de faltar (los mismos que usa la web).
# Como en promedio falta 1 de cada 4 clases (25 %), una probabilidad del 35 % ya es alta.
# El modelo "predice falta" cuando la probabilidad llega a PROB_ALTA.
PROB_ALTA = float(os.getenv("PROB_ALTA", "0.35"))
PROB_MEDIA = float(os.getenv("PROB_MEDIA", "0.28"))
