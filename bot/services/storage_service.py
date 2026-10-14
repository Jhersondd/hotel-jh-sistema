import os
import json
import logging
from datetime import datetime, date
from typing import List, Dict, Optional, Tuple
from config import settings
from services.redis_service import redis_service

logger = logging.getLogger("hotel_bot.storage")

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
RESERVATIONS_FILE = os.path.join(DATA_DIR, "reservations.json")
ROOMS_FILE = os.path.join(DATA_DIR, "rooms.json")
SALES_FILE = os.path.join(DATA_DIR, "sales.json")
CHAT_LOGS_FILE = os.path.join(DATA_DIR, "chat_logs.json")

DEFAULT_ROOMS = [
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

class StorageService:
    def __init__(self):
        self._ensure_data_files()

    def _ensure_data_files(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        if not os.path.exists(ROOMS_FILE):
            with open(ROOMS_FILE, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_ROOMS, f, indent=2, ensure_ascii=False)
        if not os.path.exists(RESERVATIONS_FILE):
            with open(RESERVATIONS_FILE, "w", encoding="utf-8") as f:
                json.dump([], f, indent=2, ensure_ascii=False)
        if not os.path.exists(SALES_FILE):
            with open(SALES_FILE, "w", encoding="utf-8") as f:
                json.dump([], f, indent=2, ensure_ascii=False)
        if not os.path.exists(CHAT_LOGS_FILE):
            with open(CHAT_LOGS_FILE, "w", encoding="utf-8") as f:
                json.dump([], f, indent=2, ensure_ascii=False)

    def get_all_rooms(self) -> List[Dict]:
        """Obtiene el catálogo de habitaciones del hotel."""
        # Si Google Sheets está conectado, intentar primero desde ahí
        try:
            from services.sheets_service import sheets_service
            if sheets_service.sheet:
                rooms = sheets_service.get_all_rooms()
                if rooms:
                    return rooms
        except Exception:
            pass

        try:
            if os.path.exists(ROOMS_FILE):
                with open(ROOMS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error leyendo {ROOMS_FILE}: {e}")

        return DEFAULT_ROOMS

    def get_all_reservations(self) -> List[Dict]:
        """Obtiene todas las reservas registradas (persistidas localmente y sincronizadas)."""
        reservas = []
        try:
            if os.path.exists(RESERVATIONS_FILE):
                with open(RESERVATIONS_FILE, "r", encoding="utf-8") as f:
                    reservas = json.load(f)
        except Exception as e:
            logger.error(f"Error leyendo {RESERVATIONS_FILE}: {e}")

        # Si Google Sheets está activo, complementar con las de Sheets
        try:
            from services.sheets_service import sheets_service
            if sheets_service.sheet:
                sheet_res = sheets_service.get_confirmed_reservations()
                ids_existentes = {r.get("id_reserva") for r in reservas if r.get("id_reserva")}
                for sr in sheet_res:
                    if sr.get("id_reserva") not in ids_existentes:
                        reservas.append(sr)
        except Exception:
            pass

        return reservas

    def save_reservation(self, res_data: dict) -> bool:
        """
        Guarda la reserva en el archivo local JSON, en Redis y en Google Sheets.
        """
        res_id = res_data.get("id_reserva", "")
        if not res_id:
            return False

        # 1. Guardar en JSON local
        try:
            reservas = []
            if os.path.exists(RESERVATIONS_FILE):
                with open(RESERVATIONS_FILE, "r", encoding="utf-8") as f:
                    try:
                        reservas = json.load(f)
                    except json.JSONDecodeError:
                        reservas = []

            # Actualizar si ya existe o agregar nueva
            idx = next((i for i, r in enumerate(reservas) if r.get("id_reserva") == res_id), -1)
            if idx >= 0:
                reservas[idx] = res_data
            else:
                reservas.append(res_data)

            with open(RESERVATIONS_FILE, "w", encoding="utf-8") as f:
                json.dump(reservas, f, indent=2, ensure_ascii=False)
            logger.info(f"Reserva {res_id} guardada en {RESERVATIONS_FILE}")
        except Exception as e:
            logger.error(f"Error guardando reserva en archivo local: {e}")

        # 2. Guardar en Redis para búsqueda rápida en memoria
        if redis_service.client:
            try:
                redis_service.client.set(f"reservation:{res_id}", json.dumps(res_data), ex=86400 * 30)
                # Índices secundarios
                dni = res_data.get("dni_documento", "").strip()
                if dni:
                    redis_service.client.set(f"res_by_dni:{dni}", res_id, ex=86400 * 30)
                phone = res_data.get("telefono_wa", "").strip()
                if phone:
                    redis_service.client.set(f"res_by_phone:{phone}", res_id, ex=86400 * 30)
            except Exception as e:
                logger.warning(f"Error guardando reserva en Redis: {e}")

        # 3. Guardar en Google Sheets
        try:
            from services.sheets_service import sheets_service
            if sheets_service.sheet:
                sheets_service.create_reservation(res_data)
        except Exception as e:
            logger.warning(f"Error guardando reserva en Sheets: {e}")

        return True

    def find_reservation(self, query: str, phone: str = None) -> Optional[Dict]:
        """
        Busca una reserva por DNI/Pasaporte, Código de Reserva (RES-XXXX), teléfono o nombre.
        """
        q = (query or "").strip().lower()
        clean_phone = (phone or "").replace("+", "").strip()

        # 1. Buscar en Redis por DNI exacto
        if redis_service.client and q:
            try:
                cached_id = redis_service.client.get(f"res_by_dni:{q}")
                if cached_id:
                    res_raw = redis_service.client.get(f"reservation:{cached_id.decode('utf-8')}")
                    if res_raw:
                        return json.loads(res_raw.decode("utf-8"))
            except Exception:
                pass

        # 2. Buscar en reservas locales
        reservas = self.get_all_reservations()
        for r in reversed(reservas):
            r_id = str(r.get("id_reserva", "")).lower()
            r_dni = str(r.get("dni_documento", "")).lower()
            r_phone = str(r.get("telefono_wa", "")).replace("+", "").strip()
            r_name = str(r.get("nombre_huesped", "")).lower()

            # Coincidencia por DNI
            if q and (q == r_dni or q in r_dni):
                return r

            # Coincidencia por Código de Reserva
            if q and (q == r_id or q in r_id):
                return r

            # Coincidencia por teléfono del remitente si coincide con la reserva
            if clean_phone and clean_phone in r_phone:
                return r

            # Coincidencia por nombre si la consulta contiene el nombre
            if q and len(q) >= 4 and (q in r_name or r_name in q):
                return r

        return None

    def get_available_rooms(self, checkin: str, checkout: str, guest_phone: str = None) -> Tuple[List[Dict], int, int]:
        """
        Calcula habitaciones disponibles cruzando estado operativo, reservas confirmadas y holds en Redis.
        Retorna: (habitaciones_disponibles, total_habitaciones, ocupadas_conteo)
        """
        all_rooms = self.get_all_rooms()
        existing_res = self.get_all_reservations()

        try:
            req_in = datetime.strptime(checkin, "%Y-%m-%d").date()
            req_out = datetime.strptime(checkout, "%Y-%m-%d").date()
        except ValueError:
            return [], len(all_rooms), 0

        available = []
        occupied_count = 0

        for room in all_rooms:
            room_id = room["id_habitacion"]

            # 1. Filtro operativo (mantenimiento o limpieza)
            if room["estado_operativo"].lower() != "disponible":
                occupied_count += 1
                continue

            # 2. Filtro de hold en Redis (15 minutos mientras otro cliente completa pago)
            if redis_service.is_room_held(room_id, checkin, checkout, by_phone=guest_phone):
                occupied_count += 1
                continue

            # 3. Filtro de cruce de fechas con reservas existentes
            has_conflict = False
            for res in existing_res:
                if res.get("id_habitacion") == room_id:
                    estado = str(res.get("estado_reserva", "")).upper()
                    if estado in ["CANCELADA", "CHECKOUT"]:
                        continue

                    try:
                        res_in_str = res.get("fecha_ingreso")
                        res_out_str = res.get("fecha_salida")
                        if not res_in_str or not res_out_str:
                            continue
                        res_in = datetime.strptime(res_in_str, "%Y-%m-%d").date()
                        res_out = datetime.strptime(res_out_str, "%Y-%m-%d").date()

                        # Conflicto si los rangos se solapan
                        if not (req_out <= res_in or req_in >= res_out):
                            has_conflict = True
                            break
                    except ValueError:
                        continue

            if not has_conflict:
                available.append(room)
            else:
                occupied_count += 1

        return available, len(all_rooms), occupied_count

    def get_today_checkouts(self) -> List[Dict]:
        """Retorna las reservas cuyo check-out es hoy para notificaciones internas."""
        today_str = datetime.now().strftime("%Y-%m-%d")
        reservas = self.get_all_reservations()
        checkouts_today = []
        for r in reservas:
            if r.get("fecha_salida") == today_str and r.get("estado_reserva") in ["CONFIRMADA", "EN_ESTADIA"]:
                checkouts_today.append(r)
        return checkouts_today

    def record_sale(self, res_data: dict, agent: str = "Bot Autónomo") -> dict:
        """
        Registra una venta comercial en sales.json, en Redis y en Google Sheets (pestaña 'Ventas').
        """
        import random
        sale_id = f"VTA-{datetime.now().strftime('%Y%m%d')}-{random.randint(1000, 9999)}"
        sale = {
            "id_venta": sale_id,
            "fecha_venta": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "id_reserva": res_data.get("id_reserva", ""),
            "habitacion": res_data.get("id_habitacion", ""),
            "huesped": res_data.get("nombre_huesped", ""),
            "dni": res_data.get("dni_documento", ""),
            "telefono": res_data.get("telefono_wa", ""),
            "noches": res_data.get("noches", 1),
            "monto_total": float(res_data.get("monto_total", 0.0)),
            "metodo_pago": res_data.get("metodo_pago", "Transferencia / Yape"),
            "estado_pago": res_data.get("estado_pago", "PAGADO"),
            "canal_venta": "WhatsApp",
            "agente_cierre": agent
        }

        # 1. Guardar en JSON local
        try:
            sales = self.get_all_sales()
            sales.append(sale)
            with open(SALES_FILE, "w", encoding="utf-8") as f:
                json.dump(sales, f, indent=2, ensure_ascii=False)
            logger.info(f"Venta {sale_id} registrada localmente en {SALES_FILE}")
        except Exception as e:
            logger.error(f"Error guardando venta localmente: {e}")

        # 2. Guardar en Google Sheets (pestaña 'Ventas')
        try:
            from services.sheets_service import sheets_service
            sheets_service.record_sale(sale)
        except Exception as e:
            logger.warning(f"Error sincronizando venta con Google Sheets: {e}")

        return sale

    def get_all_sales(self) -> List[Dict]:
        """Obtiene todas las ventas registradas."""
        if os.path.exists(SALES_FILE):
            try:
                with open(SALES_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error leyendo {SALES_FILE}: {e}")
        return []

    def record_chat_log(self, phone: str, guest_name: str, role: str, message: str, state: str, intent: str = "Consulta", success: bool = True) -> dict:
        """
        Registra cada interacción de chat para análisis de embudo comercial y reentrenamiento.
        """
        log_entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "telefono": phone,
            "huesped": guest_name,
            "rol": role,
            "mensaje": str(message)[:300],
            "estado_flujo": state,
            "intencion": intent,
            "exito": success
        }

        # 1. Guardar en JSON local (con rotación para no superar 5000 logs)
        try:
            logs = []
            if os.path.exists(CHAT_LOGS_FILE):
                try:
                    with open(CHAT_LOGS_FILE, "r", encoding="utf-8") as f:
                        logs = json.load(f)
                except Exception:
                    logs = []

            logs.append(log_entry)
            if len(logs) > 5000:
                logs = logs[-4000:]

            with open(CHAT_LOGS_FILE, "w", encoding="utf-8") as f:
                json.dump(logs, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.debug(f"Error guardando log de chat local: {e}")

        # 2. Guardar en Google Sheets (pestaña 'Logs_Conversaciones')
        try:
            from services.sheets_service import sheets_service
            sheets_service.record_chat_log(log_entry)
        except Exception:
            pass

        return log_entry

    def get_chat_logs(self, limit: int = 100) -> List[Dict]:
        """Retorna los últimos N logs conversacionales."""
        if os.path.exists(CHAT_LOGS_FILE):
            try:
                with open(CHAT_LOGS_FILE, "r", encoding="utf-8") as f:
                    logs = json.load(f)
                    return logs[-limit:]
            except Exception:
                pass
        return []

    def get_sales_analytics(self) -> Dict:
        """
        Calcula métricas comerciales consolidadas para dashboard de gerencia.
        """
        sales = self.get_all_sales()
        reservations = self.get_all_reservations()

        total_ventas = len(sales)
        ingresos_totales = sum(s.get("monto_total", 0.0) for s in sales)
        ticket_promedio = (ingresos_totales / total_ventas) if total_ventas > 0 else 0.0

        habitaciones_populares = {}
        for s in sales:
            hab = s.get("habitacion", "Otro")
            habitaciones_populares[hab] = habitaciones_populares.get(hab, 0) + 1

        metodos_pago = {}
        for s in sales:
            m = s.get("metodo_pago", "Otro")
            metodos_pago[m] = metodos_pago.get(m, 0) + 1

        return {
            "total_ventas_conteo": total_ventas,
            "ingresos_totales_soles": round(ingresos_totales, 2),
            "ticket_promedio_soles": round(ticket_promedio, 2),
            "habitaciones_mas_vendidas": habitaciones_populares,
            "metodos_pago_distribucion": metodos_pago,
            "reservas_activas_conteo": len(reservations),
            "tasa_conversion_estimada": f"{round((total_ventas / max(len(reservations) + total_ventas, 1)) * 100, 1)}%"
        }

storage_service = StorageService()
