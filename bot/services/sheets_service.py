import os
import logging
from datetime import datetime
from typing import List, Dict, Optional
from config import settings
from services.redis_service import redis_service

logger = logging.getLogger("hotel_bot.sheets")

# Datos demo por defecto si Google Sheets aún no ha sido configurado
MOCK_HABITACIONES = [
    {
        "id_habitacion": "HAB-101",
        "tipo": "Matrimonial Estándar",
        "precio_base": 150.00,
        "estado_operativo": "Disponible",
        "id_cerradura_iot": "lock_101",
        "descripcion": "Cama Queen, baño privado, TV Smart, Wi-Fi 200MB, agua caliente."
    },
    {
        "id_habitacion": "HAB-102",
        "tipo": "Doble Superior",
        "precio_base": 190.00,
        "estado_operativo": "Disponible",
        "id_cerradura_iot": "lock_102",
        "descripcion": "2 camas de 1.5 plazas, baño privado, escritorio, vista panorámica."
    },
    {
        "id_habitacion": "HAB-201",
        "tipo": "Suite Matrimonial Jacuzzi",
        "precio_base": 280.00,
        "estado_operativo": "Disponible",
        "id_cerradura_iot": "lock_201",
        "descripcion": "Cama King, Jacuzzi privado, minibar, aire acondicionado, balcón."
    }
]

class SheetsService:
    def __init__(self):
        self.sheet_id = settings.GOOGLE_SHEET_ID
        self.creds_file = settings.GOOGLE_CREDENTIALS_FILE
        self.client = None
        self.sheet = None
        self._init_client()

    def _init_client(self):
        if not self.sheet_id or not os.path.exists(self.creds_file):
            logger.info("Google Sheets no configurado aún (falta ID o credentials.json). Se usará catálogo en memoria.")
            return

        try:
            import gspread
            self.client = gspread.service_account(filename=self.creds_file)
            self.sheet = self.client.open_by_key(self.sheet_id)
            logger.info(f"Conectado exitosamente a Google Sheet: {self.sheet.title}")
        except Exception as e:
            logger.error(f"Error conectando a Google Sheets: {e}. Se usará catálogo en memoria.")
            self.client = None
            self.sheet = None

    def get_all_rooms(self) -> List[Dict]:
        if not self.sheet:
            return MOCK_HABITACIONES

        try:
            ws = self.sheet.worksheet("Habitaciones")
            records = ws.get_all_records()
            rooms = []
            for r in records:
                rooms.append({
                    "id_habitacion": str(r.get("id_habitacion", "")),
                    "tipo": str(r.get("tipo", "")),
                    "precio_base": float(r.get("precio_base", 0)),
                    "estado_operativo": str(r.get("estado_operativo", "Disponible")),
                    "id_cerradura_iot": str(r.get("id_cerradura_iot", "")),
                    "descripcion": str(r.get("descripcion", ""))
                })
            return rooms
        except Exception as e:
            logger.error(f"Error leyendo 'Habitaciones' de Google Sheets: {e}")
            return MOCK_HABITACIONES

    def get_confirmed_reservations(self) -> List[Dict]:
        if not self.sheet:
            return []

        try:
            ws = self.sheet.worksheet("Reservas")
            records = ws.get_all_records()
            reservas = []
            for r in records:
                estado = str(r.get("estado_reserva", "")).upper()
                if estado not in ["CANCELADA", "CHECKOUT"]:
                    reservas.append({
                        "id_reserva": str(r.get("id_reserva")),
                        "id_habitacion": str(r.get("id_habitacion")),
                        "fecha_ingreso": str(r.get("fecha_ingreso")),
                        "fecha_salida": str(r.get("fecha_salida")),
                        "estado_reserva": estado
                    })
            return reservas
        except Exception as e:
            logger.error(f"Error leyendo 'Reservas' de Google Sheets: {e}")
            return []

    def get_available_rooms(self, checkin: str, checkout: str, guest_phone: str = None) -> List[Dict]:
        """
        Calcula habitaciones disponibles cruzando estado operativo, reservas previas y candados en Redis (15m).
        """
        all_rooms = self.get_all_rooms()
        existing_res = self.get_confirmed_reservations()

        try:
            req_in = datetime.strptime(checkin, "%Y-%m-%d").date()
            req_out = datetime.strptime(checkout, "%Y-%m-%d").date()
        except ValueError:
            return []

        available = []
        for room in all_rooms:
            room_id = room["id_habitacion"]

            # 1. Filtro operativo
            if room["estado_operativo"].lower() != "disponible":
                continue

            # 2. Filtro de hold en Redis (15 minutos mientras alguien más está pagando)
            if redis_service.is_room_held(room_id, checkin, checkout, by_phone=guest_phone):
                continue

            # 3. Filtro de cruce de fechas con reservas existentes
            has_conflict = False
            for res in existing_res:
                if res["id_habitacion"] == room_id:
                    try:
                        res_in = datetime.strptime(res["fecha_ingreso"], "%Y-%m-%d").date()
                        res_out = datetime.strptime(res["fecha_salida"], "%Y-%m-%d").date()

                        # Conflicto si los rangos se solapan
                        if not (req_out <= res_in or req_in >= res_out):
                            has_conflict = True
                            break
                    except ValueError:
                        continue

            if not has_conflict:
                available.append(room)

        return available

    def create_reservation(self, res_data: dict) -> bool:
        """
        Registra la nueva reserva en la hoja 'Reservas'.
        """
        logger.info(f"Registrando reserva: {res_data}")
        if not self.sheet:
            return True

        try:
            ws = self.sheet.worksheet("Reservas")
            row = [
                res_data.get("id_reserva", ""),
                res_data.get("id_habitacion", ""),
                res_data.get("nombre_huesped", ""),
                res_data.get("telefono_wa", ""),
                res_data.get("fecha_ingreso", ""),
                res_data.get("fecha_salida", ""),
                res_data.get("pin_acceso", ""),
                res_data.get("estado_reserva", "CONFIRMADA"),
                res_data.get("monto_total", 0.0),
                res_data.get("estado_pago", "PAGADO"),
                res_data.get("metodo_pago", "Transferencia"),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ]
            ws.append_row(row)
            return True
        except Exception as e:
            logger.error(f"Error escribiendo reserva en Google Sheets: {e}")
            return False

    def register_lead(self, phone: str, name: str, stage: str = "Cotizado"):
        if not self.sheet:
            return

        try:
            ws = self.sheet.worksheet("Leads_CRM")
            row = [
                f"LEAD-{phone[-4:]}",
                phone,
                name or "Huésped WhatsApp",
                stage,
                "Bot Autónomo",
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ]
            ws.append_row(row)
        except Exception as e:
            logger.warning(f"Error registrando lead en Google Sheets: {e}")

    def record_sale(self, sale_data: dict) -> bool:
        """
        Registra una venta confirmada en la hoja 'Ventas' para analítica financiera y comercial.
        """
        if not self.sheet:
            return False
        try:
            try:
                ws = self.sheet.worksheet("Ventas")
            except Exception:
                ws = self.sheet.add_worksheet(title="Ventas", rows=500, cols=13)
                ws.append_row([
                    "ID_Venta", "Fecha_Venta", "ID_Reserva", "Habitacion", "Huesped",
                    "DNI", "Telefono", "Noches", "Monto_Total", "Metodo_Pago",
                    "Estado_Pago", "Canal_Venta", "Agente_Cierre"
                ])

            row = [
                sale_data.get("id_venta", ""),
                sale_data.get("fecha_venta", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                sale_data.get("id_reserva", ""),
                sale_data.get("habitacion", ""),
                sale_data.get("huesped", ""),
                sale_data.get("dni", ""),
                sale_data.get("telefono", ""),
                sale_data.get("noches", 1),
                sale_data.get("monto_total", 0.0),
                sale_data.get("metodo_pago", "Transferencia / Yape"),
                sale_data.get("estado_pago", "PAGADO"),
                sale_data.get("canal_venta", "WhatsApp"),
                sale_data.get("agente_cierre", "Bot Autónomo")
            ]
            ws.append_row(row)
            logger.info(f"Venta {sale_data.get('id_venta')} registrada en pestaña 'Ventas' de Google Sheets")
            return True
        except Exception as e:
            logger.error(f"Error registrando venta en Google Sheets: {e}")
            return False

    def record_chat_log(self, log_data: dict) -> bool:
        """
        Registra interacciones en la pestaña 'Logs_Conversaciones' para optimización del agente comercial.
        """
        if not self.sheet:
            return False
        try:
            try:
                ws = self.sheet.worksheet("Logs_Conversaciones")
            except Exception:
                ws = self.sheet.add_worksheet(title="Logs_Conversaciones", rows=1000, cols=8)
                ws.append_row([
                    "Timestamp", "Telefono", "Huesped", "Rol",
                    "Mensaje", "Estado_Flujo", "Intencion_Detectada", "Exito"
                ])

            row = [
                log_data.get("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                log_data.get("telefono", ""),
                log_data.get("huesped", ""),
                log_data.get("rol", "Huesped"),
                str(log_data.get("mensaje", ""))[:300],
                log_data.get("estado_flujo", ""),
                log_data.get("intencion", "Consulta"),
                "SI" if log_data.get("exito", True) else "NO"
            ]
            ws.append_row(row)
            return True
        except Exception as e:
            logger.debug(f"Error registrando log de chat en Google Sheets: {e}")
            return False

    def get_ignored_phones_from_sheet(self) -> set:
        """
        Obtiene los teléfonos ignorados / archivados desde la pestaña 'Chats_Ignorados'.
        """
        if not self.sheet:
            return set()
        try:
            ws = self.sheet.worksheet("Chats_Ignorados")
            records = ws.get_all_records()
            phones = set()
            for r in records:
                val = str(r.get("telefono") or r.get("Telefono") or r.get("TELEFONO") or "").strip()
                val = val.replace("+", "").replace(" ", "").replace("-", "")
                if val:
                    phones.add(val)
            return phones
        except Exception as e:
            return set()

    def add_ignored_phone_to_sheet(self, phone: str, name: str = "", reason: str = "Archivado"):
        """
        Registra un nuevo teléfono ignorado en la pestaña 'Chats_Ignorados' de Google Sheets.
        """
        if not self.sheet:
            return False
        try:
            try:
                ws = self.sheet.worksheet("Chats_Ignorados")
            except Exception:
                ws = self.sheet.add_worksheet(title="Chats_Ignorados", rows=100, cols=5)
                ws.append_row(["Telefono", "Nombre", "Motivo", "Fecha_Agregado"])
            clean = phone.replace("+", "").replace(" ", "").replace("-", "").strip()
            ws.append_row([clean, name, reason, datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
            logger.info(f"Teléfono {clean} registrado como ignorado en Google Sheets")
            return True
        except Exception as e:
            logger.error(f"Error agregando teléfono ignorado a Google Sheets: {e}")
            return False

sheets_service = SheetsService()

