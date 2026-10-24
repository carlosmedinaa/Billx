"""Comprueba que la app puede llegar a MySQL (Tailscale + credenciales de .env)."""
import sys

from database import comprobar_conexion
from errores import BillxError

try:
    comprobar_conexion()
    print("Conexion correcta con el servidor de datos.")
except BillxError as error:
    print("Error de conexion:\n" + str(error))
    sys.exit(1)
