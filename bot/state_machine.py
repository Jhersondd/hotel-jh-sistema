import re
import random
import logging
from datetime import datetime, timedelta, date
from config import settings
from services.redis_service import redis_service
from services.storage_service import storage_service
from services.sheets_service import sheets_service
from services.evolution_service import evolution_service
from services.chatwoot_service import chatwoot_service
from services.ttlock_service import ttlock_service
from services.notification_service import notification_service

logger = logging.getLogger("hotel_bot.state_machine")

def parse_dates_from_text(text: str):
    """
    Intenta extraer dos fechas en formato YYYY-MM-DD o DD/MM/AAAA.
    """
    clean_text = text.strip()

    # Regex para YYYY-MM-DD
    iso_dates = re.findall(r"\b(202\d-\d{1,2}-\d{1,2})\b", clean_text)
    if len(iso_dates) >= 2:
        try:
            d1 = datetime.strptime(iso_dates[0], "%Y-%m-%d").date()
            d2 = datetime.strptime(iso_dates[1], "%Y-%m-%d").date()
            return str(d1), str(d2)
        except ValueError:
            pass

    # Regex para DD/MM/YYYY o DD-MM-YYYY
    latam_dates = re.findall(r"\b(\d{1,2})[/-](\d{1,2})[/-](202\d)\b", clean_text)
    if len(latam_dates) >= 2:
        try:
            d1 = datetime(int(latam_dates[0][2]), int(latam_dates[0][1]), int(latam_dates[0][0])).date()
            d2 = datetime(int(latam_dates[1][2]), int(latam_dates[1][1]), int(latam_dates[1][0])).date()
            return str(d1), str(d2)
        except ValueError:
            pass

    return None, None

def extract_dni_and_name(text: str) -> tuple:
    """Extrae el DNI/Documento y el nombre del texto ingresado por el huésped."""
    clean = text.strip()
    # Buscar secuencia de 8 a 12 dígitos
    doc_match = re.search(r"\b(\d{8,12})\b", clean)
    if doc_match:
        doc = doc_match.group(1)
        name = clean.replace(doc, "").replace("-", "").replace("/", "").strip()
        if not name or len(name) < 3:
            name = "Huésped"
        return doc, name
    return "", clean

async def confirm_and_deliver_pin(phone: str, res_data: dict = None) -> bool:
    """
    Confirma una reserva, genera el PIN de cerradura inteligente (TTLock) y lo entrega al huésped.
    """
    session = redis_service.get_user_session(phone)
    if not res_data:
        res_id = session.get("res_id") or f"RES-2026-{random.randint(1000, 9999)}"
        room_id = session.get("selected_room")
        checkin = session.get("checkin")
        checkout = session.get("checkout")
        lock_id = session.get("lock_id")
        monto = session.get("monto_total", 0.0)
        guest_name = session.get("guest_name", "Huésped")
        guest_dni = session.get("dni_documento", "Registrado")
    else:
        res_id = res_data.get("id_reserva")
        room_id = res_data.get("id_habitacion")
        checkin = res_data.get("fecha_ingreso")
        checkout = res_data.get("fecha_salida")
        lock_id = res_data.get("id_cerradura_iot", "")
        monto = res_data.get("monto_total", 0.0)
        guest_name = res_data.get("nombre_huesped", "Huésped")
        guest_dni = res_data.get("dni_documento", "Registrado")

    if not room_id or not checkin or not checkout:
        return False

    # Generar PIN temporal de cerradura inteligente (TTLock / Fallback seguro)
    pin_code = await ttlock_service.generate_passcode(lock_id, checkin, checkout)

    final_res = {
        "id_reserva": res_id,
        "id_habitacion": room_id,
        "nombre_huesped": guest_name,
        "dni_documento": guest_dni,
        "telefono_wa": phone,
        "fecha_ingreso": checkin,
        "fecha_salida": checkout,
        "pin_acceso": pin_code,
        "estado_reserva": "CONFIRMADA",
        "monto_total": monto,
        "estado_pago": "PAGADO",
        "metodo_pago": "Transferencia / Yape",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    # Guardar en almacenamiento local JSON + Redis + Google Sheets
    storage_service.save_reservation(final_res)

    # Registrar venta comercial en el libro de ventas y analítica
    storage_service.record_sale(final_res, agent="Bot Autónomo")

    # Liberar el hold temporal de Redis
    redis_service.release_room_hold(room_id, checkin, checkout)
    redis_service.clear_user_session(phone)

    # Mensaje de confirmación y entrega de llave digital autónoma
    confirm_msg = (
        f"🎉 *¡RESERVA CONFIRMADA CON ÉXITO!* 🎉\n\n"
        f"Estimado/a *{guest_name}*, tu estadía está 100% asegurada:\n\n"
        f"📋 Código de Reserva: *{res_id}*\n"
        f"🏨 Habitación: *{room_id}*\n"
        f"🪪 DNI Registrado: *{guest_dni}*\n"
        f"🗓️ Ingreso: *{checkin}* (Check-in desde las {settings.CHECKIN_TIME})\n"
        f"🗓️ Salida: *{checkout}* (Check-out hasta las {settings.CHECKOUT_TIME})\n\n"
        f"🔑 *TU CÓDIGO DIGITAL DE ACCESO (SMARTLOCK):*\n"
        f"👉 Código PIN: *{pin_code}*\n\n"
        f"📖 *Instrucciones para abrir tu habitación:*\n"
        f"1. Toca el teclado táctil de la cerradura para encender la luz.\n"
        f"2. Digita tu PIN: *{pin_code}* (presiona la tecla numeral al final).\n"
        f"3. La cerradura emitirá un pitido verde y se desbloqueará de inmediato.\n\n"
        f"📶 *Wi-Fi:* Red `Hotel_JH_Huespedes` / Clave: `HotelJH2026`\n"
        f"📍 *Ubicación:* https://maps.google.com\n\n"
        f"¡Que disfrutes tu estadía en {settings.HOTEL_NAME}! Escribe *MENU* cuando necesites asistencia."
    )
    await evolution_service.send_text(phone, confirm_msg)

    # Notificar internamente al administrador / recepción
    await notification_service.notify_new_booking(final_res)
    return True

async def handle_guest_message(phone: str, user_name: str, message_text: str):
    text = (message_text or "").strip()
    session = redis_service.get_user_session(phone)
    current_state = session.get("state", "START")

    logger.info(f"Procesando mensaje de {phone} en estado [{current_state}]: '{text}'")

    # Registrar interacción conversacional para analítica y auditoría
    storage_service.record_chat_log(
        phone=phone,
        guest_name=user_name,
        role="Huesped",
        message=text,
        state=current_state,
        intent="Interaccion"
    )

    # Comando de reinicio universal
    if text.lower() in ["menu", "menú", "inicio", "cancelar", "reiniciar", "hola", "buenas"]:
        if current_state != "START" and text.lower() in ["menu", "menú", "inicio", "cancelar"]:
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
        greeting = (
            f"¡Hola {user_name or ''}! 👋 Bienvenido a *{settings.HOTEL_NAME}* 🏨\n"
            f"Tu estadía autónoma, confortable y segura.\n\n"
            f"¿Cómo te podemos ayudar hoy? Por favor responde con el número de tu opción:\n\n"
            f"1️⃣ *Consultar habitaciones y tarifas disponibles*\n"
            f"2️⃣ *Consultar mi reserva / Obtener PIN de acceso*\n"
            f"3️⃣ *Hablar con un asesor comercial (Recepción)*\n\n"
            f"_Responde con 1, 2 o 3_"
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
            today = datetime.now().date()
            tomorrow = today + timedelta(days=1)
            msg = (
                f"📅 *Consulta de Disponibilidad*\n\n"
                f"Por favor indícanos tus fechas de *ingreso* y *salida* en formato AAAA-MM-DD.\n\n"
                f"📌 *Ejemplo:* `{today} al {tomorrow}`\n\n"
                f"_(O escribe MENU para volver al inicio)_"
            )
            redis_service.set_user_session(phone, {"state": "AWAITING_DATES"})
            await evolution_service.send_text(phone, msg)
            return

        elif text == "2" or "reserva" in text.lower() or "acceso" in text.lower() or "pin" in text.lower():
            msg = (
                f"🔍 *Consulta de Reserva y Llave Digital*\n\n"
                f"Por favor escribe tu número de *Documento de Identidad (DNI o Pasaporte)* con el que registraste tu estadía, o tu *Código de Reserva* (ejemplo: `RES-2026-XXXX`):"
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
    # ESTADO: AWAITING_DATES (PARSEO DE FECHAS CON CONTROL ESTRICTO)
    # =========================================================================
    if current_state == "AWAITING_DATES":
        checkin, checkout = parse_dates_from_text(text)
        if not checkin or not checkout:
            today = datetime.now().date()
            tomorrow = today + timedelta(days=1)
            await evolution_service.send_text(
                phone,
                f"⚠️ No pude reconocer las fechas. Por favor escríbelas en formato `AAAA-MM-DD al AAAA-MM-DD`.\n\n"
                f"📌 *Ejemplo:* `{today} al {tomorrow}`"
            )
            return

        d_in = datetime.strptime(checkin, "%Y-%m-%d").date()
        d_out = datetime.strptime(checkout, "%Y-%m-%d").date()
        today = datetime.now().date()

        # CONTROL DE FECHAS: 1. No permitir fechas pasadas
        if d_in < today:
            await evolution_service.send_text(
                phone,
                f"⚠️ *Fecha no válida:* La fecha de ingreso ({checkin}) ya pasó. Hoy es *{today}*.\n\n"
                f"Por favor indica fechas a partir de hoy en adelante (Ejemplo: `{today} al {today + timedelta(days=1)}`)."
            )
            return

        # CONTROL DE FECHAS: 2. Salida debe ser posterior al ingreso
        noches = (d_out - d_in).days
        if noches <= 0:
            await evolution_service.send_text(
                phone,
                "⚠️ *Fecha no válida:* La fecha de salida debe ser posterior a la fecha de ingreso (mínimo 1 noche de estadía)."
            )
            return

        # CONTROL DE FECHAS: 3. Límite razonable (máximo 60 noches)
        if noches > 60:
            await evolution_service.send_text(
                phone,
                "⚠️ Para reservas corporativas o de larga estadía (más de 60 noches), por favor escribe *3* para coordinar con recepción."
            )
            return

        # Consultar habitaciones disponibles cruzando datos reales
        disponibles, total_rooms, ocupadas = storage_service.get_available_rooms(checkin, checkout, guest_phone=phone)
        if not disponibles:
            msg = (
                f"😔 Lo sentimos, todas nuestras habitaciones están reservadas del *{checkin}* al *{checkout}*.\n\n"
                f"¿Deseas probar con otras fechas o prefieres hablar con un asesor? Escribe *3* para asesor o envía otras fechas."
            )
            await evolution_service.send_text(phone, msg)
            return

        # Listar opciones con indicador dinámico de disponibilidad
        msg = f"🏨 *Habitaciones Disponibles en Hotel JH*\n"
        msg += f"🗓️ Estadía: Del *{checkin}* al *{checkout}* ({noches} noche{'s' if noches > 1 else ''})\n"
        msg += f"📊 Disponibilidad: *{len(disponibles)} de {total_rooms} habitaciones disponibles* ({ocupadas} reservadas)\n\n"

        for r in disponibles:
            total = r["precio_base"] * noches
            msg += (
                f"🚪 *{r['id_habitacion']}* — {r['tipo']}\n"
                f"   💵 Tarifa: S/ {r['precio_base']:.2f}/noche (Total: *S/ {total:.2f}*)\n"
                f"   ✨ {r.get('descripcion', '')}\n\n"
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

        all_rooms = storage_service.get_all_rooms()
        room_info = next((r for r in all_rooms if r["id_habitacion"] == room_id), None)
        precio_total = (room_info["precio_base"] if room_info else 150) * session.get("noches", 1)

        session["selected_room"] = room_id
        session["monto_total"] = precio_total
        session["lock_id"] = room_info.get("id_cerradura_iot", "") if room_info else ""
        session["state"] = "AWAITING_GUEST_INFO"
        redis_service.set_user_session(phone, session)

        msg = (
            f"🔒 *Habitación {room_id} retenida por 15 minutos*\n"
            f"💵 Total de estadía: *S/ {precio_total:.2f}* ({session.get('noches', 1)} noches)\n\n"
            f"Para tu registro hotelero oficial, por favor ingresa tu:\n"
            f"👤 *Nombre Completo y N° de DNI o Pasaporte*\n\n"
            f"📌 *Ejemplo:* `Carlos Alberto Ruiz - 47575542`"
        )
        await evolution_service.send_text(phone, msg)
        return

    # =========================================================================
    # ESTADO: AWAITING_GUEST_INFO (PARSEO PRECISO DE DNI Y NOMBRE)
    # =========================================================================
    if current_state == "AWAITING_GUEST_INFO":
        dni, name = extract_dni_and_name(text)
        if not dni:
            # Si no incluyó número de documento, solicitárselo cortésmente
            await evolution_service.send_text(
                phone,
                "⚠️ Por favor ingresa también tu número de *DNI o Pasaporte* para el registro legal del hotel.\n\n"
                "📌 *Ejemplo:* `Juan Pérez - 45678912`"
            )
            return

        session["guest_name"] = name
        session["dni_documento"] = dni
        session["res_id"] = f"RES-2026-{random.randint(1000, 9999)}"
        session["state"] = "AWAITING_PAYMENT"
        redis_service.set_user_session(phone, session)

        msg = (
            f"💳 *Instrucciones para el Pago*\n\n"
            f"🏨 Habitación: *{session['selected_room']}*\n"
            f"👤 Huésped: *{name}* (DNI: `{dni}`)\n"
            f"💵 Monto a transferir: *S/ {session['monto_total']:.2f}*\n\n"
            f"📌 *Cuentas Bancarias y Billeteras Digitales:*\n"
            f"{settings.BANK_TRANSFER_DETAILS}\n\n"
            f"📸 Una vez realizado el abono, por favor envía la *foto o captura de pantalla de tu comprobante* por este chat.\n\n"
            f"_Nuestro equipo verificará el abono para emitir tu PIN de acceso digital._"
        )
        await evolution_service.send_text(phone, msg)
        return

    # =========================================================================
    # ESTADO: AWAITING_PAYMENT (FILTRO ESTRICTO DE COMPROBANTE Y VERIFICACIÓN)
    # =========================================================================
    if current_state == "AWAITING_PAYMENT":
        is_image_sent = (text == "COMPROBANTE_ENVIADO" or "comprobante" in text.lower())

        if not is_image_sent:
            await evolution_service.send_text(
                phone,
                f"⚠️ Para poder validar tu reserva de la habitación *{session.get('selected_room')}*, "
                f"por favor envía la *foto o captura de pantalla* del comprobante de transferencia bancaria o Yape/Plin.\n\n"
                f"_Si ya lo enviaste o tienes alguna dificultad, escribe *3* para hablar con recepción._"
            )
            return

        # Guardar pre-reserva en estado PENDIENTE_VERIFICACION
        pre_res = {
            "id_reserva": session.get("res_id"),
            "id_habitacion": session.get("selected_room"),
            "nombre_huesped": session.get("guest_name"),
            "dni_documento": session.get("dni_documento"),
            "telefono_wa": phone,
            "fecha_ingreso": session.get("checkin"),
            "fecha_salida": session.get("checkout"),
            "pin_acceso": "Pendiente de Validación",
            "estado_reserva": "EN_VERIFICACION",
            "monto_total": session.get("monto_total", 0.0),
            "estado_pago": "EN_REVISION",
            "metodo_pago": "Transferencia / Yape",
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        storage_service.save_reservation(pre_res)

        # Notificar internamente a recepción / administrador con alerta de verificación
        await notification_service.notify_receipt_pending_verification(
            phone=phone,
            room_id=session.get("selected_room"),
            amount=session.get("monto_total", 0.0),
            guest_name=session.get("guest_name"),
            dni=session.get("dni_documento")
        )

        # Responder al cliente de forma profesional y transparente
        receipt_ack = (
            f"📸 *¡Comprobante de Pago Recibido!*\n\n"
            f"Muchas gracias, *{session.get('guest_name')}*. Hemos recibido tu comprobante para la habitación *{session.get('selected_room')}*.\n\n"
            f"⏳ En este momento nuestro equipo de recepción está validando el abono en el sistema bancario (demora de 2 a 5 minutos).\n\n"
            f"En cuanto esté confirmado, te enviaremos por este mismo chat tu confirmación final y el *PIN digital de la cerradura* de tu habitación.\n\n"
            f"_Si necesitas atención urgente, escribe *3* para hablar directamente con recepción._"
        )
        await evolution_service.send_text(phone, receipt_ack)
        return

    # =========================================================================
    # ESTADO: AWAITING_DOC_QUERY (BUSCAR RESERVA POR DNI, CODIGO O TELEFONO)
    # =========================================================================
    if current_state == "AWAITING_DOC_QUERY":
        query = text.strip()
        encontrada = storage_service.find_reservation(query, phone=phone)

        if encontrada:
            msg = (
                f"📋 *Información de tu Reserva - {settings.HOTEL_NAME}*\n\n"
                f"• Código: *{encontrada.get('id_reserva')}*\n"
                f"• Huésped: *{encontrada.get('nombre_huesped', 'Huésped')}*\n"
                f"• DNI/Doc: *{encontrada.get('dni_documento', 'Registrado')}*\n"
                f"• Habitación: *{encontrada.get('id_habitacion')}*\n"
                f"• Fechas: Del *{encontrada.get('fecha_ingreso')}* al *{encontrada.get('fecha_salida')}*\n"
                f"• Estado: *{encontrada.get('estado_reserva')}* ({encontrada.get('estado_pago', 'PAGADO')})\n\n"
                f"🔑 *TU PIN DIGITAL DE ACCESO (SMARTLOCK):*\n"
                f"👉 PIN: *{encontrada.get('pin_acceso', 'Consultar en recepción')}*\n\n"
                f"⏰ Check-in: desde las {settings.CHECKIN_TIME} | Check-out: hasta las {settings.CHECKOUT_TIME}\n"
                f"📶 Wi-Fi: Red `Hotel_JH_Huespedes` / Clave: `HotelJH2026`\n\n"
                f"_Si requieres cambios en tu reserva, escribe *3* para hablar con recepción._"
            )
        else:
            msg = (
                f"❌ No encontramos una reserva activa con el documento o código *{query}*.\n\n"
                f"¿Deseas verificar con un recepcionista? Escribe *3* para comunicarte con recepción o *MENU* para volver al inicio."
            )

        redis_service.clear_user_session(phone)
        await evolution_service.send_text(phone, msg)
        return
