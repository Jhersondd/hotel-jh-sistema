import httpx
import logging
from config import settings

logger = logging.getLogger("hotel_bot.evolution")

class EvolutionService:
    def __init__(self):
        self.base_url = settings.EVOLUTION_URL.rstrip("/")
        self.instance = settings.EVOLUTION_INSTANCE_NAME
        self.api_key = settings.EVOLUTION_API_KEY

    @property
    def headers(self):
        return {
            "apikey": self.api_key,
            "Content-Type": "application/json"
        }

    async def send_text(self, to_phone: str, message: str) -> bool:
        """
        Envía un mensaje de texto por WhatsApp al número especificado.
        """
        clean_phone = to_phone.replace("+", "").replace(" ", "").strip()
        url = f"{self.base_url}/message/sendText/{self.instance}"
        payload = {
            "number": clean_phone,
            "text": message,
            "delay": 1200,
            "linkPreview": False
        }

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.post(url, json=payload, headers=self.headers)
                if resp.status_code in [200, 201]:
                    logger.info(f"Mensaje enviado exitosamente a {clean_phone}")
                    return True
                else:
                    logger.error(f"Error enviando mensaje Evolution API ({resp.status_code}): {resp.text}")
                    return False
        except Exception as e:
            logger.error(f"Excepción enviando mensaje a {clean_phone}: {e}")
            return False

    async def check_instance_status(self) -> dict:
        url = f"{self.base_url}/instance/connectionState/{self.instance}"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url, headers=self.headers)
                if resp.status_code == 200:
                    return resp.json()
                return {"state": "disconnected", "error": resp.text}
        except Exception as e:
            return {"state": "error", "error": str(e)}

evolution_service = EvolutionService()
