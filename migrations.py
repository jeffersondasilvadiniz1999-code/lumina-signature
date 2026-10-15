"""Append-only, transactional schema upgrades. Never seed demo products."""
import hashlib
from pathlib import Path


def migrate(connection, schema):
    with connection.transaction():
        connection.execute('SELECT pg_advisory_xact_lock(681293771)')
        connection.execute('CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, checksum TEXT NOT NULL, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())')
        for statement in schema.split(';'):
            if statement.strip(): connection.execute(statement)
        for path in sorted(Path(__file__).parent.glob('[0-9][0-9][0-9]_*.sql')):
            version=int(path.name.split('_')[0]);sql=path.read_text()
            checksum=hashlib.sha256(sql.encode()).hexdigest()
            previous=connection.execute('SELECT checksum FROM schema_migrations WHERE version=%s',(version,)).fetchone()
            if previous:
                if previous['checksum']!=checksum:raise RuntimeError('Migração já aplicada foi alterada. Crie nova migração.')
                continue
            connection.execute(sql)
            connection.execute('INSERT INTO schema_migrations(version,checksum) VALUES(%s,%s)',(version,checksum))
