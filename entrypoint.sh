#!/bin/bash
set -e

echo "[medsaas] Aguardando banco de dados..."
sleep 3

echo "[medsaas] Aplicando migrations..."
flask db upgrade

if [ "$RUN_SEED" = "true" ]; then
    echo "[medsaas] Rodando seed inicial..."
    python scripts/seed.py
    echo "[medsaas] Seed concluido. Mude RUN_SEED=false no .env para nao repetir."
else
    echo "[medsaas] Seed pulado (RUN_SEED != true)."
fi

WORKERS=${WEB_WORKERS:-$(python -c "import os; print(2 * os.cpu_count() + 1)" 2>/dev/null || echo 3)}

echo "[medsaas] Iniciando gunicorn com $WORKERS workers..."
exec gunicorn \
    --bind 0.0.0.0:${PORT:-5050} \
    --workers "$WORKERS" \
    --timeout 120 \
    --max-requests 1000 \
    --max-requests-jitter 100 \
    --access-logfile /var/log/medsaas-access.log \
    --error-logfile /var/log/medsaas-error.log \
    --capture-output \
    run:app
