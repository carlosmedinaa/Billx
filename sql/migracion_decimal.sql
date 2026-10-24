-- =====================================================================
-- Billx: migracion de importes DOUBLE -> DECIMAL y regimen fiscal en documentos
-- =====================================================================
-- Ejecutar con el usuario ADMIN (permisos ALTER), sobre la base correcta:
--
--     mysql -h <servidor> -u billx_admin -p billx_db < sql/migracion_decimal.sql
--
-- ANTES: haz copia de seguridad (scripts/backup_servidor.sh o mysqldump).
-- Se puede volver a ejecutar sin dano: las columnas e indices nuevos solo se
-- crean si faltan y los MODIFY dejan igual una columna que ya es DECIMAL.
--
-- Comprobaciones previas recomendadas (solo lectura). Si alguna devuelve filas,
-- esos valores se REDONDEARAN al convertir; revisalos antes de seguir:
--
--   SELECT id, base_imponible, total_iva, total_recargo, total FROM documentos
--    WHERE base_imponible <> ROUND(base_imponible, 2) OR total_iva <> ROUND(total_iva, 2)
--       OR total_recargo <> ROUND(total_recargo, 2) OR total <> ROUND(total, 2);
--   SELECT id, documento_id, cantidad, precio_unitario, subtotal FROM documentos_lineas
--    WHERE cantidad <> ROUND(cantidad, 3) OR precio_unitario <> ROUND(precio_unitario, 4)
--       OR subtotal <> ROUND(subtotal, 2);
--   SELECT id, precio_coste, precio_venta FROM articulos
--    WHERE precio_coste <> ROUND(precio_coste, 4) OR precio_venta <> ROUND(precio_venta, 4);
--
-- Las tablas deben ser InnoDB (transacciones y SELECT ... FOR UPDATE):
--   SELECT TABLE_NAME, ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE();
-- =====================================================================

-- 1) Columnas de dinero, cantidades y porcentajes a DECIMAL ------------

ALTER TABLE empresas
    MODIFY retencion_irpf DECIMAL(5,2) NOT NULL DEFAULT 0;

ALTER TABLE clientes
    MODIFY descuento DECIMAL(5,2) NOT NULL DEFAULT 0;

ALTER TABLE articulos
    MODIFY precio_coste DECIMAL(12,4) NOT NULL DEFAULT 0,
    MODIFY precio_venta DECIMAL(12,4) NOT NULL DEFAULT 0,
    MODIFY iva          DECIMAL(5,2)  NOT NULL DEFAULT 21,
    MODIFY stock        DECIMAL(12,3) NOT NULL DEFAULT 0,
    MODIFY stock_minimo DECIMAL(12,3) NOT NULL DEFAULT 0;

ALTER TABLE documentos
    MODIFY base_imponible DECIMAL(12,2) NOT NULL DEFAULT 0,
    MODIFY total_iva      DECIMAL(12,2) NOT NULL DEFAULT 0,
    MODIFY total_recargo  DECIMAL(12,2) NOT NULL DEFAULT 0,
    MODIFY total          DECIMAL(12,2) NOT NULL DEFAULT 0;

ALTER TABLE documentos_lineas
    MODIFY cantidad             DECIMAL(12,3) NOT NULL DEFAULT 1,
    MODIFY precio_unitario      DECIMAL(12,4) NOT NULL DEFAULT 0,
    MODIFY porcentaje_descuento DECIMAL(5,2)  NOT NULL DEFAULT 0,
    MODIFY porcentaje_iva       DECIMAL(5,2)  NOT NULL DEFAULT 21,
    MODIFY subtotal             DECIMAL(12,2) NOT NULL DEFAULT 0;

-- 2) Columnas nuevas de documentos (solo si faltan) ---------------------
-- MySQL 8 no admite "ADD COLUMN IF NOT EXISTS": se consulta information_schema.

SET @sql = IF((SELECT COUNT(*) FROM information_schema.COLUMNS
               WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'documentos'
                 AND COLUMN_NAME = 'exento_iva') = 0,
    'ALTER TABLE documentos ADD COLUMN exento_iva TINYINT NOT NULL DEFAULT 0', 'DO 0');
PREPARE paso FROM @sql; EXECUTE paso; DEALLOCATE PREPARE paso;

SET @sql = IF((SELECT COUNT(*) FROM information_schema.COLUMNS
               WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'documentos'
                 AND COLUMN_NAME = 'recargo_equivalencia') = 0,
    'ALTER TABLE documentos ADD COLUMN recargo_equivalencia TINYINT NOT NULL DEFAULT 0', 'DO 0');
PREPARE paso FROM @sql; EXECUTE paso; DEALLOCATE PREPARE paso;

SET @sql = IF((SELECT COUNT(*) FROM information_schema.COLUMNS
               WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'documentos'
                 AND COLUMN_NAME = 'porcentaje_irpf') = 0,
    'ALTER TABLE documentos ADD COLUMN porcentaje_irpf DECIMAL(5,2) NOT NULL DEFAULT 0', 'DO 0');
PREPARE paso FROM @sql; EXECUTE paso; DEALLOCATE PREPARE paso;

SET @sql = IF((SELECT COUNT(*) FROM information_schema.COLUMNS
               WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'documentos'
                 AND COLUMN_NAME = 'total_retencion') = 0,
    'ALTER TABLE documentos ADD COLUMN total_retencion DECIMAL(12,2) NOT NULL DEFAULT 0', 'DO 0');
PREPARE paso FROM @sql; EXECUTE paso; DEALLOCATE PREPARE paso;

-- Los documentos antiguos quedan con exento_iva = 0, recargo = 0 e IRPF = 0,
-- que es exactamente como los calculaba la version anterior del programa.

-- 3) Indices (solo si faltan) -------------------------------------------
-- idx_lineas_documento es importante: sin el, borrar las lineas de un documento
-- bloquea toda la tabla documentos_lineas mientras dura la transaccion.

SET @sql = IF((SELECT COUNT(*) FROM information_schema.STATISTICS
               WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'documentos_lineas'
                 AND INDEX_NAME = 'idx_lineas_documento') = 0,
    'CREATE INDEX idx_lineas_documento ON documentos_lineas (documento_id)', 'DO 0');
PREPARE paso FROM @sql; EXECUTE paso; DEALLOCATE PREPARE paso;

SET @sql = IF((SELECT COUNT(*) FROM information_schema.STATISTICS
               WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'documentos'
                 AND INDEX_NAME = 'idx_documentos_numero') = 0,
    'CREATE INDEX idx_documentos_numero ON documentos (empresa_id, tipo, numero)', 'DO 0');
PREPARE paso FROM @sql; EXECUTE paso; DEALLOCATE PREPARE paso;

-- 4) OPCIONAL: impedir numeros duplicados tambien a nivel de base de datos.
-- Primero comprueba que no hay duplicados historicos (importaciones, version
-- anterior). Si esta consulta no devuelve filas, puedes crear el indice unico:
--
--   SELECT empresa_id, tipo, numero, COUNT(*) FROM documentos
--    GROUP BY empresa_id, tipo, numero HAVING COUNT(*) > 1;
--
--   CREATE UNIQUE INDEX uq_documentos_numero ON documentos (empresa_id, tipo, numero);
