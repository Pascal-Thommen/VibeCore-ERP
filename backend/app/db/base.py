from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

CORE_SCHEMA = "core"
SHELL_SCHEMA = "shell"

metadata = MetaData(
    naming_convention={
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
)


class Base(DeclarativeBase):
    """Shared SQLAlchemy base; each model must explicitly choose `core` or `shell`."""

    metadata = metadata
