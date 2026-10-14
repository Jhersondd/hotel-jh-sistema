import os
import re
import logging
from typing import Set, Dict, List
from config import settings
from services.redis_service import redis_service

logger = logging.getLogger("hotel_bot.filter")

IGNORED_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ignored_chats.txt")

class FilterService:
    def __init__(self):
        self.file_path = IGNORED_FILE_PATH
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        """Crea el archivo ignored_chats.txt si no existe con instrucciones claras."""
        if not os.path.exists(self.file_path):
            with open(self.file_path, "w", encoding="utf-8") as f:
                f.write(
                    "# ==============================================================================\n"
                    "# HOTEL JH - LISTA DE CHATS Y CONTACTOS IGNORADOS / ARCHIVADOS\n"
                    "# Los números en esta lista NUNCA activarán el bot hotelero automático.\n"
                    "# Escribe un número por línea (puedes incluir el código de país, ej: 51912345678).\n"
                    "# Las líneas que comiencen con '#' son comentarios.\n"
                    "# ==============================================================================\n"
                    "# Agrega aquí tus chats personales, familiares, proveedores o archivados:\n"
                )

    def clean_phone(self, phone: str) -> str:
        """Limpia el teléfono quitando +, espacios, guiones y sufijos WhatsApp."""
        if not phone:
            return ""
        clean = phone.split("@")[0]
        clean = re.sub(r"[^\d]", "", clean)
        return clean

    def get_file_ignored_phones(self) -> Set[str]:
        """Lee los números configurados en el archivo ignored_chats.txt."""
        phones = set()
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            clean = self.clean_phone(line)
                            if clean:
                                phones.add(clean)
            except Exception as e:
                logger.error(f"Error leyendo {self.file_path}: {e}")
        return phones

    def get_all_ignored_phones(self) -> Set[str]:
        """
        Retorna la unión de todos los números ignorados:
        1. Configurados en .env (IGNORED_PHONE_NUMBERS)
        2. Configurados en ignored_chats.txt
        3. El propio número del hotel (para evitar loops)
        4. Almacenados dinámicamente en Redis
        """
        ignored = set()

        # 1. Del .env
        for p in settings.ignored_phones:
            cleaned = self.clean_phone(p)
            if cleaned:
                ignored.add(cleaned)

        # 2. Del archivo ignored_chats.txt
        ignored.update(self.get_file_ignored_phones())

        # 3. Número propio del hotel
        ignored.add("51912275156")

        # 4. De Redis
        if redis_service.client:
            try:
                cached = redis_service.client.smembers("hotel:ignored_phones")
                if cached:
                    for c in cached:
                        c_str = c.decode("utf-8") if isinstance(c, bytes) else str(c)
                        ignored.add(self.clean_phone(c_str))
            except Exception as e:
                logger.warning(f"Error leyendo ignored_phones de Redis: {e}")

        # 5. De Google Sheets (Pestaña Chats_Ignorados)
        try:
            from services.sheets_service import sheets_service
            sheet_phones = sheets_service.get_ignored_phones_from_sheet()
            for sp in sheet_phones:
                ignored.add(self.clean_phone(sp))
        except Exception:
            pass

        return ignored

    def is_phone_ignored(self, phone: str) -> bool:
        """
        Verifica de forma ultrarrápida si un teléfono está archivado / ignorado.
        """
        clean = self.clean_phone(phone)
        if not clean:
            return True

        # Verificar contra el conjunto unificado
        all_ignored = self.get_all_ignored_phones()
        if clean in all_ignored:
            return True

        # Verificar terminaciones si el código de país difiere
        for item in all_ignored:
            if len(item) >= 9 and len(clean) >= 9:
                if clean.endswith(item) or item.endswith(clean):
                    return True

        return False

    def add_ignored_phone(self, phone: str, reason: str = "Archivado"):
        """
        Agrega un teléfono a la lista de ignorados tanto en archivo local como en Redis.
        """
        clean = self.clean_phone(phone)
        if not clean:
            return False

        # Guardar en Redis
        if redis_service.client:
            try:
                redis_service.client.sadd("hotel:ignored_phones", clean)
            except Exception as e:
                logger.warning(f"Error guardando en Redis: {e}")

        # Guardar en archivo local si no está ya
        current = self.get_file_ignored_phones()
        if clean not in current:
            try:
                with open(self.file_path, "a", encoding="utf-8") as f:
                    f.write(f"{clean} # {reason}\n")
                logger.info(f"Teléfono {clean} agregado a {self.file_path} ({reason})")
            except Exception as e:
                logger.error(f"Error escribiendo en {self.file_path}: {e}")

        return True

    def remove_ignored_phone(self, phone: str) -> bool:
        """Remueve un teléfono de la lista de ignorados."""
        clean = self.clean_phone(phone)
        if not clean:
            return False

        if redis_service.client:
            try:
                redis_service.client.srem("hotel:ignored_phones", clean)
            except Exception:
                pass

        # Reescribir archivo
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                new_lines = []
                for line in lines:
                    stripped = line.strip()
                    if stripped and not stripped.startswith("#"):
                        if self.clean_phone(stripped) == clean:
                            continue
                    new_lines.append(line)
                with open(self.file_path, "w", encoding="utf-8") as f:
                    f.writelines(new_lines)
            except Exception as e:
                logger.error(f"Error actualizando {self.file_path}: {e}")

        return True

filter_service = FilterService()
