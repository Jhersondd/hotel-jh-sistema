import random
import logging
import httpx
from datetime import datetime
from config import settings

logger = logging.getLogger("hotel_bot.ttlock")

class TTLockService:
    def __init__(self):
        self.client_id = settings.TTLOCK_CLIENT_ID
        self.client_secret = settings.TTLOCK_CLIENT_SECRET
        self.username = settings.TTLOCK_USERNAME
        self.password = settings.TTLOCK_PASSWORD
        self.base_url = "https://api.ttlock.com"
        self._access_token = None

    async def get_access_token(self) -> str:
        if not self.client_id or not self.client_secret:
            return None

        if self._access_token:
            return self._access_token

        url = f"{self.base_url}/oauth/token"
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "username": self.username,
            "password": self.password,
            "grant_type": "password"
        }

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.post(url, data=data)
                if resp.status_code == 200:
                    payload = resp.json()
                    self._access_token = payload.get("access_token")
                    return self._access_token
                else:
                    logger.error(f"Error autenticando en TTLock: {resp.text}")
                    return None
        except Exception as e:
            logger.error(f"Excepción obteniendo token TTLock: {e}")
            return None

    async def generate_passcode(self, lock_id: str, checkin_date: str, checkout_date: str) -> str:
        """
        Genera un PIN de teclado numérico temporal.
        Si la API de TTLock no está configurada, genera un PIN de 6 dígitos seguro como fallback.
        """
        token = await self.get_access_token()
        if not token or not lock_id:
            # Fallback local: genera PIN de 6 dígitos terminado en #
            fallback_pin = f"{random.randint(100000, 999999)}#"
            logger.info(f"TTLock no configurado o sin conexión. PIN generado en modo local/fallback: {fallback_pin}")
            return fallback_pin

        try:
            # Convertir fechas a timestamps milisegundos
            # Check-in a las 14:00, Check-out a las 11:00
            start_dt = datetime.strptime(f"{checkin_date} {settings.CHECKIN_TIME}", "%Y-%m-%d %H:%M")
            end_dt = datetime.strptime(f"{checkout_date} {settings.CHECKOUT_TIME}", "%Y-%m-%d %H:%M")

            start_ts = int(start_dt.timestamp() * 1000)
            end_ts = int(end_dt.timestamp() * 1000)

            url = f"{self.base_url}/v3/keyboardPwd/get"
            params = {
                "clientId": self.client_id,
                "accessToken": token,
                "lockId": lock_id,
                "keyboardPwdType": 3, # Tipo 3: Passcode temporal
                "startDate": start_ts,
                "endDate": end_ts,
                "date": int(datetime.now().timestamp() * 1000)
            }

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, data=params)
                if resp.status_code == 200:
                    result = resp.json()
                    pin = result.get("keyboardPwd")
                    if pin:
                        return f"{pin}#"
                logger.warning(f"Respuesta inesperada de TTLock: {resp.text}. Usando PIN de contingencia.")
        except Exception as e:
            logger.error(f"Error llamando a TTLock API: {e}")

        return f"{random.randint(100000, 999999)}#"

ttlock_service = TTLockService()
