"""Excepciones propias de Billx.

La UI solo debe capturar estas clases, nunca las del driver (mysql.connector)
ni las de sqlite3: asi un cambio de motor no obliga a tocar las pantallas.
"""


class BillxError(Exception):
    """Base de todos los errores controlados de la aplicacion."""


class ConfigError(BillxError):
    """Falta configuracion obligatoria (variables de entorno / .env)."""


class DatabaseError(BillxError):
    """Fallo de acceso a la base de datos (red caida, credenciales, SQL...)."""
