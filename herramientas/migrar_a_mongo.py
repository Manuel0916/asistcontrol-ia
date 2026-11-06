"""
MIGRACIÓN: MySQL + historial de Mongo  →  una sola base MongoDB "asistcontrol"

Lee (sin modificar nada):
  - MySQL local `control_asistencia`: usuarios, roles, usuario_roles, login_config, asistencias
  - Mongo local `control_asistencia_mongo.asistencias`: el historial (5016 registros)

Escribe en la base `asistcontrol` del destino (tu PC o MongoDB Atlas):
  usuarios, roles, login_config, asistencias, contadores

Las asistencias de MySQL que ya estaban en el historial (mismo alumno, clase y minuto)
NO se repiten. Los ids son números (1, 2, 3...) como en MySQL, para que la app y la web
sigan funcionando igual.

Uso (PowerShell, dentro de control_asistencias_ia):
  # en tu PC
  .venv\\Scripts\\python herramientas\\migrar_a_mongo.py
  # en la nube (Atlas)
  .venv\\Scripts\\python herramientas\\migrar_a_mongo.py "mongodb+srv://usuario:clave@cluster0.xxxx.mongodb.net/"

Requiere: pip install pymysql  (solo para esta herramienta)
"""
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import pymysql
from pymongo import MongoClient

ZONA = ZoneInfo("America/Bogota")
UTC = ZoneInfo("UTC")
BD_DESTINO = "asistcontrol"
MYSQL = dict(host="localhost", user="root", password=os.getenv("MYSQL_PASSWORD", "1234"),
             database="control_asistencia", charset="utf8mb4")
MONGO_LOCAL = "mongodb://localhost:27017"


def estado_normal(e):
    e = (e or "").strip().lower()
    return {"presente": "Presente", "tarde": "Tarde", "ausente": "Ausente"}.get(e, (e or "").capitalize())


def clave(nombre, clase, fecha_utc):
    """Identifica una asistencia: alumno + clase + minuto (sin importar mayúsculas)."""
    return (str(nombre).strip().lower(), str(clase).strip().lower(), fecha_utc.strftime("%Y-%m-%d %H:%M"))


def leer_mysql():
    con = pymysql.connect(**MYSQL, cursorclass=pymysql.cursors.DictCursor)
    with con, con.cursor() as c:
        c.execute("SELECT id, nombre FROM roles")
        roles = c.fetchall()
        c.execute("SELECT id, username, email, password FROM usuarios")
        usuarios = c.fetchall()
        c.execute("SELECT usuario_id, rol_id FROM usuario_roles")
        usuario_roles = c.fetchall()
        c.execute("SELECT id, rol, CAST(login_habilitado AS UNSIGNED) AS h FROM login_config")
        login = c.fetchall()
        c.execute("SELECT id, usuario_id, nombre, clase, estado, fecha_hora FROM asistencias ORDER BY fecha_hora, id")
        asistencias = c.fetchall()
    return roles, usuarios, usuario_roles, login, asistencias


def main():
    destino_uri = sys.argv[1] if len(sys.argv) > 1 else MONGO_LOCAL
    destino = MongoClient(destino_uri, serverSelectionTimeoutMS=15000)[BD_DESTINO]
    if destino["usuarios"].estimated_document_count() or destino["asistencias"].estimated_document_count():
        print(f"La base '{BD_DESTINO}' del destino ya tiene datos. No se hace nada para no duplicar.")
        return

    roles, usuarios, usuario_roles, login, asis_mysql = leer_mysql()
    historial = list(MongoClient(MONGO_LOCAL)["control_asistencia_mongo"]["asistencias"].find({}))

    # ---------------- roles y usuarios (los roles van dentro de cada usuario)
    rol_por_id = {r["id"]: {"_id": r["id"], "nombre": r["nombre"]} for r in roles}
    roles_de = {}
    for ur in usuario_roles:
        if ur["rol_id"] in rol_por_id:
            roles_de.setdefault(ur["usuario_id"], []).append(rol_por_id[ur["rol_id"]])
    docs_usuarios = []
    for u in usuarios:
        d = {"_id": u["id"], "username": u["username"], "password": u["password"], "roles": roles_de.get(u["id"], [])}
        if u["email"]:
            d["email"] = u["email"]
        docs_usuarios.append(d)
    docs_login = [{"_id": l["id"], "rol": l["rol"], "login_habilitado": bool(l["h"])} for l in login]

    # ---------------- asistencias: historial primero, luego las de MySQL que no estén repetidas
    filas, vistos = [], set()
    for h in historial:
        f = h.get("fechahora") or h.get("fechaHora")
        if not (h.get("nombre") and h.get("clase") and f and h.get("estado")):
            continue
        f = f.replace(tzinfo=UTC) if f.tzinfo is None else f   # Mongo guarda en UTC
        vistos.add(clave(h["nombre"], h["clase"], f))
        filas.append({"nombre": h["nombre"].strip(), "clase": h["clase"].strip(),
                      "estado": estado_normal(h["estado"]), "fechahora": f, "origen": "historial"})

    repetidas = 0
    for a in asis_mysql:
        if not (a["nombre"] and a["clase"] and a["fecha_hora"]):
            continue
        # El historial importado a MySQL quedó con la hora UTC; se compara así primero
        if clave(a["nombre"], a["clase"], a["fecha_hora"].replace(tzinfo=UTC)) in vistos:
            repetidas += 1
            continue
        f = a["fecha_hora"].replace(tzinfo=ZONA).astimezone(UTC)   # registros de la app: hora de Colombia
        if clave(a["nombre"], a["clase"], f) in vistos:
            repetidas += 1
            continue
        vistos.add(clave(a["nombre"], a["clase"], f))
        d = {"nombre": a["nombre"].strip(), "clase": a["clase"].strip(),
             "estado": estado_normal(a["estado"]), "fechahora": f, "origen": "app"}
        if a["usuario_id"]:
            d["usuario_id"] = a["usuario_id"]
        filas.append(d)

    filas.sort(key=lambda d: d["fechahora"])
    for i, d in enumerate(filas, start=1):
        d["_id"] = i

    # ---------------- escribir
    destino["roles"].insert_many(list(rol_por_id.values()))
    destino["usuarios"].insert_many(docs_usuarios)
    if docs_login:
        destino["login_config"].insert_many(docs_login)
    destino["asistencias"].insert_many(filas)
    destino["contadores"].insert_many([
        {"_id": "usuarios", "seq": max((u["_id"] for u in docs_usuarios), default=0)},
        {"_id": "roles", "seq": max(rol_por_id, default=0)},
        {"_id": "login_config", "seq": max((l["_id"] for l in docs_login), default=0)},
        {"_id": "asistencias", "seq": len(filas)},
    ])

    print(f"Listo en '{BD_DESTINO}' ({datetime.now():%H:%M}):")
    print(f"  usuarios: {len(docs_usuarios)} · roles: {len(rol_por_id)} · login_config: {len(docs_login)}")
    print(f"  asistencias: {len(filas)} (historial {len(historial)} + MySQL {len(asis_mysql)} "
          f"- {repetidas} repetidas omitidas)")


if __name__ == "__main__":
    main()
