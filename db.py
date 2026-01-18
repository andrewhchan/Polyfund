import os
from functools import lru_cache
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


@lru_cache()
def get_engine() -> Optional[Engine]:
    """
    Return a SQLAlchemy engine if DATABASE_URL (or SUPABASE_DB_URL) is set.
    Uses future engine for 2.0-style.
    """
    url = os.getenv("DATABASE_URL") or os.getenv("SUPABASE_DB_URL")
    if not url:
        return None
    return create_engine(url, future=True, pool_pre_ping=True)
