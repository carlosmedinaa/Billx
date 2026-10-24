"""Crea o amplia las tablas de Billx con el usuario ADMIN (permisos DDL).

Uso (una vez, o cuando cambie TABLAS en database.py):
    python init_esquema.py

Necesita BILLX_DB_ADMIN_USER / BILLX_DB_ADMIN_PASSWORD en el entorno o en .env.
La aplicacion diaria usa un usuario SIN permisos DDL y no toca el esquema.
"""
import sys

from database import init_db
from errores import BillxError


def main():
    try:
        init_db(admin=True)
    except BillxError as error:
        print("ERROR:", error)
        return 1
    print("Esquema creado/actualizado correctamente.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
