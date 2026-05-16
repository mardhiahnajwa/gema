#!/bin/bash
set -e

echo "============================================"
echo "  Gema API - Starting up"
echo "============================================"

# Wait for PostgreSQL
echo "[1/3] Waiting for PostgreSQL..."
until python -c "
import psycopg2, os, sys
url = os.environ.get('SYNC_DATABASE_URL', '')
try:
    conn = psycopg2.connect(url)
    conn.close()
    sys.exit(0)
except Exception as e:
    sys.exit(1)
" 2>/dev/null; do
    echo "  PostgreSQL not ready - retrying in 2s..."
    sleep 2
done
echo "  PostgreSQL is ready!"

# Wait for Redis
echo "[2/3] Waiting for Redis..."
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

# Initialize database tables
echo "[3/3] Initializing database..."
python -c "
import asyncio
from app.database import create_tables
asyncio.run(create_tables())
print('  Database initialized!')
"

echo "============================================"
echo "  Starting Gema API server..."
echo "============================================"
exec "$@"
