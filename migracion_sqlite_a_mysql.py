import sqlite3
import mysql.connector
import os

from config import mysql_config
from errores import ConfigError

DB_SQLITE_PATH = r"C:\Users\medin\Desktop\00000000 TFG ERP\gestion.db"

# Credenciales: BILLX_DB_ADMIN_* en el entorno o en .env (ver config.py). Nada en el codigo.

TABLAS_MYSQL = {
    "empresas": """CREATE TABLE IF NOT EXISTS empresas (
        id INT AUTO_INCREMENT PRIMARY KEY,
        nombre VARCHAR(255) NOT NULL DEFAULT '',
        nombre_comercial VARCHAR(255) NOT NULL DEFAULT '',
        nif VARCHAR(50) NOT NULL DEFAULT '',
        direccion VARCHAR(255) NOT NULL DEFAULT '',
        cp VARCHAR(20) NOT NULL DEFAULT '',
        ciudad VARCHAR(100) NOT NULL DEFAULT '',
        provincia VARCHAR(100) NOT NULL DEFAULT '',
        pais VARCHAR(100) NOT NULL DEFAULT 'España',
        telefono VARCHAR(50) NOT NULL DEFAULT '',
        email VARCHAR(150) NOT NULL DEFAULT '',
        web VARCHAR(150) NOT NULL DEFAULT '',
        iban VARCHAR(50) NOT NULL DEFAULT '',
        logo VARCHAR(255) NOT NULL DEFAULT '',
        serie_factura VARCHAR(20) NOT NULL DEFAULT 'FAC-',
        serie_presupuesto VARCHAR(20) NOT NULL DEFAULT 'PRE-',
        serie_albaran VARCHAR(20) NOT NULL DEFAULT 'ALB-',
        siguiente_factura INT NOT NULL DEFAULT 1,
        siguiente_presupuesto INT NOT NULL DEFAULT 1,
        siguiente_albaran INT NOT NULL DEFAULT 1,
        retencion_irpf DOUBLE NOT NULL DEFAULT 0,
        pie_documento TEXT,
        predeterminada TINYINT NOT NULL DEFAULT 0,
        activo TINYINT NOT NULL DEFAULT 1,
        fecha_creacion VARCHAR(50) NOT NULL DEFAULT ''
    )""",
    "clientes": """CREATE TABLE IF NOT EXISTS clientes (
        id INT AUTO_INCREMENT PRIMARY KEY,
        codigo VARCHAR(50) NOT NULL DEFAULT '',
        nombre VARCHAR(255) NOT NULL DEFAULT '',
        nombre_comercial VARCHAR(255) NOT NULL DEFAULT '',
        nif VARCHAR(50) NOT NULL DEFAULT '',
        tipo VARCHAR(50) NOT NULL DEFAULT 'Empresa',
        direccion VARCHAR(255) NOT NULL DEFAULT '',
        cp VARCHAR(20) NOT NULL DEFAULT '',
        ciudad VARCHAR(100) NOT NULL DEFAULT '',
        provincia VARCHAR(100) NOT NULL DEFAULT '',
        pais VARCHAR(100) NOT NULL DEFAULT 'España',
        telefono VARCHAR(50) NOT NULL DEFAULT '',
        email VARCHAR(150) NOT NULL DEFAULT '',
        contacto VARCHAR(150) NOT NULL DEFAULT '',
        iban VARCHAR(50) NOT NULL DEFAULT '',
        forma_pago VARCHAR(50) NOT NULL DEFAULT 'Transferencia',
        dias_pago INT NOT NULL DEFAULT 0,
        descuento DOUBLE NOT NULL DEFAULT 0,
        recargo_equivalencia TINYINT NOT NULL DEFAULT 0,
        exento_iva TINYINT NOT NULL DEFAULT 0,
        notas TEXT,
        activo TINYINT NOT NULL DEFAULT 1,
        fecha_creacion VARCHAR(50) NOT NULL DEFAULT ''
    )""",
    "articulos": """CREATE TABLE IF NOT EXISTS articulos (
        id INT AUTO_INCREMENT PRIMARY KEY,
        referencia VARCHAR(100) NOT NULL DEFAULT '',
        descripcion TEXT,
        tipo VARCHAR(50) NOT NULL DEFAULT 'Producto',
        familia VARCHAR(100) NOT NULL DEFAULT '',
        unidad VARCHAR(50) NOT NULL DEFAULT 'Unidad',
        precio_coste DOUBLE NOT NULL DEFAULT 0,
        precio_venta DOUBLE NOT NULL DEFAULT 0,
        iva DOUBLE NOT NULL DEFAULT 21,
        control_stock TINYINT NOT NULL DEFAULT 0,
        stock DOUBLE NOT NULL DEFAULT 0,
        stock_minimo DOUBLE NOT NULL DEFAULT 0,
        activo TINYINT NOT NULL DEFAULT 1,
        notas TEXT,
        fecha_creacion VARCHAR(50) NOT NULL DEFAULT ''
    )""",
    "documentos": """CREATE TABLE IF NOT EXISTS documentos (
        id INT AUTO_INCREMENT PRIMARY KEY,
        tipo VARCHAR(50) NOT NULL DEFAULT 'factura',
        numero VARCHAR(50) NOT NULL DEFAULT '',
        fecha VARCHAR(50) NOT NULL DEFAULT '',
        empresa_id INT NOT NULL DEFAULT 0,
        cliente_id INT NOT NULL DEFAULT 0,
        cliente_nombre VARCHAR(255) NOT NULL DEFAULT '',
        cliente_nif VARCHAR(50) NOT NULL DEFAULT '',
        cliente_direccion VARCHAR(255) NOT NULL DEFAULT '',
        cliente_cp VARCHAR(20) NOT NULL DEFAULT '',
        cliente_ciudad VARCHAR(100) NOT NULL DEFAULT '',
        cliente_provincia VARCHAR(100) NOT NULL DEFAULT '',
        cliente_pais VARCHAR(100) NOT NULL DEFAULT '',
        base_imponible DOUBLE NOT NULL DEFAULT 0,
        total_iva DOUBLE NOT NULL DEFAULT 0,
        total_recargo DOUBLE NOT NULL DEFAULT 0,
        total DOUBLE NOT NULL DEFAULT 0,
        notas TEXT,
        estado VARCHAR(50) NOT NULL DEFAULT 'Borrador',
        fecha_creacion VARCHAR(50) NOT NULL DEFAULT '',
        forma_pago VARCHAR(50) NOT NULL DEFAULT 'Transferencia',
        fecha_vencimiento VARCHAR(50) NOT NULL DEFAULT ''
    )""",
    "documentos_lineas": """CREATE TABLE IF NOT EXISTS documentos_lineas (
        id INT AUTO_INCREMENT PRIMARY KEY,
        documento_id INT NOT NULL,
        articulo_id INT NOT NULL DEFAULT 0,
        referencia VARCHAR(100) NOT NULL DEFAULT '',
        descripcion TEXT,
        cantidad DOUBLE NOT NULL DEFAULT 1,
        precio_unitario DOUBLE NOT NULL DEFAULT 0,
        porcentaje_descuento DOUBLE NOT NULL DEFAULT 0,
        porcentaje_iva DOUBLE NOT NULL DEFAULT 21,
        subtotal DOUBLE NOT NULL DEFAULT 0
    )"""
}

# Aquí definimos exactamente qué columnas existen en MySQL para filtrar
COLUMNAS_VALIDAS = {
    "empresas": ["id", "nombre", "nombre_comercial", "nif", "direccion", "cp", "ciudad", "provincia", "pais", "telefono", "email", "web", "iban", "logo", "serie_factura", "serie_presupuesto", "serie_albaran", "siguiente_factura", "siguiente_presupuesto", "siguiente_albaran", "retencion_irpf", "pie_documento", "predeterminada", "activo", "fecha_creacion"],
    "clientes": ["id", "codigo", "nombre", "nombre_comercial", "nif", "tipo", "direccion", "cp", "ciudad", "provincia", "pais", "telefono", "email", "contacto", "iban", "forma_pago", "dias_pago", "descuento", "recargo_equivalencia", "exento_iva", "notas", "activo", "fecha_creacion"],
    "articulos": ["id", "referencia", "descripcion", "tipo", "familia", "unidad", "precio_coste", "precio_venta", "iva", "control_stock", "stock", "stock_minimo", "activo", "notas", "fecha_creacion"],
    "documentos": ["id", "tipo", "numero", "fecha", "empresa_id", "cliente_id", "cliente_nombre", "cliente_nif", "cliente_direccion", "cliente_cp", "cliente_ciudad", "cliente_provincia", "cliente_pais", "base_imponible", "total_iva", "total_recargo", "total", "notas", "estado", "fecha_creacion", "forma_pago", "fecha_vencimiento"],
    "documentos_lineas": ["id", "documento_id", "articulo_id", "referencia", "descripcion", "cantidad", "precio_unitario", "porcentaje_descuento", "porcentaje_iva", "subtotal"]
}

def migrar_datos():
    print("ATENCION: este script BORRA (DROP TABLE) todas las tablas de Billx en MySQL")
    print("y las recrea desde SQLite. Si ya hay datos reales en el servidor, se pierden.")
    if input("Escribe BORRAR para continuar: ").strip() != "BORRAR":
        print("Cancelado.")
        return

    if not os.path.exists(DB_SQLITE_PATH):
        print(f"ERROR: No se encuentra {DB_SQLITE_PATH}")
        return

    con_sqlite = sqlite3.connect(DB_SQLITE_PATH)
    con_sqlite.row_factory = sqlite3.Row
    cursor_sqlite = con_sqlite.cursor()

    try:
        con_mysql = mysql.connector.connect(**mysql_config(admin=True))
        cursor_mysql = con_mysql.cursor()
    except (mysql.connector.Error, ConfigError) as e:
        print(f"Error al conectar con MySQL: {e}")
        return

    # Primero limpiamos las tablas que se quedaron a medias
    for tabla in TABLAS_MYSQL.keys():
        cursor_mysql.execute(f"DROP TABLE IF EXISTS {tabla}")

    # Creamos las tablas con la estructura limpia y mejorada (TEXT para descripciones largas)
    for tabla, ddl in TABLAS_MYSQL.items():
        cursor_mysql.execute(ddl)

    # Migrar tabla a tabla usando solo las columnas válidas
    for tabla in TABLAS_MYSQL.keys():
        print(f"\nMigrando datos de la tabla: {tabla}...")
        
        cursor_sqlite.execute(f"SELECT * FROM {tabla}")
        filas = cursor_sqlite.fetchall()
        
        if not filas:
            print("   Sin datos. Saltando.")
            continue

        columnas_disponibles_sqlite = list(filas[0].keys())
        
        # Filtramos para quedarnos solo con las columnas que existen en MySQL
        columnas_a_migrar = [col for col in columnas_disponibles_sqlite if col in COLUMNAS_VALIDAS[tabla]]
        
        marcadores = ", ".join(["%s"] * len(columnas_a_migrar))
        nombres_columnas = ", ".join(columnas_a_migrar)
        sql_insert = f"INSERT INTO {tabla} ({nombres_columnas}) VALUES ({marcadores})"
        
        contador = 0
        for fila in filas:
            # Extraer solo los valores de las columnas válidas y aplicar escudo anti-None
            valores = tuple((0 if fila[col] is None else fila[col]) for col in columnas_a_migrar)
            
            try:
                cursor_mysql.execute(sql_insert, valores)
                contador += 1
            except Exception as e:
                print(f"   Error fila ID {fila['id']}: {e}")
                
        con_mysql.commit()
        print(f"   => Migrados {contador} registros con éxito.")

    cursor_sqlite.close()
    con_sqlite.close()
    cursor_mysql.close()
    con_mysql.close()
    print("\n¡MIGRACIÓN COMPLETADA CON ÉXITO!")

if __name__ == "__main__":
    migrar_datos()