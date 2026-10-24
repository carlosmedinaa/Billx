# Explicación detallada del proyecto

## 1. Qué es este proyecto

Este proyecto es una aplicación de escritorio para gestionar una empresa comercial desde una sola herramienta. Su objetivo principal es manejar:

- la empresa emisora
- los clientes
- los artículos
- los documentos comerciales
- la numeración y los totales
- la emisión de facturas y presupuestos
- la exportación a PDF y el envío por correo

La app tiene una interfaz gráfica con PyQt6 y usa SQLite para almacenar todos los datos de forma local.

## 2. Cómo está organizado

La organización es bastante clara por capas:

### Capa de datos

[database.py](c:/Users/medin/Desktop/00000000%20TFG%20ERP/database.py)

Es el núcleo de la aplicación. Aquí se define:

- la ruta de la base de datos
- la estructura de cada tabla
- creación automática de tablas e índices
- acceso a datos con funciones reutilizables
- validaciones mínimas del negocio

El sistema usa estas tablas:

- empresas
- clientes
- articulos
- documentos
- documentos_lineas

Estas tablas permiten guardar toda la información operativa del negocio.

### Capa visual y reutilizable

[ui_common.py](c:/Users/medin/Desktop/00000000%20TFG%20ERP/ui_common.py)

Este archivo implementa widgets comunes que se reutilizan en todas las pantallas:

- campos de texto
- campos numéricos
- checkboxes
- combos
- botones estándar
- paneles de lista
- diálogo base para fichas

Es la capa “de soporte” que hace que el resto de pantallas queden más limpias.

### Capa funcional por módulo

Las pantallas más importantes son:

- [empresas.py](c:/Users/medin/Desktop/00000000%20TFG%20ERP/empresas.py)
- [clientes.py](c:/Users/medin/Desktop/00000000%20TFG%20ERP/clientes.py)
- [articulos.py](c:/Users/medin/Desktop/00000000%20TFG%20ERP/articulos.py)
- [documentos.py](c:/Users/medin/Desktop/00000000%20TFG%20ERP/documentos.py)

Cada uno gestiona una parte del negocio y suele tener una clase principal que hereda de PanelLista o DialogoFicha.

### Capa de negocio y presentación

- [impresion.py](c:/Users/medin/Desktop/00000000%20TFG%20ERP/impresion.py): genera documentos en PDF.
- [email_sender.py](c:/Users/medin/Desktop/00000000%20TFG%20ERP/email_sender.py): envía los documentos por correo.
- [importacion_ebp.py](c:/Users/medin/Desktop/00000000%20TFG%20ERP/importacion_ebp.py): importa datos masivos desde CSV.

## 3. Cómo funciona la base de datos

La base se crea con SQLite y se llama [gestion.db](c:/Users/medin/Desktop/00000000%20TFG%20ERP/gestion.db).

### Tabla empresas

Guarda la empresa emisora del documento:

- nombre
- NIF
- dirección
- ciudad
- provincia
- email
- web
- logo
- serie por tipo de documento
- siguiente número para facturas, presupuestos y albaranes
- pie de documento
- empresa predeterminada

Esto permite que la aplicación se comporte como una empresa que emite presupuestos y facturas en nombre propio.

### Tabla clientes

Guarda todos los clientes fiscales:

- código
- nombre
- NIF
- dirección
- forma de pago
- días de pago
- descuento
- preferencias fiscales
- datos de contacto

La app usa esta tabla para asociar un cliente a un documento.

### Tabla articulos

Guarda los productos o servicios que se venden:

- referencia
- descripción
- tipo
- familia
- unidad
- precio de coste
- precio de venta
- IVA
- stock

Esto es lo que luego se usa para rellenar líneas del documento.

### Tabla documentos

Es la cabecera del documento comercial:

- tipo: factura / presupuesto / albarán
- número
- fecha
- empresa_id
- cliente_id
- base imponible
- total IVA
- total
- forma de pago
- vencimiento
- estado

### Tabla documentos_lineas

Guarda cada línea de cada documento:

- documento_id
- referencia del artículo
- descripción
- cantidad
- precio unitario
- IVA aplicado
- subtotal

Así el mismo documento puede tener varias líneas, pudiendo variar cantidad, IVA y precio.

## 4. Cómo se usan las pantallas principales

### 4.1 Pantalla principal

[gestion.py](c:/Users/medin/Desktop/00000000%20TFG%20ERP/gestion.py) crea la ventana principal y cambia entre módulos con un menú lateral.

En el inicio se muestran contadores:

- total de empresas
- clientes activos
- artículos activos
- artículos bajo stock mínimo
- empresa predeterminada

### 4.2 Empresas

En la pantalla de empresas se puede:

- crear una nueva empresa
- editar datos
- seleccionar logo
- definir series numéricas
- marcar una empresa como predeterminada

### 4.3 Clientes

En la pantalla de clientes se puede:

- crear clientes
- asignar forma de pago
- poner NIF, dirección y datos de contacto
- decir si están activos
- gestionar condiciones de descuento

### 4.4 Artículos

En la pantalla de artículos se puede:

- crear artículos y servicios
- poner precio de venta y coste
- asignar familia y unidad
- gestionar IVA
- controlar stock

### 4.5 Documentos

En documentos se crea la parte operativa del negocio:

- se selecciona empresa
- se busca un cliente
- se rellena fecha y vencimiento
- se añaden líneas con artículos
- se calcula automáticamente bases e impuestos
- se guarda el documento

Esto convierte el ERP en una herramienta real para emitir compras, presupuestos y facturas.

## 5. Lógica de numeración

La base de datos tiene la idea de que cada empresa tiene una serie y un número siguiente para cada tipo de documento.

En [database.py](c:/Users/medin/Desktop/00000000%20TFG%20ERP/database.py) existen funciones como:

- formatear_numero()
- consumir_numero()
- previsualizar_numero()

Esto permite que cada factura o presupuesto tenga un número automático con formato como:

- FAC-0001
- PRE-0005
- ALB-0022

Eso es muy útil para no tener que escribir números manualmente.

## 6. Cálculo de totales

En [documentos.py](c:/Users/medin/Desktop/00000000%20TFG%20ERP/documentos.py) se recalculan los totales según cada línea:

- cantidad * precio unitario = subtotal por línea
- subtotal * IVA / 100 = cuota de IVA
- base total + IVA total = total final

La aplicación hace estos cálculos al instante y los muestra en pantalla.

## 7. Cómo se generan PDFs

[impresion.py](c:/Users/medin/Desktop/00000000%20TFG%20ERP/impresion.py) usa reportlab para dibujar la factura, el presupuesto o el albarán.

Genera una hoja con:

- nombre de la empresa
- dirección y datos fiscales
- cliente
- número
- fecha
- vencimiento
- líneas con descripción, cantidad, precio y IVA
- totales finales
- marca de agua para borradores o documentos no abonados

Esto convierte los documentos de la base de datos en documentos imprimibles y profesionales.

## 8. Envío de documentos por correo

[email_sender.py](c:/Users/medin/Desktop/00000000%20TFG%20ERP/email_sender.py) es un módulo distinto que prepara correos con SMTP para enviar el PDF generado al cliente.

Funciona así:

- toma el email del remitente
- toma el email del cliente
- prepara asunto y cuerpo del mensaje
- adjunta el PDF
- envía con SMTP

La app además incluye una ventana de correo para preparar texto y contraseña del remitente.

## 9. Importación de datos desde EBP

[importacion_ebp.py](c:/Users/medin/Desktop/00000000%20TFG%20ERP/importacion_ebp.py) es un módulo específico para migrar información desde un sistema externo.

Su función es leer CSVs exportados de EBP y mapear sus columnas para que se guarden en la misma estructura del ERP.

El flujo es:

- detecta la codificación del CSV
- detecta el separador
- identifica columnas como nombre, NIF, cliente, número, importe, IVA, etc.
- normaliza los valores
- crea o actualiza registros en la base de datos local
- hace una copia de seguridad antes de importar
- evita duplicados con identificadores o comprobaciones

## 10. Qué tipo de proyecto es

Este no es un proyecto web ni un backend API. Es un ERP de escritorio local. Tiene las siguientes características:

- interfaz gráfica con PyQt6
- almacenamiento local en SQLite
- lógica de negocio propia
- gestión documental
- automatización de numeración
- exportación profesional en PDF
- importación de datos externos

## 11. En resumen práctico

Si pensáramos en la vida real, el proyecto funciona así:

1. La empresa se da de alta.
2. Los clientes se registran con sus datos fiscales y condiciones de pago.
3. Los productos o servicios se registran en el catálogo.
4. El usuario genera un presupuesto, un albarán o una factura.
5. El sistema calcula precios e IVA automáticamente.
6. El documento se guarda en la base de datos.
7. Se puede imprimir, ver en PDF o mandar por correo.
8. Si se importa información desde EBP, la app la transforma para que encaje en esta base.

## 12. Conclusión

El proyecto es un ERP de gestión comercial funcional, orientado a un entorno local y pequeño/mediano. Tiene una estructura clara por módulos, usa SQLite como base de trabajo, automatiza procesos repetitivos y está pensado para gestionar todo lo que normalmente hace una empresa en su ciclo comercial: clientes, catálogo, facturación y documento final.

En otras palabras, es un sistema completo para gestionar la parte administrativa y comercial de una empresa sin depender de servicios externos ni de un servidor central.
