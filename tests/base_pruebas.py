"""Utilidades comunes de las pruebas que usan MySQL.

SOLO se ejecutan contra la base billx_test. Hay que pedirlo expresamente:

    PowerShell:  $env:BILLX_DB_NAME = "billx_test"; python -m unittest discover -s tests -v
    Git Bash:    BILLX_DB_NAME=billx_test python -m unittest discover -s tests -v

Sin esa variable, estas pruebas se saltan. Ademas, antes de borrar nada se
pregunta al servidor (SELECT DATABASE()) a que base se esta conectado.

Preparacion (una vez, como root en el servidor):
    CREATE DATABASE billx_test CHARACTER SET utf8mb4;
    GRANT ALL PRIVILEGES ON billx_test.* TO 'billx_app'@'%';
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_PRUEBAS = "billx_test"
TABLAS_A_VACIAR = ("documentos_lineas", "documentos", "clientes", "articulos", "empresas")


def _base_conectada(cursor):
    cursor.execute("SELECT DATABASE()")
    return cursor.fetchone()[0]


def exigir_base_de_pruebas():
    """Llamar desde setUpModule(). Salta las pruebas si no se apunta a billx_test."""
    if os.environ.get("BILLX_DB_NAME") != BASE_PRUEBAS:
        raise unittest.SkipTest("Define BILLX_DB_NAME=billx_test para ejecutar las pruebas con base de datos.")
    import database
    con = database.conectar()
    try:
        nombre = _base_conectada(con.cursor())
    finally:
        con.close()
    if nombre != BASE_PRUEBAS:
        raise RuntimeError("Conectado a '%s' en lugar de '%s': pruebas canceladas." % (nombre, BASE_PRUEBAS))
    # Crea/actualiza el esquema de billx_test. Con admin si esta configurado;
    # si no, con el usuario normal (que en billx_test si debe tener permisos DDL).
    database.init_db(admin=bool(os.environ.get("BILLX_DB_ADMIN_USER")))


def vaciar_tablas():
    import database
    con = database.conectar()
    cursor = con.cursor()
    try:
        if _base_conectada(cursor) != BASE_PRUEBAS:
            raise RuntimeError("Me niego a vaciar una base que no es " + BASE_PRUEBAS)
        for tabla in TABLAS_A_VACIAR:
            cursor.execute("DELETE FROM " + tabla)
        con.commit()
    finally:
        cursor.close()
        con.close()


def crear_empresa(**datos):
    from database import insertar
    base = {"nombre": "Empresa Pruebas", "nif": "B00000000", "serie_factura": "FAC-",
            "serie_presupuesto": "PRE-", "serie_albaran": "ALB-", "siguiente_factura": 1,
            "siguiente_presupuesto": 1, "siguiente_albaran": 1, "retencion_irpf": 0,
            "predeterminada": 0, "activo": 1}
    base.update(datos)
    return insertar("empresas", base)


_contador_clientes = [0]


def crear_cliente(**datos):
    from database import insertar
    _contador_clientes[0] += 1
    base = {"codigo": "CLI-%04d" % _contador_clientes[0],
            "nombre": "Cliente", "nif": "", "forma_pago": "Transferencia", "dias_pago": 30,
            "descuento": 0, "recargo_equivalencia": 0, "exento_iva": 0, "activo": 1}
    base.update(datos)
    return insertar("clientes", base)
