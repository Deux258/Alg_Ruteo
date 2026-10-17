"""Conexiones sin credenciales escritas en el repositorio."""
import os
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from core.contracts import ROOT, sha256


def connect():
    dsn = os.environ.get("DATABASE_URL")
    kwargs = dict(autocommit=True, row_factory=dict_row, connect_timeout=10)
    if dsn:
        return psycopg.connect(dsn, **kwargs)
    return psycopg.connect(host=os.getenv("DB_HOST", "db"), port=int(os.getenv("DB_PORT", "5432")),
                          dbname=os.getenv("DB_NAME", "ruteo"), user=os.getenv("DB_USER", "postgres"),
                          password=os.environ["DB_PASSWORD"], **kwargs)


def apply_migrations(conn, directory):
    """Migraciones adicionales sin BEGIN/COMMIT, ordenadas y con checksum."""
    from pglast import parse_sql, ast
    versions=set()
    for path in sorted(directory.glob('[0-9][0-9][0-9]_*.sql')):
        version=int(path.name.split('_',1)[0])
        if version<2 or version in versions:
            raise ValueError('Numeración de migraciones inválida o duplicada')
        versions.add(version)
        checksum=sha256(path)
        existing=conn.execute('SELECT checksum FROM routing.schema_migrations WHERE version=%s',(version,)).fetchone()
        if existing:
            if existing['checksum']!=checksum:
                raise ValueError(f'Migración {version} aplicada cambió; crear una nueva versión')
            continue
        source=path.read_text()
        if any(isinstance(x.stmt,ast.TransactionStmt) for x in parse_sql(source)):
            raise ValueError('Migraciones adicionales no deben incluir BEGIN/COMMIT/ROLLBACK')
        with conn.transaction():
            conn.execute(source,prepare=False)
            conn.execute('INSERT INTO routing.schema_migrations(version,checksum) VALUES(%s,%s)',(version,checksum))


def apply_schema(conn):
    path = ROOT / "BD/crear_bd.sql"
    checksum = sha256(path)
    conn.execute('SELECT pg_advisory_lock(74260101)')
    try:
        old=None
        if conn.execute("SELECT to_regclass('routing.schema_migrations') AS t").fetchone()["t"]:
            old = conn.execute("SELECT checksum FROM routing.schema_migrations WHERE version=1").fetchone()
            if old and old["checksum"] not in (None, checksum):
                raise ValueError("DDL versión 1 cambió: agregar una migración explícita; no reescribir una versión aplicada")
        if not old or old['checksum'] is None:
            conn.execute(path.read_text(), prepare=False)
            conn.execute("UPDATE routing.schema_migrations SET checksum=%s WHERE version=1 AND (checksum IS NULL OR checksum=%s)",
                         (checksum, checksum))
        apply_migrations(conn,ROOT/'BD/migraciones')
    finally:
        conn.execute('SELECT pg_advisory_unlock(74260101)')
    conn.execute("SET TIME ZONE 'UTC'")
    return conn.execute("SELECT version() AS postgres,postgis_full_version() AS postgis,pgr_version() AS pgrouting").fetchone()


def create_reader(conn):
    password = os.environ.get("WEB_DB_PASSWORD")
    if not password:
        return
    with conn.transaction():
        if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname='routing_web'").fetchone():
            conn.execute("CREATE ROLE routing_web LOGIN")
        conn.execute(sql.SQL("ALTER ROLE routing_web PASSWORD {}").format(sql.Literal(password)))
        conn.execute("ALTER ROLE routing_web SET default_transaction_read_only=on")
        conn.execute("ALTER ROLE routing_web SET statement_timeout='5s'")
        conn.execute("GRANT USAGE ON SCHEMA routing,public TO routing_web")
        conn.execute("GRANT SELECT ON ALL TABLES IN SCHEMA routing TO routing_web")
        conn.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA routing GRANT SELECT ON TABLES TO routing_web")
        dbname = conn.execute("SELECT current_database() AS name").fetchone()["name"]
        conn.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO routing_web").format(sql.Identifier(dbname)))
