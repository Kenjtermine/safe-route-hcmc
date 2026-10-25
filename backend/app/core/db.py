import psycopg

from app.core.config import settings


def get_connection() -> psycopg.Connection:
    """Kết nối đồng bộ tới PostgreSQL.

    Nếu nhóm chọn async (asyncpg / SQLAlchemy async) thì thay file này;
    các module khác chỉ nên import từ đây.
    """
    return psycopg.connect(settings.database_url)
