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

WORKERS=${WEB_WORKERS:-$(python -c "import os; print(2 * os.cpu_count() + 1)" 2>/dev/null || echo 3)}

echo "[nous] Iniciando gunicorn com $WORKERS workers..."
exec gunicorn \
    --bind 0.0.0.0:${PORT:-5050} \
    --workers "$WORKERS" \
    --timeout 120 \
    --max-requests 1000 \
    --max-requests-jitter 100 \
    --access-logfile /var/log/nous-access.log \
    --error-logfile /var/log/nous-error.log \
    --capture-output \
    run:app
