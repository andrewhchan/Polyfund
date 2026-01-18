import os
from functools import lru_cache
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from supabase import Client, create_client


@lru_cache()
def get_engine() -> Optional[Engine]:
    """
    Return a SQLAlchemy engine if explicitly enabled.
    Disabled by default to favor Supabase client path.
    """
    if os.getenv("DISABLE_DIRECT_DB", "").lower() in ("1", "true", "yes"):
        return None
    url = os.getenv("DATABASE_URL") or os.getenv("SUPABASE_DB_URL")
    if not url:
        return None
    return create_engine(url, future=True, pool_pre_ping=True)


@lru_cache()
def get_supabase() -> Optional[Client]:
    """
    Return a Supabase client if SUPABASE_URL and a server key are set.
    Prefers SUPABASE_SERVICE_ROLE_KEY, falls back to SUPABASE_SECRET_KEY or SUPABASE_KEY.
    """
    url = os.getenv("SUPABASE_URL")
    key = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_SECRET_KEY")
        or os.getenv("SUPABASE_KEY")
    )
    print(f"Supabase URL: {url}, Key present: {key is not None}")
    if not url or not key:
        return None
    return create_client(url, key)
