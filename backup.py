"""Copias de seguridad de la base de datos MySQL con mysqldump.

La copia fiable es la del SERVIDOR (ver scripts/backup_servidor.sh). Esta
funcion es la copia manual de comodidad desde el menu de la aplicacion.
La contrasena se pasa por variable de entorno (MYSQL_PWD), nunca por la
linea de comandos, para que no aparezca en la lista de procesos.
"""
import os
import shutil
import subprocess

from config import mysql_config
from errores import DatabaseError


def localizar_mysqldump():
    ruta = os.environ.get("BILLX_MYSQLDUMP", "").strip()
    if ruta and os.path.isfile(ruta):
        return ruta
    return shutil.which("mysqldump") or shutil.which("mariadb-dump")


def volcar_base_de_datos(ruta_destino):
    """Genera un volcado .sql completo en ruta_destino. Lanza DatabaseError."""
    ejecutable = localizar_mysqldump()
    if not ejecutable:
        raise DatabaseError(
            "No se encontro 'mysqldump' en este equipo.\n\n"
            "Instala MySQL Client/Workbench o indica su ruta en BILLX_MYSQLDUMP (.env).\n"
            "Recuerda que la copia automatica diaria debe hacerse en el servidor."
        )

    cfg = mysql_config()
    comando = [
        ejecutable,
        "--host=" + cfg["host"],
        "--port=" + str(cfg["port"]),
        "--user=" + cfg["user"],
        "--single-transaction",
        "--default-character-set=utf8mb4",
        "--result-file=" + ruta_destino,
        cfg["database"],
    ]
    entorno = dict(os.environ, MYSQL_PWD=cfg["password"])
    opciones = {}
    if os.name == "nt":
        opciones["creationflags"] = 0x08000000  # CREATE_NO_WINDOW: sin ventana negra

    try:
        resultado = subprocess.run(comando, env=entorno, capture_output=True,
                                   text=True, timeout=300, **opciones)
    except subprocess.TimeoutExpired:
        _borrar_parcial(ruta_destino)
        raise DatabaseError("La copia de seguridad tardo demasiado y se cancelo.")
    except OSError as error:
        raise DatabaseError("No se pudo ejecutar mysqldump: " + str(error))

    if resultado.returncode != 0:
        _borrar_parcial(ruta_destino)
        raise DatabaseError("mysqldump fallo:\n" + (resultado.stderr or "").strip())
    if not os.path.isfile(ruta_destino) or os.path.getsize(ruta_destino) == 0:
        _borrar_parcial(ruta_destino)
        raise DatabaseError("La copia de seguridad salio vacia; no se ha guardado.")
    return ruta_destino


def _borrar_parcial(ruta):
    try:
        if os.path.isfile(ruta):
            os.remove(ruta)
    except OSError:
        pass
