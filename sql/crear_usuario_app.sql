-- Ejecutar UNA vez en el servidor MySQL, conectado como root (o admin).
-- 1) Cambia 'CLAVE_NUEVA_LARGA' por una contrasena nueva y unica (>= 16 caracteres).
-- 2) Cambia '100.%' si quieres restringir a IPs concretas de tu tailnet
--    (las IPs de Tailscale son 100.64.0.0/10; '100.%' es un compromiso comodo).

-- Usuario de la APLICACION: solo datos, nada de DDL.
CREATE USER IF NOT EXISTS 'billx_app'@'100.%' IDENTIFIED BY 'CLAVE_NUEVA_LARGA';
GRANT SELECT, INSERT, UPDATE, DELETE ON billx_db.* TO 'billx_app'@'100.%';

-- Usuario ADMIN para init_esquema.py / migraciones (usalo solo cuando haga falta).
CREATE USER IF NOT EXISTS 'billx_admin'@'100.%' IDENTIFIED BY 'OTRA_CLAVE_LARGA_DISTINTA';
GRANT ALL PRIVILEGES ON billx_db.* TO 'billx_admin'@'100.%';

-- Si la copia manual con mysqldump desde el cliente da error de permisos en MySQL 8,
-- añade tambien:   GRANT LOCK TABLES ON billx_db.* TO 'billx_app'@'100.%';

-- 3) La contrasena antigua ya esta comprometida (esta en el historial de git):
ALTER USER 'root'@'localhost' IDENTIFIED BY 'OTRA_CLAVE_ROOT_LARGA';
-- Y si root tiene acceso remoto, eliminalo:
-- DROP USER IF EXISTS 'root'@'%';

FLUSH PRIVILEGES;
