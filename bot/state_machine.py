import re
import random
import logging
from datetime import datetime, timedelta
from config import settings
from services.redis_service import redis_service
from services.sheets_service import sheets_service
from services.evolution_service import evolution_service
from services.chatwoot_service import chatwoot_service
from services.ttlock_service import ttlock_service

logger = logging.getLogger("hotel_bot.state_machine")

def parse_dates_from_text(text: str):
    """
    Intenta extraer dos fechas en formato YYYY-MM-DD o DD/MM/AAAA.
    """
    # Regex para YYYY-MM-DD
    iso_dates = re.findall(r"\b(202\d-\d{1,2}-\d{1,2})\b", text)
    if len(iso_dates) >= 2:
        try:
            d1 = datetime.strptime(iso_dates[0], "%Y-%m-%d").date()
            d2 = datetime.strptime(iso_dates[1], "%Y-%m-%d").date()
            if d2 > d1:
                return str(d1), str(d2)
        except ValueError:
            pass

    # Regex para DD/MM/YYYY o DD-MM-YYYY
    latam_dates = re.findall(r"\b(\d{1,2})[/-](\d{1,2})[/-](202\d)\b", text)
    if len(latam_dates) >= 2:
        try:
            d1 = datetime(int(latam_dates[0][2]), int(latam_dates[0][1]), int(latam_dates[0][0])).date()
            d2 = datetime(int(latam_dates[1][2]), int(latam_dates[1][1]), int(latam_dates[1][0])).date()
            if d2 > d1:
                return str(d1), str(d2)
        except ValueError:
            pass

    return None, None

async def handle_guest_message(phone: str, user_name: str, message_text: str):
    text = (message_text or "").strip()
    session = redis_service.get_user_session(phone)
    current_state = session.get("state", "START")

    logger.info(f"Procesando mensaje de {phone} en estado [{current_state}]: '{text}'")

    # Comando de reinicio universal
    if text.lower() in ["menu", "menú", "inicio", "cancelar", "reiniciar", "hola", "buenas"]:
        if current_state != "START" and text.lower() in ["menu", "menú", "inicio", "cancelar"]:
            # Liberar cualquier hold temporal activo
            hold_room = session.get("selected_room")
            h_in = session.get("checkin")
            h_out = session.get("checkout")
            if hold_room and h_in and h_out:
                redis_service.release_room_hold(hold_room, h_in, h_out)

            redis_service.clear_user_session(phone)
            current_state = "START"

    # =========================================================================
    # ESTADO: START / MENU PRINCIPAL
    # =========================================================================
    if current_state == "START":
        # Menú de bienvenida
        greeting = (
            f"¡Hola {user_name or ''}! 👋 Bienvenido a *{settings.HOTEL_NAME}* 🏨\n"
            f"Tu estadía autónoma y confortable en la mejor ubicación.\n\n"
            f"¿Cómo te podemos ayudar hoy? Elige una opción:\n\n"
            f"1️⃣ *Ver habitaciones y tarifas disponibles*\n"
            f"2️⃣ *Consultar mi reserva / Obtener PIN de acceso*\n"
            f"3️⃣ *Hablar con un asesor comercial*\n\n"
            f"_Responde con el número de tu opción (1, 2 o 3)_"
        )
        redis_service.set_user_session(phone, {"state": "MENU"})
        await evolution_service.send_text(phone, greeting)
        sheets_service.register_lead(phone, user_name, "Nuevo Contacto")
        return

    # =========================================================================
    # ESTADO: MENU (EVALUAR SELECCIÓN)
    # =========================================================================
    if current_state == "MENU":
        if text == "1" or "habitacion" in text.lower() or "tarifa" in text.lower():
            today = datetime.now().strftime("%Y-%m-%d")
            tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            msg = (
                f"📅 *Consulta de Disponibilidad*\n\n"
                f"Por favor indícanos tus fechas de *ingreso* y *salida* en formato AAAA-MM-DD.\n\n"
                f"Ejemplo: `{today} al {tomorrow}`"
            )
            redis_service.set_user_session(phone, {"state": "AWAITING_DATES"})
            await evolution_service.send_text(phone, msg)
            return

        elif text == "2" or "reserva" in text.lower() or "acceso" in text.lower() or "pin" in text.lower():
            msg = (
                f"🔍 *Consulta de Reserva*\n\n"
                f"Por favor escribe tu número de *Documento de Identidad (DNI/Pasaporte)* con el que registraste tu reserva:"
            )
            redis_service.set_user_session(phone, {"state": "AWAITING_DOC_QUERY"})
            await evolution_service.send_text(phone, msg)
            return

        elif text == "3" or "asesor" in text.lower() or "humano" in text.lower() or "recepcion" in text.lower():
            msg = (
                f"🛎️ *Transferencia a Recepción*\n\n"
                f"He notificado a nuestro equipo comercial y de recepción. Uno de nuestros asesores responderá "
                f"por este mismo chat en breve.\n\n"
                f"_El bot se ha pausado para brindarte atención personalizada._"
            )
            await evolution_service.send_text(phone, msg)
            await chatwoot_service.handover_to_agent(phone, "Huésped solicitó hablar con recepción")
            redis_service.clear_user_session(phone)
            return
        else:
            await evolution_service.send_text(
                phone,
                "Por favor responde con *1*, *2* o *3* según lo que desees realizar, o escribe *MENU* para reiniciar."
            )
            return

    # =========================================================================
    # ESTADO: AWAITING_DATES (PARSEO DE FECHAS Y BÚSQUEDA)
    # =========================================================================
    if current_state == "AWAITING_DATES":
        checkin, checkout = parse_dates_from_text(text)
        if not checkin or not checkout:
            await evolution_service.send_text(
                phone,
                "⚠️ No pude reconocer las fechas. Por favor escríbelas en formato `AAAA-MM-DD al AAAA-MM-DD` (ejemplo: `2026-11-15 al 2026-11-17`)."
            )
            return

        # Calcular número de noches
        d_in = datetime.strptime(checkin, "%Y-%m-%d").date()
        d_out = datetime.strptime(checkout, "%Y-%m-%d").date()
        noches = (d_out - d_in).days

        if noches <= 0:
            await evolution_service.send_text(phone, "⚠️ La fecha de salida debe ser posterior a la fecha de ingreso.")
            return

        # Consultar habitaciones disponibles
        disponibles = sheets_service.get_available_rooms(checkin, checkout, guest_phone=phone)
        if not disponibles:
            msg = (
                f"😔 Lo sentimos, no tenemos habitaciones disponibles para el rango del *{checkin}* al *{checkout}*.\n\n"
                f"¿Deseas probar con otras fechas o prefieres hablar con un asesor? Escribe *3* para asesor o envía otras fechas."
            )
            await evolution_service.send_text(phone, msg)
            return

        # Listar opciones
        msg = f"✨ *Habitaciones Disponibles ({noches} noche{'s' if noches > 1 else ''})*\n"
        msg += f"🗓️ Del *{checkin}* al *{checkout}*\n\n"

        for r in disponibles:
            total = r["precio_base"] * noches
            msg += (
                f"🚪 *{r['id_habitacion']}* - {r['tipo']}\n"
                f"💵 Tarifa: S/ {r['precio_base']:.2f} / noche (Total: *S/ {total:.2f}*)\n"
                f"ℹ️ {r.get('descripcion', '')}\n\n"
            )

        msg += (
            f"👉 Para reservar, responde con el código de la habitación que deseas (ejemplo: *{disponibles[0]['id_habitacion']}*).\n"
            f"O escribe *MENU* para volver al inicio."
        )

        redis_service.set_user_session(phone, {
            "state": "SELECTING_ROOM",
            "checkin": checkin,
            "checkout": checkout,
            "noches": noches,
            "available_ids": [r["id_habitacion"].upper() for r in disponibles]
        })
        await evolution_service.send_text(phone, msg)
        sheets_service.register_lead(phone, user_name, "Cotización Presentada")
        return

    # =========================================================================
    # ESTADO: SELECTING_ROOM (APLICAR HOLD ATÓMICO 15 MIN)
    # =========================================================================
    if current_state == "SELECTING_ROOM":
        selected_code = text.upper().replace(" ", "")
        valid_ids = session.get("available_ids", [])

        matched = [vid for vid in valid_ids if vid in selected_code or selected_code in vid]
        if not matched:
            await evolution_service.send_text(
                phone,
                f"⚠️ Habitación no válida. Por favor selecciona una de las disponibles: {', '.join(valid_ids)} o escribe *MENU*."
            )
            return

        room_id = matched[0]
        checkin = session.get("checkin")
        checkout = session.get("checkout")

        # Bloquear habitación por 15 minutos en Redis (Cart Hold)
        acquired = redis_service.acquire_room_hold(room_id, checkin, checkout, phone, ttl_seconds=900)
        if not acquired:
            await evolution_service.send_text(
                phone,
                f"⚠️ La habitación *{room_id}* acaba de ser seleccionada por otro cliente. "
                f"Por favor elige otra de la lista o espera unos minutos."
            )
            return

        # Buscar detalles de la habitación
        all_rooms = sheets_service.get_all_rooms()
        room_info = next((r for r in all_rooms if r["id_habitacion"] == room_id), None)
        precio_total = (room_info["precio_base"] if room_info else 150) * session.get("noches", 1)

        session["selected_room"] = room_id
        session["monto_total"] = precio_total
        session["lock_id"] = room_info.get("id_cerradura_iot", "") if room_info else ""
        session["state"] = "AWAITING_GUEST_INFO"
        redis_service.set_user_session(phone, session)

        msg = (
            f"🔒 *Habitación {room_id} retenida por 15 minutos*\n\n"
            f"Total a pagar: *S/ {precio_total:.2f}*\n\n"
            f"Para completar tu pre-registro, por favor escribe tu:\n"
            f"*Nombre Completo y N° de DNI o Pasaporte*\n\n"
            f"Ejemplo: `Carlos Alberto Ruiz - 48912345`"
        )
        await evolution_service.send_text(phone, msg)
        return

    # =========================================================================
    # ESTADO: AWAITING_GUEST_INFO (DATOS DEL CLIENTE Y DATOS DE PAGO)
    # =========================================================================
    if current_state == "AWAITING_GUEST_INFO":
        session["guest_data"] = text
        session["state"] = "AWAITING_PAYMENT"
        redis_service.set_user_session(phone, session)

        msg = (
            f"💳 *Instrucciones de Pago*\n\n"
            f"Habitación: *{session['selected_room']}*\n"
            f"Monto total: *S/ {session['monto_total']:.2f}*\n\n"
            f"📌 *Cuentas Bancarias y Billeteras Digitales:*\n"
            f"{settings.BANK_TRANSFER_DETAILS}\n\n"
            f"📸 Una vez realizado el pago, por favor envía la *foto o captura de tu comprobante* "
            f"por este chat (o escribe *CONFIRMAR PAGO*)."
        )
        await evolution_service.send_text(phone, msg)
        return

    # =========================================================================
    # ESTADO: AWAITING_PAYMENT (VALIDACIÓN Y EMISIÓN DE PIN AUTÓNOMO)
    # =========================================================================
    if current_state == "AWAITING_PAYMENT":
        # Generar código de reserva único
        res_id = f"RES-2026-{random.randint(1000, 9999)}"
        room_id = session.get("selected_room")
        checkin = session.get("checkin")
        checkout = session.get("checkout")
        lock_id = session.get("lock_id")
        monto = session.get("monto_total")
        guest_info = session.get("guest_data", user_name)

        # Generar PIN temporal de cerradura inteligente (TTLock)
        pin_code = await ttlock_service.generate_passcode(lock_id, checkin, checkout)

        # Guardar reserva definitiva en Google Sheets
        sheets_service.create_reservation({
            "id_reserva": res_id,
            "id_habitacion": room_id,
            "nombre_huesped": guest_info,
            "telefono_wa": phone,
            "fecha_ingreso": checkin,
            "fecha_salida": checkout,
            "pin_acceso": pin_code,
            "estado_reserva": "CONFIRMADA",
            "monto_total": monto,
            "estado_pago": "PAGADO",
            "metodo_pago": "Transferencia / Yape"
        })

        # Liberar el hold temporal de Redis (ya es una reserva confirmada)
        redis_service.release_room_hold(room_id, checkin, checkout)
        redis_service.clear_user_session(phone)

        # Mensaje de confirmación y entrega de llave digital autónoma
        confirm_msg = (
            f"🎉 *¡RESERVA CONFIRMADA CON ÉXITO!* 🎉\n\n"
            f"📋 Código de Reserva: *{res_id}*\n"
            f"🏨 Habitación Asignada: *{room_id}*\n"
            f"🗓️ Ingreso: *{checkin}* (desde las {settings.CHECKIN_TIME})\n"
            f"🗓️ Salida: *{checkout}* (hasta las {settings.CHECKOUT_TIME})\n\n"
            f"🔑 *TU CÓDIGO DIGITAL DE ACCESO (SMARTLOCK):*\n"
            f"👉 Código PIN: *{pin_code}*\n\n"
            f"📖 *Instrucciones para abrir tu habitación:*\n"
            f"1. Toca el teclado digital de la cerradura de tu habitación para encender la luz.\n"
            f"2. Digita tu PIN: *{pin_code}* (incluyendo la tecla numeral al final).\n"
            f"3. La cerradura emitirá un pitido verde y se desbloqueará automáticamente.\n\n"
            f"📶 *Wi-Fi del Hotel:* Red `Hotel_JH_Huespedes` / Clave: `HotelJH2026`\n"
            f"📍 *Ubicación:* https://maps.google.com\n\n"
            f"¡Que tengas una excelente estadía! Escribe *MENU* cuando necesites asistencia."
        )
        await evolution_service.send_text(phone, confirm_msg)
        return

    # =========================================================================
    # ESTADO: AWAITING_DOC_QUERY (BUSCAR RESERVA EXISTENTE)
    # =========================================================================
    if current_state == "AWAITING_DOC_QUERY":
        query = text.strip().lower()
        reservas = sheets_service.get_confirmed_reservations()

        # Buscar por teléfono o documento
        encontrada = None
        for r in reservas:
            if phone in r.get("telefono_wa", "") or query in str(r.get("nombre_huesped", "")).lower():
                encontrada = r
                break

        if encontrada:
            msg = (
                f"✅ *Reserva Encontrada*\n\n"
                f"Código: *{encontrada['id_reserva']}*\n"
                f"Habitación: *{encontrada['id_habitacion']}*\n"
                f"Fechas: *{encontrada['fecha_ingreso']}* al *{encontrada['fecha_salida']}*\n"
                f"Estado: *{encontrada['estado_reserva']}*\n"
                f"🔑 PIN de Puerta: *{encontrada.get('pin_acceso', 'Consultar en recepción')}*\n\n"
                f"Si requieres cambios en tu reserva, escribe *3* para hablar con recepción."
            )
        else:
            msg = (
                f"❌ No encontramos una reserva activa asociada a esos datos.\n"
                f"¿Deseas verificar con un recepcionista? Escribe *3* para comunicarte con recepción o *MENU* para volver al inicio."
            )

        redis_service.clear_user_session(phone)
        await evolution_service.send_text(phone, msg)
        return
