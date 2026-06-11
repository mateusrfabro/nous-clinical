#!/bin/bash
set -e

echo "[nous] Aguardando banco de dados..."
sleep 3

echo "[nous] Aplicando migrations..."
flask db upgrade

if [ "$RUN_SEED" = "true" ]; then
    echo "[nous] Rodando seed inicial..."
    python scripts/seed.py
    echo "[nous] Seed concluido. Mude RUN_SEED=false no .env para nao repetir."
else
    echo "[nous] Seed pulado (RUN_SEED != true)."
fi

# Default seguro p/ container pequeno. NAO usar 2*cpu+1: em PaaS o cpu_count()
# reflete o host inteiro e sobe workers demais -> OOM. Ajuste via WEB_WORKERS.
WORKERS=${WEB_WORKERS:-2}

echo "[nous] Iniciando gunicorn com $WORKERS workers..."
# --preload: carrega o app uma vez no master e faz fork -> workers compartilham
#   a memoria base (copy-on-write). Essencial em instancia pequena (512MB).
# Logs no stdout/stderr (-) para aparecerem no painel do provedor (Render etc.).
exec gunicorn \
    --bind 0.0.0.0:${PORT:-5050} \
    --workers "$WORKERS" \
    --preload \
    --timeout 120 \
    --max-requests 1000 \
    --max-requests-jitter 100 \
    --access-logfile - \
    --error-logfile - \
    --capture-output \
    run:app
