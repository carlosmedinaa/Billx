#!/usr/bin/env bash
# Copia diaria de billx_db EN EL SERVIDOR (mini PC). Programar con cron, p. ej.:
#   30 2 * * *  /opt/billx/backup_servidor.sh >> /var/log/billx_backup.log 2>&1
#
# Credenciales: crea ~/.billx_backup.cnf (chmod 600) con:
#   [client]
#   user=billx_admin
#   password=TU_CLAVE
set -euo pipefail

DESTINO="${BILLX_BACKUP_DIR:-/var/backups/billx}"
RETENCION_DIAS="${BILLX_BACKUP_DIAS:-30}"
BASE="${BILLX_DB_NAME:-billx_db}"
FICHERO="$DESTINO/billx_$(date +%Y%m%d_%H%M%S).sql.gz"

mkdir -p "$DESTINO"
mysqldump --defaults-extra-file="$HOME/.billx_backup.cnf" \
          --single-transaction --default-character-set=utf8mb4 "$BASE" | gzip > "$FICHERO"

# Una copia vacia o diminuta es un fallo, no un exito
if [ "$(stat -c%s "$FICHERO")" -lt 1024 ]; then
  echo "ERROR: copia sospechosamente pequena: $FICHERO" >&2
  rm -f "$FICHERO"
  exit 1
fi

find "$DESTINO" -name 'billx_*.sql.gz' -mtime +"$RETENCION_DIAS" -delete
echo "$(date -Is) OK $FICHERO"
