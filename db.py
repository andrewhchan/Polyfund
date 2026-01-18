import os
from functools import lru_cache
from typing import Optional

from supabase import Client, create_client

@lru_cache()
def get_supabase() -> Optional[Client]:
    """
    Return a Supabase client if SUPABASE_URL and a server key are set.
    Prefers SUPABASE_SERVICE_ROLE_KEY, falls back to SUPABASE_SECRET_KEY or SUPABASE_KEY.
    """
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SECRET_KEY")
    
    print(f"Supabase URL: {url}, Key present: {key is not None}")
    if not url or not key:
        return None
    return create_client(url, key)
