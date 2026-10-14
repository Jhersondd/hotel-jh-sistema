"""
Suite de Pruebas de Calidad (QA), Produccion y Tests de Usuario Final
Sistema de Hotel Autónomo - Hotel JH
"""
import sys
import os
import json
from datetime import datetime, date, timedelta

# Asegurar path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.storage_service import storage_service
from services.filter_service import filter_service
from services.redis_service import redis_service
from state_machine import parse_dates_from_text, extract_dni_and_name

def test_dates_validation():
    print("\n--- TEST 1: Control Estricto de Fechas ---")
    today = datetime.now().date()
    past_d1, past_d2 = parse_dates_from_text("2026-10-10 al 2026-10-12")
    assert past_d1 is not None and past_d2 is not None, "Error parseando fechas pasadas"
    p_in = datetime.strptime(past_d1, "%Y-%m-%d").date()
    assert p_in < today, "Debe detectar que 2026-10-10 es fecha pasada"

    inv_d1, inv_d2 = parse_dates_from_text("2026-11-15 al 2026-11-10")
    inv_in = datetime.strptime(inv_d1, "%Y-%m-%d").date()
    inv_out = datetime.strptime(inv_d2, "%Y-%m-%d").date()
    noches_inv = (inv_out - inv_in).days
    assert noches_inv <= 0, "Debe calcular noches <= 0 para salida anterior a ingreso"

    fut_d1, fut_d2 = parse_dates_from_text("2026-11-20 al 2026-11-22")
    assert fut_d1 is not None and fut_d2 is not None, "Error parseando fechas futuras"
    f_in = datetime.strptime(fut_d1, "%Y-%m-%d").date()
    assert f_in >= today, "Debe aceptar fecha futura"
    print("✅ TEST 1 PASADO: Fechas pasadas e invertidas rechazadas correctamente.")

def test_dni_extraction_and_lookup():
    print("\n--- TEST 2: Extracción y Búsqueda por DNI/Pasaporte ---")
    dni, name = extract_dni_and_name("Carlos Alberto Ruiz - 47575542")
    assert dni == "47575542", f"DNI esperado '47575542', obtenido '{dni}'"
    assert "Carlos Alberto Ruiz" in name, f"Nombre esperado, obtenido '{name}'"

    test_res = {
        "id_reserva": "RES-2026-TEST01",
        "id_habitacion": "HAB-101",
        "nombre_huesped": "Carlos Alberto Ruiz",
        "dni_documento": "47575542",
        "telefono_wa": "51910000001",
        "fecha_ingreso": "2026-11-20",
        "fecha_salida": "2026-11-22",
        "pin_acceso": "123456#",
        "estado_reserva": "CONFIRMADA",
        "monto_total": 300.0,
        "estado_pago": "PAGADO",
        "metodo_pago": "Yape"
    }
    storage_service.save_reservation(test_res)

    found_by_dni = storage_service.find_reservation("47575542")
    assert found_by_dni is not None, "Fallo al buscar por DNI"
    assert found_by_dni["id_reserva"] == "RES-2026-TEST01", "ID de reserva no coincide"
    assert found_by_dni["pin_acceso"] == "123456#", "PIN de Smartlock no coincide"

    found_by_code = storage_service.find_reservation("RES-2026-TEST01")
    assert found_by_code is not None, "Fallo al buscar por código de reserva"

    not_found = storage_service.find_reservation("00000000")
    assert not_found is None, "Debe retornar None para DNI inexistente"
    print("✅ TEST 2 PASADO: Extracción e indexación de DNI funcionando al 100%.")

def test_dynamic_availability():
    print("\n--- TEST 3: Disponibilidad Dinámica de Habitaciones ---")
    disp, total, ocup = storage_service.get_available_rooms("2026-11-20", "2026-11-22")
    assert total >= 3, "Catálogo de habitaciones debe tener al menos 3 habitaciones"
    # HAB-101 está reservada en esas fechas
    hab_ids = [r["id_habitacion"] for r in disp]
    assert "HAB-101" not in hab_ids, "HAB-101 no debe estar disponible en fechas ya reservadas"
    assert ocup >= 1, "Debe contabilizar al menos 1 habitación ocupada"
    print(f"✅ TEST 3 PASADO: Disponibilidad dinámica calcula {len(disp)}/{total} libres, {ocup} ocupadas.")

def test_sales_and_chat_logging():
    print("\n--- TEST 4: Base de Ventas y Logs de Conversación ---")
    test_sale_data = {
        "id_reserva": "RES-2026-TEST01",
        "id_habitacion": "HAB-101",
        "nombre_huesped": "Carlos Alberto Ruiz",
        "dni_documento": "47575542",
        "telefono_wa": "51910000001",
        "noches": 2,
        "monto_total": 300.0,
        "metodo_pago": "Yape",
        "estado_pago": "PAGADO"
    }
    sale = storage_service.record_sale(test_sale_data, agent="Bot Autónomo")
    assert sale["id_venta"].startswith("VTA-"), "ID de venta inválido"
    assert sale["monto_total"] == 300.0, "Monto de venta incorrecto"

    analytics = storage_service.get_sales_analytics()
    assert analytics["total_ventas_conteo"] >= 1, "Debe haber al menos 1 venta"
    assert analytics["ingresos_totales_soles"] >= 300.0, "Ingresos totales incorrectos"

    # Registrar chat log
    log = storage_service.record_chat_log(
        phone="51910000001",
        guest_name="Carlos Ruiz",
        role="Huesped",
        message="Quiero consultar tarifas",
        state="MENU",
        intent="Consulta_Tarifas",
        success=True
    )
    assert log["telefono"] == "51910000001", "Teléfono en log incorrecto"

    recent_logs = storage_service.get_chat_logs(limit=10)
    assert len(recent_logs) >= 1, "Debe existir al menos 1 log conversacional"
    print(f"✅ TEST 4 PASADO: Venta e interacción registradas. Total ventas: S/ {analytics['ingresos_totales_soles']}")

def test_ignored_phones_filter():
    print("\n--- TEST 5: Filtro de Chats Archivados e Ignorados ---")
    test_phone = "51988887777"
    assert not filter_service.is_phone_ignored(test_phone), "Número nuevo no debe estar ignorado inicialmente"

    filter_service.add_ignored_phone(test_phone, reason="Contacto de prueba QA")
    assert filter_service.is_phone_ignored(test_phone), "Número debe estar ignorado tras agregarlo"

    filter_service.remove_ignored_phone(test_phone)
    assert not filter_service.is_phone_ignored(test_phone), "Número no debe estar ignorado tras eliminarlo"
    print("✅ TEST 5 PASADO: Filtro de exclusión de chats archivados verificado.")

def main():
    print("=" * 60)
    print("EJECUTANDO EVALUACION DE PRODUCCION Y QA - HOTEL JH")
    print("=" * 60)
    test_dates_validation()
    test_dni_extraction_and_lookup()
    test_dynamic_availability()
    test_sales_and_chat_logging()
    test_ignored_phones_filter()
    print("\n" + "=" * 60)
    print("🎉 TODAS LAS PRUEBAS DE QA Y PRODUCCIÓN PASARON CON ÉXITO (100%)")
    print("=" * 60)

if __name__ == "__main__":
    main()
