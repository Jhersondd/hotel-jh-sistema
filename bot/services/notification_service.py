import asyncio
import logging
from datetime import datetime
from config import settings
from services.storage_service import storage_service
from services.evolution_service import evolution_service
from services.redis_service import redis_service

logger = logging.getLogger("hotel_bot.notification")

ADMIN_PHONE = "51912275156"

class NotificationService:
    def __init__(self):
        self.admin_phone = ADMIN_PHONE

    async def notify_new_booking(self, res_data: dict):
        """Notifica internamente a recepción / admin de una nueva reserva."""
        msg = (
            f"🔔 *NUEVA RESERVA HOTEL JH*\n\n"
            f"🏨 Habitación: *{res_data.get('id_habitacion')}*\n"
            f"👤 Huésped: *{res_data.get('nombre_huesped')}*\n"
            f"🪪 DNI/Doc: *{res_data.get('dni_documento', 'No especificado')}*\n"
            f"📱 WhatsApp: *+{res_data.get('telefono_wa')}*\n"
            f"🗓️ Fechas: Del *{res_data.get('fecha_ingreso')}* al *{res_data.get('fecha_salida')}*\n"
            f"💵 Monto: *S/ {res_data.get('monto_total', 0):.2f}*\n"
            f"🔑 PIN Smartlock: `{res_data.get('pin_acceso')}`\n"
            f"📌 Estado: *{res_data.get('estado_reserva')}* ({res_data.get('metodo_pago')})"
        )
        try:
            await evolution_service.send_text(self.admin_phone, msg)
        except Exception as e:
            logger.error(f"Error enviando notificación interna de reserva: {e}")

    async def notify_receipt_pending_verification(self, phone: str, room_id: str, amount: float, guest_name: str, dni: str = ""):
        """Notifica internamente a recepción que un cliente ha enviado un comprobante de pago."""
        msg = (
            f"📸 *COMPROBANTE RECIBIDO - PENDIENTE DE REVISIÓN*\n\n"
            f"Un huésped ha enviado su comprobante de pago para validar:\n\n"
            f"👤 Huésped: *{guest_name}*\n"
            f"🪪 DNI/Doc: *{dni or 'En revisión'}*\n"
            f"📱 Teléfono: *+{phone}*\n"
            f"🏨 Habitación solicitada: *{room_id}*\n"
            f"💵 Monto a verificar: *S/ {amount:.2f}*\n\n"
            f"👉 *Acciones de Recepción:*\n"
            f"Verifica el abono en tu app bancaria (BCP/Yape) y en Chatwoot.\n"
            f"Para aprobar y liberar la habitación con PIN, responde por WhatsApp:\n"
            f"`/aprobar {phone}` o usa el botón en Chatwoot."
        )
        try:
            await evolution_service.send_text(self.admin_phone, msg)
        except Exception as e:
            logger.error(f"Error enviando alerta de comprobante pendiente: {e}")

    async def check_and_notify_daily_checkouts(self):
        """
        Verifica las reservas que vencen el día de hoy y notifica a recepción si aún no se notificó.
        """
        today_str = datetime.now().strftime("%Y-%m-%d")
        checkouts = storage_service.get_today_checkouts()

        if not checkouts:
            return

        for res in checkouts:
            res_id = res.get("id_reserva")
            notified_key = f"notified_checkout:{today_str}:{res_id}"

            if redis_service.client and redis_service.client.get(notified_key):
                continue

            msg = (
                f"⏰ *ALERTA DE CHECK-OUT HOY*\n\n"
                f"Habitación: *{res.get('id_habitacion')}*\n"
                f"Huésped: *{res.get('nombre_huesped')}* (DNI: {res.get('dni_documento', 'N/A')})\n"
                f"📱 Teléfono: *+{res.get('telefono_wa')}*\n"
                f"⏰ Hora límite de salida: *{settings.CHECKOUT_TIME}*\n\n"
                f"🧹 *Procedimiento:* Coordinar inspección de habitación y limpieza."
            )
            try:
                await evolution_service.send_text(self.admin_phone, msg)
                if redis_service.client:
                    redis_service.client.set(notified_key, "1", ex=86400)
                logger.info(f"Notificación de checkout enviada para reserva {res_id}")
            except Exception as e:
                logger.error(f"Error enviando alerta de checkout para {res_id}: {e}")

    async def start_scheduler(self):
        """Tarea periódica en segundo plano que revisa alertas cada 10 minutos."""
        logger.info("Iniciando scheduler de notificaciones de check-out y control interno...")
        while True:
            try:
                await self.check_and_notify_daily_checkouts()
            except Exception as e:
                logger.error(f"Error en scheduler de notificaciones: {e}")
            await asyncio.sleep(600)  # Cada 10 minutos

notification_service = NotificationService()
