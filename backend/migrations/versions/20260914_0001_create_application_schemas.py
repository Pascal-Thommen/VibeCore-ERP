"""Create isolated Core and Shell PostgreSQL schemas.

Revision ID: 20260914_0001
Revises:
Create Date: 2026-09-14
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260914_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Prepare the two schema boundaries; no business tables exist yet."""
    op.execute("CREATE SCHEMA IF NOT EXISTS core")
    op.execute("CREATE SCHEMA IF NOT EXISTS shell")


def downgrade() -> None:
    """Remove only the empty bootstrap schemas in reverse dependency order."""
    op.execute("DROP SCHEMA IF EXISTS shell")
    op.execute("DROP SCHEMA IF EXISTS core")
