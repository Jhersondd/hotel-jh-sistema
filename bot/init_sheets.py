import os
import json
import logging
from datetime import datetime
import gspread

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("init_sheets")

SPREADSHEET_ID = "1Fic5pia9U2oqlulgRJWttbhh-nwHoR96SdCKEuAnwz4"
CREDS_FILE = os.path.join(os.path.dirname(__file__), "credentials.json")
if not os.path.exists(CREDS_FILE):
    CREDS_FILE = "/app/credentials.json"

DEFAULT_ROOMS = [
    [
        "HAB-101",
        "Matrimonial Estándar",
        150.00,
        "Disponible",
        "lock_101",
        "Cama Queen, baño privado, TV Smart, Wi-Fi 200MB, agua caliente."
    ],
    [
        "HAB-102",
        "Doble Superior",
        190.00,
        "Disponible",
        "lock_102",
        "2 camas de 1.5 plazas, baño privado, escritorio, vista panorámica."
    ],
    [
        "HAB-201",
        "Suite Matrimonial Jacuzzi",
        280.00,
        "Disponible",
        "lock_201",
        "Cama King, Jacuzzi privado, minibar, aire acondicionado, balcón."
    ]
]

def format_header_row(worksheet, num_cols):
    """Aplica formato visual profesional (Fondo azul marino oscuro, texto blanco en negrita, inmovilizar fila 1)."""
    try:
        col_letter = chr(ord('A') + num_cols - 1)
        worksheet.format(f"A1:{col_letter}1", {
            "backgroundColor": {"red": 0.11, "green": 0.21, "blue": 0.36},
            "textFormat": {"foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0}, "bold": True, "fontSize": 10},
            "horizontalAlignment": "CENTER"
        })
        worksheet.freeze(rows=1)
    except Exception as e:
        logger.warning(f"No se pudo aplicar formato estético a {worksheet.title}: {e}")

def main():
    logger.info(f"Conectando a Google Sheets con ID: {SPREADSHEET_ID}")
    gc = gspread.service_account(filename=CREDS_FILE)
    sh = gc.open_by_key(SPREADSHEET_ID)
    logger.info(f"Conexión exitosa a: '{sh.title}'")

    existing_sheets = {ws.title: ws for ws in sh.worksheets()}
    logger.info(f"Pestañas actuales detectadas: {list(existing_sheets.keys())}")

    # =========================================================================
    # 1. PESTAÑA: Habitaciones
    # =========================================================================
    ws_hab = existing_sheets.get("Habitaciones")
    if not ws_hab:
        ws_hab = sh.add_worksheet(title="Habitaciones", rows=100, cols=6)
    
    hab_rows = ws_hab.get_all_values()
    if len(hab_rows) <= 1 or not any(hab_rows[0]):
        logger.info("Inicializando catálogo en 'Habitaciones'...")
        headers = ["id_habitacion", "tipo", "precio_base", "estado_operativo", "id_cerradura_iot", "descripcion"]
        ws_hab.clear()
        ws_hab.append_row(headers)
        for room in DEFAULT_ROOMS:
            ws_hab.append_row(room)
        format_header_row(ws_hab, len(headers))
        logger.info("✅ 'Habitaciones' inicializada con 3 habitaciones disponibles.")
    else:
        logger.info("ℹ️ 'Habitaciones' ya contiene datos, conservando registros existentes.")

    # =========================================================================
    # 2. PESTAÑA: Reservas
    # =========================================================================
    ws_res = existing_sheets.get("Reservas")
    if not ws_res:
        ws_res = sh.add_worksheet(title="Reservas", rows=500, cols=13)

    res_rows = ws_res.get_all_values()
    if len(res_rows) <= 1 or not any(res_rows[0]):
        logger.info("Inicializando pestaña 'Reservas'...")
        headers = [
            "id_reserva", "id_habitacion", "nombre_huesped", "dni_documento",
            "telefono_wa", "fecha_ingreso", "fecha_salida", "pin_acceso",
            "estado_reserva", "monto_total", "estado_pago", "metodo_pago", "fecha_creacion"
        ]
        ws_res.clear()
        ws_res.append_row(headers)

        # Migrar reservas locales si existen
        data_dir = os.path.join(os.path.dirname(__file__), "data")
        local_res_file = os.path.join(data_dir, "reservations.json")
        if os.path.exists(local_res_file):
            try:
                with open(local_res_file, "r", encoding="utf-8") as f:
                    local_res = json.load(f)
                    for r in local_res:
                        row = [
                            r.get("id_reserva", ""),
                            r.get("id_habitacion", ""),
                            r.get("nombre_huesped", ""),
                            r.get("dni_documento", ""),
                            r.get("telefono_wa", ""),
                            r.get("fecha_ingreso", ""),
                            r.get("fecha_salida", ""),
                            r.get("pin_acceso", ""),
                            r.get("estado_reserva", "CONFIRMADA"),
                            r.get("monto_total", 0.0),
                            r.get("estado_pago", "PAGADO"),
                            r.get("metodo_pago", "Yape"),
                            r.get("created_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                        ]
                        ws_res.append_row(row)
                logger.info(f"✅ 'Reservas' sincronizada con {len(local_res)} registros iniciales.")
            except Exception as e:
                logger.warning(f"Error migrando reservas locales: {e}")
        format_header_row(ws_res, len(headers))
    else:
        logger.info("ℹ️ 'Reservas' ya contiene datos.")

    # =========================================================================
    # 3. PESTAÑA: Leads_CRM
    # =========================================================================
    ws_leads = existing_sheets.get("Leads_CRM") or existing_sheets.get("Leads CRM")
    if not ws_leads:
        ws_leads = sh.add_worksheet(title="Leads_CRM", rows=500, cols=6)

    leads_rows = ws_leads.get_all_values()
    if len(leads_rows) <= 1 or not any(leads_rows[0]):
        logger.info("Inicializando pestaña 'Leads_CRM'...")
        headers = ["id_lead", "telefono_wa", "nombre", "etapa_embudo", "agente_asignado", "ultimo_contacto"]
        ws_leads.clear()
        ws_leads.append_row(headers)
        # Lead demo inicial
        ws_leads.append_row(["LEAD-0001", "51910127301", "Jherson Concha", "Reserva_En_Revision", "Bot Autónomo", datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
        format_header_row(ws_leads, len(headers))
        logger.info("✅ 'Leads_CRM' inicializada.")
    else:
        logger.info("ℹ️ 'Leads_CRM' ya contiene datos.")

    # =========================================================================
    # 4. PESTAÑA: Ventas (Base de Ventas)
    # =========================================================================
    ws_ventas = existing_sheets.get("Ventas")
    if not ws_ventas:
        ws_ventas = sh.add_worksheet(title="Ventas", rows=1000, cols=13)

    ventas_rows = ws_ventas.get_all_values()
    if len(ventas_rows) <= 1 or not any(ventas_rows[0]):
        logger.info("Inicializando pestaña 'Ventas'...")
        headers = [
            "ID_Venta", "Fecha_Venta", "ID_Reserva", "Habitacion", "Huesped",
            "DNI", "Telefono", "Noches", "Monto_Total", "Metodo_Pago",
            "Estado_Pago", "Canal_Venta", "Agente_Cierre"
        ]
        ws_ventas.clear()
        ws_ventas.append_row(headers)

        # Migrar ventas locales si existen
        data_dir = os.path.join(os.path.dirname(__file__), "data")
        local_sales_file = os.path.join(data_dir, "sales.json")
        if os.path.exists(local_sales_file):
            try:
                with open(local_sales_file, "r", encoding="utf-8") as f:
                    local_sales = json.load(f)
                    for s in local_sales:
                        row = [
                            s.get("id_venta", ""),
                            s.get("fecha_venta", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                            s.get("id_reserva", ""),
                            s.get("habitacion", ""),
                            s.get("huesped", ""),
                            s.get("dni", ""),
                            s.get("telefono", ""),
                            s.get("noches", 1),
                            s.get("monto_total", 0.0),
                            s.get("metodo_pago", "Yape"),
                            s.get("estado_pago", "PAGADO"),
                            s.get("canal_venta", "WhatsApp"),
                            s.get("agente_cierre", "Bot Autónomo")
                        ]
                        ws_ventas.append_row(row)
                logger.info(f"✅ 'Ventas' sincronizada con {len(local_sales)} transacciones iniciales.")
            except Exception as e:
                logger.warning(f"Error migrando ventas locales: {e}")
        format_header_row(ws_ventas, len(headers))
    else:
        logger.info("ℹ️ 'Ventas' ya contiene datos.")

    # =========================================================================
    # 5. PESTAÑA: Logs_Conversaciones
    # =========================================================================
    ws_logs = existing_sheets.get("Logs_Conversaciones") or existing_sheets.get("Logs Conversaciones")
    if not ws_logs:
        ws_logs = sh.add_worksheet(title="Logs_Conversaciones", rows=2000, cols=8)

    logs_rows = ws_logs.get_all_values()
    if len(logs_rows) <= 1 or not any(logs_rows[0]):
        logger.info("Inicializando pestaña 'Logs_Conversaciones'...")
        headers = [
            "Timestamp", "Telefono", "Huesped", "Rol",
            "Mensaje", "Estado_Flujo", "Intencion_Detectada", "Exito"
        ]
        ws_logs.clear()
        ws_logs.append_row(headers)

        # Migrar logs de conversación locales si existen
        data_dir = os.path.join(os.path.dirname(__file__), "data")
        local_logs_file = os.path.join(data_dir, "chat_logs.json")
        if os.path.exists(local_logs_file):
            try:
                with open(local_logs_file, "r", encoding="utf-8") as f:
                    local_logs = json.load(f)
                    for log in local_logs:
                        row = [
                            log.get("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                            log.get("telefono", ""),
                            log.get("huesped", ""),
                            log.get("rol", "Huesped"),
                            str(log.get("mensaje", ""))[:300],
                            log.get("estado_flujo", ""),
                            log.get("intencion", "Consulta"),
                            "SI" if log.get("exito", True) else "NO"
                        ]
                        ws_logs.append_row(row)
                logger.info(f"✅ 'Logs_Conversaciones' sincronizada con {len(local_logs)} mensajes previos.")
            except Exception as e:
                logger.warning(f"Error migrando logs locales: {e}")
        format_header_row(ws_logs, len(headers))
    else:
        logger.info("ℹ️ 'Logs_Conversaciones' ya contiene datos.")

    # =========================================================================
    # 6. PESTAÑA: Chats_Ignorados
    # =========================================================================
    ws_ign = existing_sheets.get("Chats_Ignorados") or existing_sheets.get("Chats Ignorados")
    if not ws_ign:
        ws_ign = sh.add_worksheet(title="Chats_Ignorados", rows=200, cols=4)

    ign_rows = ws_ign.get_all_values()
    if len(ign_rows) <= 1 or not any(ign_rows[0]):
        logger.info("Inicializando pestaña 'Chats_Ignorados'...")
        headers = ["Telefono", "Nombre", "Motivo", "Fecha_Agregado"]
        ws_ign.clear()
        ws_ign.append_row(headers)
        ws_ign.append_row(["51912275156", "Recepción Hotel JH", "Canal Interno Recepción", datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
        format_header_row(ws_ign, len(headers))
        logger.info("✅ 'Chats_Ignorados' inicializada con número de recepción interna.")
    else:
        logger.info("ℹ️ 'Chats_Ignorados' ya contiene datos.")

    logger.info("🎉 ¡INICIALIZACIÓN COMPLETA DE GOOGLE SHEETS PARA HOTEL JH!")

if __name__ == "__main__":
    main()
