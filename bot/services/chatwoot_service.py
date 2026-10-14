import httpx
import logging
from config import settings

logger = logging.getLogger("hotel_bot.chatwoot")

class ChatwootService:
    def __init__(self):
        self.base_url = settings.CHATWOOT_URL.rstrip("/")
        self.account_id = settings.CHATWOOT_ACCOUNT_ID
        self.token = settings.CHATWOOT_API_TOKEN

    @property
    def headers(self):
        return {
            "api_access_token": self.token,
            "Content-Type": "application/json"
        }

    async def is_agent_active(self, phone: str) -> bool:
        """
        Consulta en Chatwoot si la conversación asociada a este teléfono está atendida por un agente ('open'),
        o si ha sido archivada/marcada con etiquetas de exclusión ('archivado', 'ignorar', 'personal', etc.).
        """
        if not self.token:
            return False

        IGNORED_LABELS = {
            "archivado", "archived", "ignorado", "ignorar", 
            "personal", "no_bot", "blacklist", "bloqueado", 
            "proveedor", "familiar", "atencion_humana", "humano", "agente"
        }

        try:
            clean_phone = phone.replace("+", "").strip()
            async with httpx.AsyncClient(timeout=4.0) as client:
                # 1. Buscar contacto por teléfono
                search_url = f"{self.base_url}/api/v1/accounts/{self.account_id}/contacts/search?q={clean_phone}"
                resp = await client.get(search_url, headers=self.headers)
                if resp.status_code != 200:
                    return False
                
                payload = resp.json()
                contacts = payload.get("payload", [])
                if not contacts:
                    return False
                
                contact = contacts[0]
                contact_id = contact["id"]

                # Verificar atributos personalizados del contacto
                custom_attrs = contact.get("custom_attributes") or {}
                if any(custom_attrs.get(k) in [True, "true", "True", 1] for k in ["archivado", "ignorar", "no_bot", "personal"]):
                    logger.info(f"Contacto {phone} tiene atributo de ignorar en Chatwoot. Bot silenciado.")
                    return True

                # 2. Obtener conversaciones del contacto
                conv_url = f"{self.base_url}/api/v1/accounts/{self.account_id}/contacts/{contact_id}/conversations"
                conv_resp = await client.get(conv_url, headers=self.headers)
                if conv_resp.status_code != 200:
                    return False
                
                conv_data = conv_resp.json().get("payload", [])
                for conv in conv_data:
                    # Si hay un agente humano asignado explícitamente a la conversación
                    if conv.get("assignee_id") is not None:
                        logger.info(f"Conversación con {phone} está asignada a un agente humano (#{conv.get('assignee_id')}). Bot silenciado.")
                        return True

                    # Si el estado es snoozed (pospuesto)
                    if conv.get("status") == "snoozed":
                        logger.info(f"Conversación con {phone} está en pausa/snoozed. Bot silenciado.")
                        return True

                    # Verificar etiquetas de atención humana o archivo
                    labels = set(l.lower() for l in (conv.get("labels") or []))
                    if labels.intersection(IGNORED_LABELS):
                        logger.info(f"Conversación con {phone} tiene etiqueta de control humano {labels}. Bot silenciado.")
                        return True

            return False
        except Exception as e:
            logger.warning(f"Error verificando estado en Chatwoot para {phone}: {e}")
            return False

    async def handover_to_agent(self, phone: str, reason: str = "Solicitud de asistencia humana"):
        """
        Transfiere la conversación al CRM marcándola como 'open', agregando etiqueta 'atencion_humana' y dejando una nota privada.
        """
        if not self.token:
            return

        try:
            clean_phone = phone.replace("+", "").strip()
            async with httpx.AsyncClient(timeout=4.0) as client:
                search_url = f"{self.base_url}/api/v1/accounts/{self.account_id}/contacts/search?q={clean_phone}"
                resp = await client.get(search_url, headers=self.headers)
                if resp.status_code != 200:
                    return
                contacts = resp.json().get("payload", [])
                if not contacts:
                    return
                contact_id = contacts[0]["id"]

                conv_url = f"{self.base_url}/api/v1/accounts/{self.account_id}/contacts/{contact_id}/conversations"
                conv_resp = await client.get(conv_url, headers=self.headers)
                if conv_resp.status_code != 200:
                    return
                conv_data = conv_resp.json().get("payload", [])
                if not conv_data:
                    return

                active_conv = conv_data[0]
                conv_id = active_conv["id"]

                # 1. Asegurar estado 'open'
                status_url = f"{self.base_url}/api/v1/accounts/{self.account_id}/conversations/{conv_id}/toggle_status"
                await client.post(status_url, json={"status": "open"}, headers=self.headers)

                # 2. Agregar etiqueta 'atencion_humana' para pausar el bot de inmediato
                labels_url = f"{self.base_url}/api/v1/accounts/{self.account_id}/conversations/{conv_id}/labels"
                await client.post(labels_url, json={"labels": ["atencion_humana"]}, headers=self.headers)

                # 3. Agregar nota privada interna para el equipo
                notes_url = f"{self.base_url}/api/v1/accounts/{self.account_id}/conversations/{conv_id}/messages"
                note_payload = {
                    "content": f"🤖 **BOT HOTELERO:** Conversación transferida al asesor comercial.\nMotivo: {reason}",
                    "message_type": "activity",
                    "private": True
                }
                await client.post(notes_url, json=note_payload, headers=self.headers)
                logger.info(f"Handover ejecutado para {phone} en conversación Chatwoot #{conv_id}")

        except Exception as e:
            logger.error(f"Error realizando handover a Chatwoot: {e}")

chatwoot_service = ChatwootService()
