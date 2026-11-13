"""Alembic runs inside app.db.upgrade, which passes an open connection."""
from alembic import context

from app.db import metadata

connection = context.config.attributes['connection']
context.configure(connection=connection, target_metadata=metadata, render_as_batch=True)
with context.begin_transaction():
    context.run_migrations()
