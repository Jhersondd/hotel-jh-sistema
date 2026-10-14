import logging
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from config import settings
from services.redis_service import redis_service
from services.chatwoot_service import chatwoot_service
from services.sheets_service import sheets_service
from services.evolution_service import evolution_service
from services.filter_service import filter_service
from state_machine import handle_guest_message

# Configuración de logs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("hotel_bot.main")

app = FastAPI(
    title=f"API Bot Hotelero Autónomo - {settings.HOTEL_NAME}",
    version="1.0.0",
    description="Motor de automatización y orquestación hotelera para WhatsApp, Chatwoot, Google Sheets y TTLock."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    """
    Verifica el estado de los componentes del sistema.
    """
    evolution_status = await evolution_service.check_instance_status()
    ignored_count = len(filter_service.get_all_ignored_phones())
    return {
        "status": "healthy",
        "hotel": settings.HOTEL_NAME,
        "redis_connected": redis_service.client is not None,
        "sheets_connected": sheets_service.sheet is not None,
        "evolution_status": evolution_status,
        "archived_chats_ignored_count": ignored_count
    }

@app.post("/webhook/evolution")
async def evolution_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Recibe los mensajes entrantes de WhatsApp despachados por Evolution API.
    """
    try:
        body = await request.json()
    except Exception:
        return {"status": "ignored", "reason": "invalid_json"}

    event = body.get("event")
    data = body.get("data", {})

    # Nos interesan únicamente los mensajes entrantes
    if event not in ["messages.upsert", "MESSAGES_UPSERT", "message.create"]:
        return {"status": "ignored", "reason": f"unhandled_event_{event}"}

    key = data.get("key", {})
    from_me = key.get("fromMe", False)

    # Ignorar mensajes enviados por nosotros mismos o por el agente en Chatwoot
    if from_me:
        return {"status": "ignored", "reason": "outgoing_message"}

    # Extraer ID de mensaje para idempotencia
    msg_id = key.get("id")
    remote_jid = key.get("remoteJid", "")

    # Ignorar grupos de WhatsApp, canales de difusión o newsletters
    if "@g.us" in remote_jid or "broadcast" in remote_jid or "@newsletter" in remote_jid:
        return {"status": "ignored", "reason": "group_or_broadcast"}

    phone = filter_service.clean_phone(remote_jid.split("@")[0])
    push_name = data.get("pushName", "Huésped")

    # Extraer texto del mensaje
    message_content = data.get("message", {})
    text = (
        message_content.get("conversation") or
        message_content.get("extendedTextMessage", {}).get("text") or
        message_content.get("imageMessage", {}).get("caption") or
        ""
    ).strip()

    # Si enviaron una imagen sin texto (comprobante de pago)
    if "imageMessage" in message_content and not text:
        text = "COMPROBANTE_ENVIADO"

    if not text:
        return {"status": "ignored", "reason": "empty_text"}

    # 1. FILTRO ESTRICTO DE CHATS ARCHIVADOS / CONTACTOS IGNORADOS
    # Si el chat está en la lista de ignorados (.env, archivo ignored_chats.txt, Google Sheets o Redis),
    # el bot NUNCA responderá a este chat.
    if filter_service.is_phone_ignored(phone):
        logger.info(f"El chat con {phone} está ARCHIVADO / IGNORADO. Bot silenciado.")
        return {"status": "ignored", "reason": "archived_or_blacklisted", "phone": phone}

    # 2. Comandos rápidos de administración para archivar/silenciar números al instante
    if text.startswith("/archivar ") or text.startswith("/ignorar "):
        parts = text.split(" ")
        if len(parts) >= 2:
            target = filter_service.clean_phone(parts[1])
            filter_service.add_ignored_phone(target, reason=f"Comando enviado por {phone}")
            await evolution_service.send_text(phone, f"✅ Chat {target} archivado e ignorado con éxito. El bot ya no le responderá.")
            return {"status": "admin_command_executed", "action": "ignored", "target": target}

    # 3. Filtro de Idempotencia en Redis (evitar procesar duplicados si Evolution reintenta)
    if msg_id and redis_service.client:
        lock_msg_key = f"processed_msg:{msg_id}"
        if not redis_service.client.set(lock_msg_key, "1", nx=True, ex=120):
            logger.info(f"Mensaje {msg_id} ya fue procesado. Descartando reintento.")
            return {"status": "ignored", "reason": "duplicate_message"}

    # 4. Verificación de Handover en Chatwoot:
    # Si un agente comercial humano está atendiendo la conversación ('open', 'snoozed', con etiquetas de archivo o asignada),
    # el bot NO responde.
    is_human_handling = await chatwoot_service.is_agent_active(phone)
    if is_human_handling:
        logger.info(f"El chat con {phone} está en manos de un agente humano o archivado en CRM. Bot silenciado.")
        return {"status": "silenced", "reason": "agent_active"}

    # 5. Procesar flujo de conversación en segundo plano
    background_tasks.add_task(handle_guest_message, phone, push_name, text)

    return {"status": "queued", "phone": phone}

@app.get("/ignored-phones")
async def list_ignored_phones():
    """
    Retorna la lista de teléfonos archivados / ignorados que el bot no atiende.
    """
    phones = sorted(list(filter_service.get_all_ignored_phones()))
    return {"total": len(phones), "ignored_phones": phones}

@app.post("/ignored-phones")
async def add_ignored_phone(data: dict):
    """
    Agrega un teléfono a la lista de archivados/ignorados.
    Ejemplo: {"phone": "51987654321", "reason": "Contacto personal"}
    """
    phone = data.get("phone", "")
    reason = data.get("reason", "Archivado manualmente")
    success = filter_service.add_ignored_phone(phone, reason)
    return {"success": success, "phone": phone, "reason": reason}

@app.delete("/ignored-phones/{phone}")
async def remove_ignored_phone(phone: str):
    """
    Remueve un teléfono de la lista de ignorados para que vuelva a ser atendido por el bot.
    """
    success = filter_service.remove_ignored_phone(phone)
    return {"success": success, "phone": phone}

@app.get("/rooms")
async def list_rooms():
    """
    Lista el catálogo de habitaciones y su estado.
    """
    return sheets_service.get_all_rooms()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=settings.PORT, reload=True)

