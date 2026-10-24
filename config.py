"""Configuracion de Billx. Los secretos NUNCA van en el codigo ni en git.

Orden de busqueda de cada valor:
  1. Variable de entorno del sistema.
  2. Fichero .env junto al ejecutable (PyInstaller) o junto a este archivo.

Variables:
  BILLX_DB_HOST        (obligatoria)  IP/nombre del servidor MySQL (Tailscale)
  BILLX_DB_USER        (obligatoria)  usuario de la APLICACION (sin DDL, no root)
  BILLX_DB_PASSWORD    (obligatoria)
  BILLX_DB_NAME        (defecto: billx_db)
  BILLX_DB_PORT        (defecto: 3306)
  BILLX_DB_TIMEOUT     (defecto: 5)   segundos de espera al conectar
  BILLX_AUTO_INIT_DB   (defecto: 0)   1 = crear/ampliar tablas al arrancar
                                      (solo en desarrollo, necesita permisos DDL)
  BILLX_DB_ADMIN_USER / BILLX_DB_ADMIN_PASSWORD
                       (opcionales)   solo para init_esquema.py y migraciones
  BILLX_MYSQLDUMP      (opcional)     ruta a mysqldump si no esta en el PATH
"""
import os
import sys

from errores import ConfigError

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _cargar_dotenv(ruta):
    """Lector minimo de .env (CLAVE=valor). No pisa variables ya definidas."""
    if not os.path.isfile(ruta):
        return
    with open(ruta, encoding="utf-8") as archivo:
        for linea in archivo:
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            clave, _, valor = linea.partition("=")
            valor = valor.strip().strip('"').strip("'")
            os.environ.setdefault(clave.strip(), valor)


_cargar_dotenv(os.path.join(BASE_DIR, ".env"))


def _obligatoria(nombre):
    valor = os.environ.get(nombre, "").strip()
    if not valor:
        raise ConfigError(
            "Falta la variable de configuracion " + nombre + ".\n\n"
            "Crea un archivo .env junto al programa (hay un modelo en .env.example)."
        )
    return valor


def _entero(nombre, defecto):
    try:
        return int(os.environ.get(nombre, defecto))
    except ValueError:
        raise ConfigError(nombre + " debe ser un numero entero.")


def mysql_config(admin=False):
    """Diccionario listo para mysql.connector.connect().

    admin=True usa BILLX_DB_ADMIN_* (permisos DDL) y se reserva para
    init_esquema.py y los scripts de migracion, nunca para la app diaria.
    """
    if admin:
        usuario = _obligatoria("BILLX_DB_ADMIN_USER")
        password = _obligatoria("BILLX_DB_ADMIN_PASSWORD")
    else:
        usuario = _obligatoria("BILLX_DB_USER")
        password = _obligatoria("BILLX_DB_PASSWORD")
    return {
        "host": _obligatoria("BILLX_DB_HOST"),
        "user": usuario,
        "password": password,
        "database": os.environ.get("BILLX_DB_NAME", "billx_db"),
        "port": _entero("BILLX_DB_PORT", 3306),
        "connection_timeout": _entero("BILLX_DB_TIMEOUT", 5),
    }


def auto_init_db():
    return os.environ.get("BILLX_AUTO_INIT_DB", "0").strip() == "1"
