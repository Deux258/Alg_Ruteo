"""Espera acotada de servicio para GitLab CI; no sustituye validar extensiones."""
import time
from core.db import connect

for attempt in range(60):
    try:
        with connect() as conn:conn.execute('SELECT 1')
        break
    except Exception:
        if attempt==59:raise
        time.sleep(1)
