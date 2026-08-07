import time
import json
from typing import Any, Optional, Dict

class InMemoryFallbackRedis:
    """Fallback in-memory key-value cache if Redis server is offline."""
    def __init__(self):
        self._store: Dict[str, Dict[str, Any]] = {}

    def set(self, key: str, value: str, ex: Optional[int] = None):
        expiry = time.time() + ex if ex else None
        self._store[key] = {"value": value, "expiry": expiry}

    def get(self, key: str) -> Optional[str]:
        if key not in self._store:
            return None
        item = self._store[key]
        if item["expiry"] and time.time() > item["expiry"]:
            del self._store[key]
            return None
        return item["value"]

    def delete(self, key: str):
        if key in self._store:
            del self._store[key]

class RedisMemoryStore:
    """Short-term session memory & response cache manager."""
    def __init__(self, host: str = "localhost", port: int = 6379):
        self.is_connected = False
        self.client = None
        
        try:
            import redis
            r = redis.Redis(host=host, port=port, socket_timeout=0.2, socket_connect_timeout=0.2)
            r.ping()
            self.client = r
            self.is_connected = True
            print("[Memory] Redis connected successfully!")
        except Exception as e:
            print(f"[Memory] Redis server offline. Using in-memory short-term cache fallback.")
            self.client = InMemoryFallbackRedis()

    def set_session_data(self, session_id: str, data: dict, ttl_seconds: int = 3600):
        try:
            self.client.set(f"session:{session_id}", json.dumps(data), ex=ttl_seconds)
        except Exception as e:
            print(f"[Redis Error] set_session_data failed: {e}")

    def get_session_data(self, session_id: str) -> Optional[dict]:
        try:
            raw = self.client.get(f"session:{session_id}")
            if raw:
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                return json.loads(raw)
        except Exception as e:
            print(f"[Redis Error] get_session_data failed: {e}")
        return None

    def cache_response(self, prompt: str, response: str, ttl_seconds: int = 1800):
        try:
            key = f"cache:{hash(prompt)}"
            self.client.set(key, response, ex=ttl_seconds)
        except Exception as e:
            print(f"[Redis Error] cache_response failed: {e}")

    def get_cached_response(self, prompt: str) -> Optional[str]:
        try:
            key = f"cache:{hash(prompt)}"
            res = self.client.get(key)
            if res and isinstance(res, bytes):
                return res.decode("utf-8")
            return res
        except Exception as e:
            print(f"[Redis Error] get_cached_response failed: {e}")
        return None
