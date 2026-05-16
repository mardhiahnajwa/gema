#!/bin/bash
set -e

echo "============================================"
echo "  Gema Worker - Starting up"
echo "============================================"

echo "[1/2] Waiting for Redis..."
until python -c "
import redis, os, sys
try:
    r = redis.from_url(os.environ.get('REDIS_URL', 'redis://redis:6379/0'))
    r.ping()
    sys.exit(0)
except Exception:
    sys.exit(1)
" 2>/dev/null; do
    echo "  Redis not ready - retrying in 2s..."
    sleep 2
done
echo "  Redis is ready!"

echo "[2/2] Waiting for PostgreSQL..."
until python -c "
import psycopg2, os, sys
try:
    conn = psycopg2.connect(os.environ.get('SYNC_DATABASE_URL', ''))
    conn.close()
    sys.exit(0)
except Exception:
    sys.exit(1)
" 2>/dev/null; do
    echo "  PostgreSQL not ready - retrying in 2s..."
    sleep 2
done
echo "  PostgreSQL is ready!"

echo "============================================"
echo "  Starting Celery worker..."
echo "============================================"
exec "$@"
