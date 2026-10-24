# Resumen del proyecto: ERP de gestión comercial

## Descripción general

Este proyecto es una aplicación de escritorio para gestionar la parte operativa de una empresa comercial, especialmente enfocada en:

- empresas emisoras
- clientes
- artículos/servicios
- presupuestos
- albaranes
- facturas
- generación de PDF
- envío por correo electrónico
- importación de datos desde CSV de EBP

Está desarrollado en Python con PyQt6 para la interfaz gráfica y SQLite como base de datos local.

## Estructura principal del proyecto

### Archivos clave

- [gestion.py](c:/Users/medin/Desktop/00000000%20TFG%20ERP/gestion.py): pantalla principal y menú del ERP.
- [database.py](c:/Users/medin/Desktop/00000000%20TFG%20ERP/database.py): definición de la base de datos, CRUD y lógica de negocio.
- [ui_common.py](c:/Users/medin/Desktop/00000000%20TFG%20ERP/ui_common.py): utilidades y widgets reutilizables de la interfaz.
- [empresas.py](c:/Users/medin/Desktop/00000000%20TFG%20ERP/empresas.py): gestión de la empresa emisora.
- [clientes.py](c:/Users/medin/Desktop/00000000%20TFG%20ERP/clientes.py): gestión de clientes.
- [articulos.py](c:/Users/medin/Desktop/00000000%20TFG%20ERP/articulos.py): catálogo de artículos y servicios.
- [documentos.py](c:/Users/medin/Desktop/00000000%20TFG%20ERP/documentos.py): gestión de documentos comerciales.
- [impresion.py](c:/Users/medin/Desktop/00000000%20TFG%20ERP/impresion.py): generación de PDF.
- [email_sender.py](c:/Users/medin/Desktop/00000000%20TFG%20ERP/email_sender.py): envío de correos con adjunto PDF.
- [importacion_ebp.py](c:/Users/medin/Desktop/00000000%20TFG%20ERP/importacion_ebp.py): importación masiva de datos desde CSV.
- [gestion.db](c:/Users/medin/Desktop/00000000%20TFG%20ERP/gestion.db): base de datos principal de la aplicación.

## Qué hace cada módulo

### 1. Base de datos

El archivo [database.py](c:/Users/medin/Desktop/00000000%20TFG%20ERP/database.py) define:

- la ruta de la base SQLite
- las tablas principales: empresas, clientes, articulos, documentos, documentos_lineas
- la función init_db() para crear la base y índices
- funciones CRUD:
  - listar
  - obtener
  - insertar
  - actualizar
  - eliminar
  - contar
  - existe_valor
- lógica para numeración automática de facturas, presupuestos y albaranes
- lógica para guardar documentos con sus líneas y recuperarlos completos

### 2. Interfaz general

[gestion.py](c:/Users/medin/Desktop/00000000%20TFG%20ERP/gestion.py) crea la ventana principal con un menú lateral que permite navegar entre secciones:

- Inicio
- Empresas
- Clientes
- Artículos
- Presupuestos
- Albaranes
- Facturas

Además:

- crea copias automáticas de seguridad al cerrar la aplicación
- permite exportar/copiar manualmente la base de datos
- incorpora el botón para importar CSV de EBP

### 3. Empresas

[empresas.py](c:/Users/medin/Desktop/00000000%20TFG%20ERP/empresas.py) permite dar de alta a la empresa emisora. Se gestionan:

- nombre fiscal y comercial
- NIF
- dirección
- serie de numeración
- número siguiente para facturas/presupuestos/albaranes
- logo
- datos bancarios
- pie de documento
- retención IRPF
- empresa predeterminada

### 4. Clientes

[clientes.py](c:/Users/medin/Desktop/00000000%20TFG%20ERP/clientes.py) gestiona clientes con:

- código interno
- nombre
- NIF
- contacto
- dirección
- forma de pago
- días de pago
- descuento
- recargo de equivalencia
- exento de IVA
- condiciones comerciales

### 5. Artículos

[articulos.py](c:/Users/medin/Desktop/00000000%20TFG%20ERP/articulos.py) gestiona el catálogo:

- referencia
- descripción
- familia
- tipo (Producto/Servicio)
- unidad
- precio de coste
- precio de venta
- IVA
- control de stock
- stock mínimo

También calcula el precio final con IVA y genera referencias automáticas.

### 6. Documentos comerciales

[documentos.py](c:/Users/medin/Desktop/00000000%20TFG%20ERP/documentos.py) es el núcleo funcional del ERP.

Permite:

- escoger empresa emisora
- escoger cliente
- elegir fecha y vencimiento
- añadir líneas con productos o servicios
- indicar cantidad, precio unitario e IVA
- calcular base imponible, IVA y total
- guardar el documento
- editar o borrar documentos
- buscar por texto
- exportar listado a CSV
- generar PDF
- enviar por email

### 7. Generación de PDF

[impresion.py](c:/Users/medin/Desktop/00000000%20TFG%20ERP/impresion.py) genera documentos en formato PDF con:

- cabecera de la empresa
- datos del cliente
- líneas del documento
- totales
- marca de agua para borradores o documentos no pagados
- formato tipo factura/presupuesto/albarán

### 8. Envío de correos

[email_sender.py](c:/Users/medin/Desktop/00000000%20TFG%20ERP/email_sender.py) envía el documento en PDF por correo, apoyándose en SMTP del servidor del remitente.

### 9. Importación desde EBP

[importacion_ebp.py](c:/Users/medin/Desktop/00000000%20TFG%20ERP/importacion_ebp.py) permite importar CSVs exportados desde EBP y transformarlos en registros reales de la base de datos. Realiza:

- detección de codificación
- detección del separador CSV
- detección automática de columnas por nombre
- normalización de texto y números
- mapeo de clientes, artículos, documentos y líneas
- copia de seguridad antes de importar
- importación idempotente (sin duplicados) usando identificadores

## Base de datos real

La aplicación no depende de archivos CSV como fuente principal. La fuente viva es la base SQLite:

- [gestion.db](c:/Users/medin/Desktop/00000000%20TFG%20ERP/gestion.db)

Los CSVs que hay en la carpeta, como [Customer.csv](c:/Users/medin/Desktop/00000000%20TFG%20ERP/Customer.csv), pueden ser archivos de exportación o fuentes de importación externa, pero la app usa la base de datos para operar y mostrar datos.

## Resumen funcional

El programa funciona como un ERP local básico para pequeñas empresas que necesitan:

- controlar su información fiscal
- generar documentos comerciales
- automatizar numeración
- mantener catálogo de productos
- calcular importe con IVA
- emitir documentos profesionales en PDF
- enviar documentos por correo
- importar datos masivos desde otro sistema

## Conclusión

Este proyecto es una aplicación de gestión comercial completa, pero orientada a un entorno local y simplificado. Tiene una estructura clara por módulos y un modelo de datos robusto basado en SQLite, con una interfaz gráfica en PyQt6 y procesos de negocio bien definidos para gestión de clientes, artículos y documentos.
