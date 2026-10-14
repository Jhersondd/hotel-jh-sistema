import json
import logging
import redis
from config import settings

logger = logging.getLogger("hotel_bot.redis")

class RedisService:
    def __init__(self):
        try:
            self.client = redis.from_url(settings.REDIS_URL, decode_responses=True)
            self.client.ping()
            logger.info("Conectado exitosamente a Redis")
        except Exception as e:
            logger.warning(f"No se pudo conectar a Redis: {e}. Usando fallback en memoria.")
            self.client = None
            self._local_memory = {}

    def get_user_session(self, phone: str) -> dict:
        key = f"session:{phone}"
        if self.client:
            data = self.client.get(key)
            return json.loads(data) if data else {"state": "START"}
        return self._local_memory.get(key, {"state": "START"})

    def set_user_session(self, phone: str, data: dict, ttl_seconds: int = 3600):
        key = f"session:{phone}"
        if self.client:
            self.client.setex(key, ttl_seconds, json.dumps(data))
        else:
            self._local_memory[key] = data

    def clear_user_session(self, phone: str):
        key = f"session:{phone}"
        if self.client:
            self.client.delete(key)
        else:
            self._local_memory.pop(key, None)

    def acquire_room_hold(self, room_id: str, checkin: str, checkout: str, phone: str, ttl_seconds: int = 900) -> bool:
        """
        Bloquea temporalmente una habitacion por 15 minutos (900 seg) mientras el cliente paga.
        Retorna True si obtuvo el bloqueo, False si ya estaba retenida.
        """
        lock_key = f"hold:{room_id}:{checkin}:{checkout}"
        if self.client:
            # SETNX atómico
            acquired = self.client.set(lock_key, phone, nx=True, ex=ttl_seconds)
            return bool(acquired)
        else:
            if lock_key in self._local_memory:
                return False
            self._local_memory[lock_key] = phone
            return True

    def release_room_hold(self, room_id: str, checkin: str, checkout: str):
        lock_key = f"hold:{room_id}:{checkin}:{checkout}"
        if self.client:
            self.client.delete(lock_key)
        else:
            self._local_memory.pop(lock_key, None)

    def is_room_held(self, room_id: str, checkin: str, checkout: str, by_phone: str = None) -> bool:
        lock_key = f"hold:{room_id}:{checkin}:{checkout}"
        if self.client:
            holder = self.client.get(lock_key)
            if not holder:
                return False
            if by_phone and holder == by_phone:
                return False # Es retenida por el mismo usuario
            return True
        else:
            holder = self._local_memory.get(lock_key)
            if not holder:
                return False
            if by_phone and holder == by_phone:
                return False
            return True

redis_service = RedisService()
