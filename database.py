import functools
from datetime import datetime

import mysql.connector

from calculos import calcular_documento
from config import BASE_DIR, mysql_config
from errores import ConfigError, DatabaseError

TIPOS_DOCUMENTO = ("factura", "presupuesto", "albaran")

# Estructura adaptada a MySQL
TABLAS = {
    "empresas": (
        ("nombre", "VARCHAR(255) NOT NULL DEFAULT ''"),
        ("nombre_comercial", "VARCHAR(255) NOT NULL DEFAULT ''"),
        ("nif", "VARCHAR(50) NOT NULL DEFAULT ''"),
        ("direccion", "VARCHAR(255) NOT NULL DEFAULT ''"),
        ("cp", "VARCHAR(20) NOT NULL DEFAULT ''"),
        ("ciudad", "VARCHAR(100) NOT NULL DEFAULT ''"),
        ("provincia", "VARCHAR(100) NOT NULL DEFAULT ''"),
        ("pais", "VARCHAR(100) NOT NULL DEFAULT 'España'"),
        ("telefono", "VARCHAR(50) NOT NULL DEFAULT ''"),
        ("email", "VARCHAR(150) NOT NULL DEFAULT ''"),
        ("web", "VARCHAR(150) NOT NULL DEFAULT ''"),
        ("iban", "VARCHAR(50) NOT NULL DEFAULT ''"),
        ("logo", "VARCHAR(255) NOT NULL DEFAULT ''"),
        ("serie_factura", "VARCHAR(20) NOT NULL DEFAULT 'FAC-'"),
        ("serie_presupuesto", "VARCHAR(20) NOT NULL DEFAULT 'PRE-'"),
        ("serie_albaran", "VARCHAR(20) NOT NULL DEFAULT 'ALB-'"),
        ("siguiente_factura", "INT NOT NULL DEFAULT 1"),
        ("siguiente_presupuesto", "INT NOT NULL DEFAULT 1"),
        ("siguiente_albaran", "INT NOT NULL DEFAULT 1"),
        ("retencion_irpf", "DECIMAL(5,2) NOT NULL DEFAULT 0"),
        ("pie_documento", "TEXT"),
        ("predeterminada", "TINYINT NOT NULL DEFAULT 0"),
        ("activo", "TINYINT NOT NULL DEFAULT 1"),
        ("fecha_creacion", "VARCHAR(50) NOT NULL DEFAULT ''"),
    ),
    "clientes": (
        ("codigo", "VARCHAR(50) NOT NULL DEFAULT ''"),
        ("nombre", "VARCHAR(255) NOT NULL DEFAULT ''"),
        ("nombre_comercial", "VARCHAR(255) NOT NULL DEFAULT ''"),
        ("nif", "VARCHAR(50) NOT NULL DEFAULT ''"),
        ("tipo", "VARCHAR(50) NOT NULL DEFAULT 'Empresa'"),
        ("direccion", "VARCHAR(255) NOT NULL DEFAULT ''"),
        ("cp", "VARCHAR(20) NOT NULL DEFAULT ''"),
        ("ciudad", "VARCHAR(100) NOT NULL DEFAULT ''"),
        ("provincia", "VARCHAR(100) NOT NULL DEFAULT ''"),
        ("pais", "VARCHAR(100) NOT NULL DEFAULT 'España'"),
        ("telefono", "VARCHAR(50) NOT NULL DEFAULT ''"),
        ("email", "VARCHAR(150) NOT NULL DEFAULT ''"),
        ("contacto", "VARCHAR(150) NOT NULL DEFAULT ''"),
        ("iban", "VARCHAR(50) NOT NULL DEFAULT ''"),
        ("forma_pago", "VARCHAR(50) NOT NULL DEFAULT 'Transferencia'"),
        ("dias_pago", "INT NOT NULL DEFAULT 0"),
        ("descuento", "DECIMAL(5,2) NOT NULL DEFAULT 0"),
        ("recargo_equivalencia", "TINYINT NOT NULL DEFAULT 0"),
        ("exento_iva", "TINYINT NOT NULL DEFAULT 0"),
        ("notas", "TEXT"),
        ("activo", "TINYINT NOT NULL DEFAULT 1"),
        ("fecha_creacion", "VARCHAR(50) NOT NULL DEFAULT ''"),
    ),
    "articulos": (
        ("referencia", "VARCHAR(100) NOT NULL DEFAULT ''"),
        ("descripcion", "TEXT"),
        ("tipo", "VARCHAR(50) NOT NULL DEFAULT 'Producto'"),
        ("familia", "VARCHAR(100) NOT NULL DEFAULT ''"),
        ("unidad", "VARCHAR(50) NOT NULL DEFAULT 'Unidad'"),
        ("precio_coste", "DECIMAL(12,4) NOT NULL DEFAULT 0"),
        ("precio_venta", "DECIMAL(12,4) NOT NULL DEFAULT 0"),
        ("iva", "DECIMAL(5,2) NOT NULL DEFAULT 21"),
        ("control_stock", "TINYINT NOT NULL DEFAULT 0"),
        ("stock", "DECIMAL(12,3) NOT NULL DEFAULT 0"),
        ("stock_minimo", "DECIMAL(12,3) NOT NULL DEFAULT 0"),
        ("activo", "TINYINT NOT NULL DEFAULT 1"),
        ("notas", "TEXT"),
        ("fecha_creacion", "VARCHAR(50) NOT NULL DEFAULT ''"),
    ),
    "documentos": (
        ("tipo", "VARCHAR(50) NOT NULL DEFAULT 'factura'"),
        ("numero", "VARCHAR(50) NOT NULL DEFAULT ''"),
        ("fecha", "VARCHAR(50) NOT NULL DEFAULT ''"),
        ("empresa_id", "INT NOT NULL DEFAULT 0"),
        ("cliente_id", "INT NOT NULL DEFAULT 0"),
        ("cliente_nombre", "VARCHAR(255) NOT NULL DEFAULT ''"),
        ("cliente_nif", "VARCHAR(50) NOT NULL DEFAULT ''"),
        ("cliente_direccion", "VARCHAR(255) NOT NULL DEFAULT ''"),
        ("cliente_cp", "VARCHAR(20) NOT NULL DEFAULT ''"),
        ("cliente_ciudad", "VARCHAR(100) NOT NULL DEFAULT ''"),
        ("cliente_provincia", "VARCHAR(100) NOT NULL DEFAULT ''"),
        ("cliente_pais", "VARCHAR(100) NOT NULL DEFAULT ''"),
        ("base_imponible", "DECIMAL(12,2) NOT NULL DEFAULT 0"),
        ("total_iva", "DECIMAL(12,2) NOT NULL DEFAULT 0"),
        ("total_recargo", "DECIMAL(12,2) NOT NULL DEFAULT 0"),
        ("total", "DECIMAL(12,2) NOT NULL DEFAULT 0"),
        ("notas", "TEXT"),
        ("estado", "VARCHAR(50) NOT NULL DEFAULT 'Borrador'"),
        ("fecha_creacion", "VARCHAR(50) NOT NULL DEFAULT ''"),
        ("forma_pago", "VARCHAR(50) NOT NULL DEFAULT 'Transferencia'"),
        ("fecha_vencimiento", "VARCHAR(50) NOT NULL DEFAULT ''"),
        # Regimen fiscal congelado al guardar: reimprimir o editar no depende
        # de como este hoy la ficha del cliente o de la empresa.
        ("exento_iva", "TINYINT NOT NULL DEFAULT 0"),
        ("recargo_equivalencia", "TINYINT NOT NULL DEFAULT 0"),
        ("porcentaje_irpf", "DECIMAL(5,2) NOT NULL DEFAULT 0"),
        ("total_retencion", "DECIMAL(12,2) NOT NULL DEFAULT 0"),
    ),
    "documentos_lineas": (
        ("documento_id", "INT NOT NULL"),
        ("articulo_id", "INT NOT NULL DEFAULT 0"),
        ("referencia", "VARCHAR(100) NOT NULL DEFAULT ''"),
        ("descripcion", "TEXT"),
        ("cantidad", "DECIMAL(12,3) NOT NULL DEFAULT 1"),
        ("precio_unitario", "DECIMAL(12,4) NOT NULL DEFAULT 0"),
        ("porcentaje_descuento", "DECIMAL(5,2) NOT NULL DEFAULT 0"),
        ("porcentaje_iva", "DECIMAL(5,2) NOT NULL DEFAULT 21"),
        ("subtotal", "DECIMAL(12,2) NOT NULL DEFAULT 0"),
    ),
}

# Indices que init_db crea si faltan. El de lineas es imprescindible: sin el,
# "DELETE ... WHERE documento_id" recorre y BLOQUEA toda la tabla en InnoDB.
INDICES = {
    "documentos": (("idx_documentos_numero", "empresa_id, tipo, numero"),),
    "documentos_lineas": (("idx_lineas_documento", "documento_id"),),
}

def _traducir_errores(funcion):
    """Convierte cualquier error del driver MySQL en DatabaseError.

    Asi la UI solo conoce errores.DatabaseError y no depende del motor.
    ValueError (validaciones) y ConfigError pasan sin tocar.
    """
    @functools.wraps(funcion)
    def envoltura(*args, **kwargs):
        try:
            return funcion(*args, **kwargs)
        except (DatabaseError, ConfigError):
            raise
        except mysql.connector.Error as error:
            raise DatabaseError(_mensaje_amigable(error)) from error
    return envoltura


_ERRNO_RED = (2002, 2003, 2006, 2013, 2055)


def _mensaje_amigable(error):
    errno = getattr(error, "errno", None)
    sin_red = errno in _ERRNO_RED or (
        errno is None and isinstance(error, (mysql.connector.errors.InterfaceError,
                                             mysql.connector.errors.OperationalError)))
    if sin_red:
        return ("No se pudo conectar con el servidor de datos.\n"
                "Comprueba que Tailscale esta conectado y que el servidor esta encendido.\n\n"
                "Detalle tecnico: " + str(error))
    if errno == 1045:
        return "Usuario o contrasena de la base de datos incorrectos.\n\nDetalle tecnico: " + str(error)
    if errno == 1142:
        return "El usuario de la base de datos no tiene permiso para esta operacion.\n\nDetalle tecnico: " + str(error)
    if errno in (1205, 1213):
        return ("Otro puesto estaba guardando a la vez y no se ha podido completar la operacion.\n"
                "No se ha guardado nada: vuelve a intentarlo.\n\nDetalle tecnico: " + str(error))
    return "Error de base de datos: " + str(error)


def conectar():
    """Abre una conexion nueva con la configuracion de entorno."""
    try:
        return mysql.connector.connect(**mysql_config())
    except mysql.connector.Error as error:
        raise DatabaseError(_mensaje_amigable(error)) from error


def comprobar_conexion():
    """Lanza DatabaseError si el servidor no responde. Usar al arrancar."""
    con = conectar()
    try:
        cursor = con.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        cursor.close()
    finally:
        con.close()

@_traducir_errores
def comprobar_esquema():
    """Lanza DatabaseError si a la base le faltan columnas que este programa usa
    (p. ej. se instalo una version nueva sin ejecutar la migracion). Solo lectura."""
    con = conectar()
    cursor = con.cursor()
    try:
        cursor.execute(
            "SELECT TABLE_NAME, COLUMN_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE()"
        )
        existentes = {(t.lower(), c.lower()) for t, c in cursor.fetchall()}
    finally:
        cursor.close()
        con.close()
    faltan = [tabla + "." + nombre for tabla, definicion in TABLAS.items()
              for nombre, _tipo in definicion if (tabla, nombre) not in existentes]
    if faltan:
        raise DatabaseError(
            "La base de datos no esta actualizada para esta version de Billx.\n"
            "Faltan columnas: " + ", ".join(faltan) + "\n\n"
            "Hay que ejecutar la migracion (sql/migracion_decimal.sql) con el usuario "
            "administrador, despues de hacer copia de seguridad."
        )


def safe_dict(fila):
    """Escudo contra nulos para evitar errores en Python"""
    if not fila: return None
    return {k: ("" if v is None else v) for k, v in fila.items()}

def columnas(tabla):
    if tabla not in TABLAS:
        raise ValueError("Tabla desconocida: " + str(tabla))
    return tuple(nombre for nombre, _tipo in TABLAS[tabla])

@_traducir_errores
def init_db(admin=False):
    """Crea/amplia las tablas. NO se llama en cada consulta: solo al arrancar
    (si BILLX_AUTO_INIT_DB=1) o desde init_esquema.py con el usuario admin."""
    try:
        con = mysql.connector.connect(**mysql_config(admin=admin))
    except mysql.connector.Error as error:
        raise DatabaseError(_mensaje_amigable(error)) from error
    cursor = con.cursor()
    try:
        for tabla, definicion in TABLAS.items():
            campos = ", ".join(nombre + " " + tipo for nombre, tipo in definicion)
            cursor.execute(
                f"CREATE TABLE IF NOT EXISTS {tabla} "
                f"(id INT AUTO_INCREMENT PRIMARY KEY, {campos})"
            )
            # MySQL equivalente a PRAGMA
            cursor.execute(f"SHOW COLUMNS FROM {tabla}")
            existentes = {f[0] for f in cursor.fetchall()}
            for nombre, tipo in definicion:
                if nombre not in existentes:
                    cursor.execute(f"ALTER TABLE {tabla} ADD COLUMN {nombre} {tipo}")
            cursor.execute(f"SHOW INDEX FROM {tabla}")
            indices = {f[2] for f in cursor.fetchall()}
            for nombre, campos in INDICES.get(tabla, ()):
                if nombre not in indices:
                    cursor.execute(f"CREATE INDEX {nombre} ON {tabla} ({campos})")
        con.commit()
    finally:
        cursor.close()
        con.close()

def _normalizar(tabla, datos):
    validas = columnas(tabla)
    limpio = {}
    for clave, valor in datos.items():
        if clave in validas:
            limpio[clave] = valor.strip() if isinstance(valor, str) else valor
    if not limpio:
        raise ValueError("No hay datos que guardar.")
    return limpio

@_traducir_errores
def listar(tabla, texto="", campos_busqueda=(), condiciones=(), params=(), orden="id"):
    validas = columnas(tabla)
    sql = "SELECT id, " + ", ".join(validas) + f" FROM {tabla} WHERE 1 = 1"
    valores = []

    texto = (texto or "").strip()
    campos_busqueda = tuple(c for c in campos_busqueda if c in validas)
    if texto and campos_busqueda:
        sql += " AND (" + " OR ".join(c + " LIKE %s" for c in campos_busqueda) + ")"
        valores.extend(["%" + texto + "%" ] * len(campos_busqueda))

    for condicion in condiciones:
        # Traduce automáticamente las '?' de SQLite al formato '%s' de MySQL
        condicion_adaptada = condicion.replace("?", "%s")
        sql += " AND (" + condicion_adaptada + ")"
        
    valores.extend(params)

    # Limpia el NOCASE por si acaso
    orden = (orden or "id").replace("COLLATE NOCASE", "")
    sql += " ORDER BY " + orden
    
    con = conectar()
    cursor = con.cursor(dictionary=True)
    try:
        cursor.execute(sql, valores)
        return [safe_dict(fila) for fila in cursor.fetchall()]
    finally:
        cursor.close()
        con.close()

@_traducir_errores
def obtener(tabla, registro_id):
    if not registro_id: return None
    con = conectar()
    cursor = con.cursor(dictionary=True)
    try:
        cursor.execute(
            f"SELECT id, " + ", ".join(columnas(tabla)) + f" FROM {tabla} WHERE id = %s",
            (registro_id,)
        )
        return safe_dict(cursor.fetchone())
    finally:
        cursor.close()
        con.close()

@_traducir_errores
def contar(tabla, condiciones=(), params=()):
    sql = f"SELECT COUNT(*) AS total FROM {tabla} WHERE 1 = 1"
    for condicion in condiciones:
        sql += " AND (" + condicion + ")"
    con = conectar()
    cursor = con.cursor(dictionary=True)
    try:
        cursor.execute(sql, tuple(params))
        fila = cursor.fetchone()
        return int(fila["total"]) if fila else 0
    finally:
        cursor.close()
        con.close()

@_traducir_errores
def insertar(tabla, datos):
    limpio = _normalizar(tabla, datos)
    if "fecha_creacion" in columnas(tabla) and not limpio.get("fecha_creacion"):
        limpio["fecha_creacion"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    campos = list(limpio)
    
    sql = f"INSERT INTO {tabla} (" + ", ".join(campos) + ") VALUES (" + ", ".join("%s" for _ in campos) + ")"
    
    con = conectar()
    cursor = con.cursor()
    try:
        cursor.execute(sql, [limpio[c] for c in campos])
        con.commit()
        return cursor.lastrowid
    finally:
        cursor.close()
        con.close()

@_traducir_errores
def actualizar(tabla, registro_id, datos):
    if not registro_id:
        raise ValueError("Falta el identificador del registro.")
    limpio = _normalizar(tabla, datos)
    limpio.pop("fecha_creacion", None)
    if not limpio:
        return registro_id
    campos = list(limpio)
    
    sql = f"UPDATE {tabla} SET " + ", ".join(c + " = %s" for c in campos) + " WHERE id = %s"
    valores = [limpio[c] for c in campos]
    valores.append(registro_id)
    
    con = conectar()
    cursor = con.cursor()
    try:
        cursor.execute(sql, valores)
        con.commit()
        return registro_id
    finally:
        cursor.close()
        con.close()

@_traducir_errores
def eliminar(tabla, registro_id):
    if not registro_id: return False
    con = conectar()
    cursor = con.cursor()
    try:
        cursor.execute(f"DELETE FROM {tabla} WHERE id = %s", (registro_id,))
        con.commit()
        return cursor.rowcount > 0
    finally:
        cursor.close()
        con.close()

@_traducir_errores
def existe_valor(tabla, campo, valor, excluir_id=None):
    valor = (valor or "").strip()
    if not valor or campo not in columnas(tabla):
        return False
    sql = f"SELECT id FROM {tabla} WHERE {campo} = %s"
    params = [valor]
    if excluir_id:
        sql += " AND id <> %s"
        params.append(excluir_id)
    sql += " LIMIT 1"  # sin esto, 2+ coincidencias dejan filas sin leer y cursor.close() falla
    con = conectar()
    cursor = con.cursor()
    try:
        cursor.execute(sql, params)
        return cursor.fetchone() is not None
    finally:
        cursor.close()
        con.close()

@_traducir_errores
def valores_distintos(tabla, campo):
    if campo not in columnas(tabla): return []
    con = conectar()
    cursor = con.cursor(dictionary=True)
    try:
        cursor.execute(
            f"SELECT DISTINCT {campo} AS valor FROM {tabla} "
            f"WHERE {campo} IS NOT NULL AND TRIM({campo}) <> '' "
            f"ORDER BY {campo}"
        )
        return [fila["valor"] for fila in cursor.fetchall()]
    finally:
        cursor.close()
        con.close()

@_traducir_errores
def marcar_empresa_predeterminada(empresa_id):
    if not empresa_id: return
    con = conectar()
    cursor = con.cursor()
    try:
        cursor.execute("UPDATE empresas SET predeterminada = 0")
        cursor.execute("UPDATE empresas SET predeterminada = 1 WHERE id = %s", (empresa_id,))
        con.commit()
    finally:
        cursor.close()
        con.close()

@_traducir_errores
def empresa_predeterminada():
    con = conectar()
    cursor = con.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT id, " + ", ".join(columnas("empresas")) + " FROM empresas "
            "WHERE activo = 1 ORDER BY predeterminada DESC, id LIMIT 1"
        )
        return safe_dict(cursor.fetchone())
    finally:
        cursor.close()
        con.close()

def formatear_numero(serie, numero):
    serie = (serie or "").strip()
    try:
        return serie + "{:04d}".format(int(numero))
    except (TypeError, ValueError):
        return serie + "0001"

@_traducir_errores
def previsualizar_numero(empresa_id, tipo):
    tipo = (tipo or "").strip().lower()
    if tipo not in TIPOS_DOCUMENTO:
        raise ValueError("Tipo de documento no valido: " + str(tipo))
    empresa = obtener("empresas", empresa_id)
    if not empresa: return None
    return formatear_numero(empresa.get("serie_" + tipo), empresa.get("siguiente_" + tipo) or 1)

def _reservar_numero(cursor, empresa_id, tipo):
    """Asigna el siguiente numero de la serie DENTRO de la transaccion en curso.

    SELECT ... FOR UPDATE bloquea la fila de la empresa hasta el commit o el
    rollback: otro puesto que guarde a la vez espera su turno, y si este
    guardado falla el rollback devuelve el contador (sin huecos ni duplicados).
    """
    cursor.execute(
        f"SELECT serie_{tipo}, siguiente_{tipo} FROM empresas WHERE id = %s FOR UPDATE",
        (empresa_id,)
    )
    fila = cursor.fetchone()
    if fila is None:
        raise ValueError("La empresa emisora no existe.")
    serie, siguiente = fila
    numero = max(int(siguiente or 1), 1)
    # Si alguien bajo el contador a mano en la ficha de la empresa, se saltan
    # los numeros que ya existen (no deja huecos: esos numeros estan usados).
    while True:
        candidato = formatear_numero(serie, numero)
        cursor.execute(
            "SELECT 1 FROM documentos WHERE empresa_id = %s AND tipo = %s AND numero = %s LIMIT 1",
            (empresa_id, tipo, candidato)
        )
        if cursor.fetchone() is None:
            break
        numero += 1
    cursor.execute(
        f"UPDATE empresas SET siguiente_{tipo} = %s WHERE id = %s",
        (numero + 1, empresa_id)
    )
    return candidato


def _insertar_lineas(cursor, documento_id, lineas):
    for linea in lineas:
        limpio_lin = _normalizar("documentos_lineas", dict(linea, documento_id=documento_id))
        campos_lin = list(limpio_lin)
        sql_lin = "INSERT INTO documentos_lineas (" + ", ".join(campos_lin) + ") VALUES (" + ", ".join("%s" for _ in campos_lin) + ")"
        cursor.execute(sql_lin, [limpio_lin[c] for c in campos_lin])


@_traducir_errores
def guardar_documento(cabecera, lineas, registro_id=None, asignar_numero=False):
    """Guarda cabecera + lineas en UNA transaccion (todo o nada). Devuelve el id.

    Los importes NO se fian de lo que llegue: se recalculan aqui con
    calculos.calcular_documento a partir de las lineas y del regimen fiscal de
    la cabecera (exento_iva, recargo_equivalencia, porcentaje_irpf).

    asignar_numero=True reserva el numero de la serie en la misma transaccion
    (documentos nuevos o duplicados). Con False se conserva cabecera["numero"].
    """
    calculo = calcular_documento(
        lineas,
        exento_iva=cabecera.get("exento_iva", 0),
        recargo_equivalencia=cabecera.get("recargo_equivalencia", 0),
        porcentaje_irpf=cabecera.get("porcentaje_irpf", 0),
    )
    exento = bool(int(cabecera.get("exento_iva") or 0))
    cabecera = dict(
        cabecera,
        exento_iva=1 if exento else 0,
        # exento anula el recargo: se guarda coherente con lo calculado
        recargo_equivalencia=0 if exento else (1 if int(cabecera.get("recargo_equivalencia") or 0) else 0),
        base_imponible=calculo["base_imponible"],
        total_iva=calculo["total_iva"],
        total_recargo=calculo["total_recargo"],
        porcentaje_irpf=calculo["porcentaje_irpf"],
        total_retencion=calculo["total_retencion"],
        total=calculo["total"],
    )
    lineas = [dict(linea, subtotal=linea["importe"]) for linea in calculo["lineas"]]

    tipo = str(cabecera.get("tipo") or "").strip().lower()
    if asignar_numero:
        if tipo not in TIPOS_DOCUMENTO:
            raise ValueError("Tipo de documento no valido: " + tipo)
        if not cabecera.get("empresa_id"):
            raise ValueError("Selecciona una empresa emisora.")

    limpio_cab = _normalizar("documentos", cabecera)
    if registro_id:
        limpio_cab.pop("fecha_creacion", None)   # editar no cambia la fecha de alta
    elif not limpio_cab.get("fecha_creacion"):
        limpio_cab["fecha_creacion"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    con = conectar()
    cursor = con.cursor()
    try:
        con.start_transaction()
        if asignar_numero:
            limpio_cab["numero"] = _reservar_numero(cursor, limpio_cab["empresa_id"], tipo)

        campos_cab = list(limpio_cab)
        if registro_id:
            sql_cab = "UPDATE documentos SET " + ", ".join(c + " = %s" for c in campos_cab) + " WHERE id = %s"
            cursor.execute(sql_cab, [limpio_cab[c] for c in campos_cab] + [registro_id])
            doc_id = registro_id
        else:
            sql_cab = "INSERT INTO documentos (" + ", ".join(campos_cab) + ") VALUES (" + ", ".join("%s" for _ in campos_cab) + ")"
            cursor.execute(sql_cab, [limpio_cab[c] for c in campos_cab])
            doc_id = cursor.lastrowid

        cursor.execute("DELETE FROM documentos_lineas WHERE documento_id = %s", (doc_id,))
        _insertar_lineas(cursor, doc_id, lineas)

        con.commit()
        return doc_id
    except BaseException:
        con.rollback()
        raise
    finally:
        cursor.close()
        con.close()

@_traducir_errores
def obtener_documento_completo(documento_id):
    cabecera = obtener("documentos", documento_id)
    if not cabecera: return None

    con = conectar()
    cursor = con.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT * FROM documentos_lineas WHERE documento_id = %s ORDER BY id",
            (documento_id,)
        )
        lineas = cursor.fetchall()
        resultado = dict(cabecera)
        resultado["lineas"] = [safe_dict(l) for l in lineas]
        return resultado
    finally:
        cursor.close()
        con.close()


@_traducir_errores
def eliminar_documento(documento_id):
    """Borra cabecera y lineas en UNA transaccion (todo o nada)."""
    if not documento_id:
        return False
    con = conectar()
    cursor = con.cursor()
    try:
        cursor.execute("DELETE FROM documentos_lineas WHERE documento_id = %s", (documento_id,))
        cursor.execute("DELETE FROM documentos WHERE id = %s", (documento_id,))
        con.commit()
        return cursor.rowcount > 0
    except Exception:
        con.rollback()
        raise
    finally:
        cursor.close()
        con.close()
