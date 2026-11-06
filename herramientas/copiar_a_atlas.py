"""
Copia tus asistencias de MongoDB local a MongoDB Atlas (la nube). Se usa UNA vez.

Uso (PowerShell, dentro de control_asistencias_ia):
    .venv\\Scripts\\python herramientas\\copiar_a_atlas.py "mongodb+srv://usuario:clave@cluster.xxxx.mongodb.net"

No borra nada en tu PC: solo lee de local y escribe en Atlas.
"""
import sys

from pymongo import MongoClient

BD, COLECCION = "control_asistencia_mongo", "asistencias"


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)

    origen = MongoClient("mongodb://localhost:27017")[BD][COLECCION]
    destino = MongoClient(sys.argv[1], serverSelectionTimeoutMS=15000)[BD][COLECCION]

    if destino.estimated_document_count() > 0:
        print(f"Atlas ya tiene {destino.estimated_document_count()} documentos en {BD}.{COLECCION}. "
              "No se copia nada para no duplicar.")
        return

    docs = list(origen.find({}))
    if not docs:
        print("La colección local está vacía.")
        return
    destino.insert_many(docs)
    print(f"Listo: {len(docs)} asistencias copiadas a Atlas ({BD}.{COLECCION}).")


if __name__ == "__main__":
    main()
