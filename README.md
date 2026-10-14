# 🏨 Sistema Hotelero Autónomo - Hotel JH ($0 Costo)

Sistema empresarial de gestión hotelera autónomo y ligero con interfaz WhatsApp, consola CRM multiagente en tiempo real (**Chatwoot Community**), base de datos operativa y analítica en **Google Sheets**, persistencia transaccional local, y control de cerraduras inteligentes (**TTLock Smartlock**).

---

## 🚀 Arquitectura Modular del Sistema

```
                  ┌────────────────────────────────────────┐
                  │       WhatsApp (WhatsApp Web / Multi)  │
                  └───────────────────┬────────────────────┘
                                      │ Baileys WebSocket
                                      ▼
                        ┌───────────────────────────┐
                        │     Evolution API v2      │
                        │   (Node.js / Port 8080)   │
                        └───────┬───────────┬───────┘
                                │           │ Webhook en vivo
                                │           ▼
                                │   ┌──────────────────────┐
                                │   │   Chatwoot CRM v3    │
                                │   │ (Consola Multiagente)│
                                │   │ - Asistencia IA      │
                                │   │ - Macros & Canned    │
                                │   └──────────┬───────────┘
                                ▼              │
    ┌──────────────────────────────────────────┴────────────────────┐
    │  Hotel Bot & Orquestador Hotelero (FastAPI / Port 5000)       │
    │  - Máquina de Estados Finita & Control de Fechas Estricto     │
    │  - Extracción e Indexación por DNI / Pasaporte                │
    │  - Filtro Multinivel de Chats Archivados (Personal/Proveedor) │
    │  - Verificación de Comprobantes con Aprobación Recepción      │
    │  - Cart Hold Atómico de 15 min en Redis contra Sobreventas   │
    │  - Notificador Interno de Check-outs Diarios a las 11:00 AM   │
    └───────────────────────┬───────────────────────┬───────────────┘
                            ▼                       ▼
              ┌───────────────────────────┐   ┌──────────────────────────┐
              │ Google Sheets & Local DB  │   │ IoT Smartlocks (TTLock)  │
              │ - Habitaciones            │   │ - Generación de PIN OTP  │
              │ - Reservas & DNI          │   │ - Apertura temporal      │
              │ - Base de Ventas          │   └──────────────────────────┘
              │ - Logs de Conversación    │
              │ - Chats Archivados        │
              └───────────────────────────┘
```

---

## 📋 Características Principales

1. **Gestión Autónoma de Reservas:**
   - Bienvenida humana y no redundante.
   - Búsqueda de disponibilidad dinámica (*"2 de 3 disponibles"*).
   - **Control Estricto de Fechas:** Bloquea fechas pasadas o salidas anteriores al ingreso.
   - Bloqueo atómico (*Cart Hold*) de 15 minutos en Redis para evitar sobreventas (*overbooking*).
2. **Registro e Indexación Precisa por DNI/Pasaporte:**
   - Separa y almacena el documento de identidad como campo indexado.
   - Permite al huésped consultar su reserva y obtener su PIN Smartlock en cualquier momento escribiendo su DNI o código de reserva.
3. **Filtro de Comprobantes de Pago & Aprobación en 1 Clic:**
   - No entrega llaves a ciegas ante cualquier imagen.
   - Pone la reserva en estado `EN_VERIFICACION`, avisa a recepción por WhatsApp y Chatwoot, y emite el PIN tras aprobación (`/aprobar` o botón en CRM).
4. **Filtro Multinivel de Chats Archivados e Ignorados:**
   - Garantiza que tus chats personales, familiares o proveedores nunca activen el bot.
   - Administrable desde `ignored_chats.txt`, Google Sheets (`Chats_Ignorados`), etiquetas de Chatwoot o comando WhatsApp `/archivar <numero>`.
5. **Base de Ventas, Analítica y Logs de Conversación:**
   - Registro automático de cada venta comercial con ID único, noches, monto e ingresos consolidados.
   - Registro de logs conversacionales para análisis de intención y optimización comercial.
6. **Notificaciones Internas de Control:**
   - Scheduler en segundo plano que avisa a recepción a diario sobre los check-outs que vencen a las 11:00 AM para coordinar la limpieza.

---

## 🛠️ Requisitos Previos

* **Docker Desktop** (con soporte WSL2 en Windows) o **Docker** en Linux.
* Conexión a Internet para descargar las imágenes iniciales.
* Un número de WhatsApp para el hotel.

---

## 📦 Puesta en Marcha Rápida

### 1. Clonar el Repositorio
```bash
git clone https://github.com/Jhersondd/hotel-jh-sistema.git
cd hotel-jh-sistema
```

### 2. Configurar Variables de Entorno
Copia `.env.example` a `.env`:
```bash
cp .env.example .env
```
*(Los valores por defecto ya están configurados para funcionar en local).*

### 3. Iniciar Contenedores
```bash
docker compose up -d
```
Todos los servicios se iniciarán de forma aislada y saludable:
- `hotel_postgres:16-alpine` (Base de datos interna)
- `hotel_redis:7-alpine` (Holds y caché en memoria)
- `hotel_chatwoot_web` & `hotel_chatwoot_worker` (CRM en http://localhost:3000)
- `hotel_evolution_api` (API WhatsApp en http://localhost:8080)
- `hotel_bot` (Motor hotelero en http://localhost:5000)

---

## 💬 Manual de Operación para Recepción y Asesores

### 1. Panel CRM Chatwoot ([http://localhost:3000](http://localhost:3000))
- **Ver Conversaciones:** Entra a *"Todas las conversaciones"* para ver a todos los clientes que interactúan en tiempo real.
- **Atender Personalmente:** Haz clic en el botón lateral **"Asignarme a mí"** o ejecuta el macro *"Asignarme y Atender Personalmente"*. **El bot se pausará automáticamente**.
- **Respuestas Rápidas:** Escribe `/` en la barra de mensajes para desplegar atajos:
  - `/yape`: Cuentas de banco y datos de Yape/Plin.
  - `/wifi`: Contraseña y red Wi-Fi.
  - `/ubicacion`: Dirección y enlace Google Maps.
  - `/horarios`: Políticas de check-in (14:00) y check-out (11:00).
  - `/aprobar`: Aprobar reserva y enviar PIN Smartlock.

### 2. Comandos Rápidos por WhatsApp
El administrador o recepcionista puede enviar comandos al WhatsApp del bot:
- `/aprobar <telefono>`: Aprueba el comprobante de pago de un cliente y le entrega su PIN de acceso.
- `/archivar <telefono>`: Silencia de inmediato un número para que el bot nunca le responda.
- `/ignorar <telefono>`: Agrega el número a la lista negra local y en Redis.

---

## 📊 Integración con Google Sheets

Para sincronizar la reportería con Google Sheets, consulta la guía paso a paso en:
[`google_sheets_template/setup_instructions.md`](./google_sheets_template/setup_instructions.md)

Pestañas incluidas:
1. `Habitaciones`: Catálogo, precios y estados operativos.
2. `Reservas`: Registro maestro de reservas con PIN y DNI.
3. `Leads_CRM`: Embudo de prospectos comerciales.
4. `Ventas`: Libro diario de ingresos y ventas confirmadas.
5. `Logs_Conversaciones`: Auditoría de mensajes para entrenamiento de ventas.
6. `Chats_Ignorados`: Lista de números personales y archivados.

---

## 🌐 Endpoints de API Disponibles (Bot)

| Método | Endpoint | Descripción |
| :--- | :--- | :--- |
| `GET` | `/health` | Estado de salud general, Redis, WhatsApp y reservas |
| `GET` | `/rooms` | Catálogo de habitaciones y tarifas |
| `GET` | `/reservations` | Listado completo de reservas registradas |
| `POST` | `/reservations/{phone}/approve` | Aprobación de pago y emisión de PIN |
| `GET` | `/sales` | Listado de ventas comerciales |
| `GET` | `/sales/analytics` | KPIs de ingresos, ticket promedio y tasa de conversión |
| `GET` | `/chat-logs` | Logs conversacionales para análisis de embudo |
| `GET` | `/ignored-phones` | Lista de teléfonos archivados e ignorados |
| `POST` | `/ignored-phones` | Agregar teléfono a ignorados |
| `DELETE` | `/ignored-phones/{phone}` | Desbloquear teléfono ignorado |

---

## 🧪 Pruebas de Calidad (QA) y Producción

Para ejecutar la suite automatizada de pruebas de producción y verificar el 100% de los componentes:

```bash
docker exec hotel_bot python tests/test_system.py
```

Resultados de las pruebas:
- Control estricto de fechas (pasadas y duración negativa).
- Extracción e indexación de DNI / Pasaporte.
- Disponibilidad dinámica en tiempo real.
- Registro de ventas y logs de conversación.
- Filtro de exclusión de chats archivados.

---

## 🔒 Auditoría de Seguridad y Privacidad

- **Aislamiento de Red:** PostgreSQL y Redis operan exclusivamente dentro de la red interna de Docker (`hotel_net`) sin puertos expuestos al tráfico de red externa.
- **Protección de Datos Personales (PII):** Los archivos con datos de huéspedes (`reservations.json`, `sales.json`, `chat_logs.json`) están excluidos del repositorio mediante `.gitignore`.
- **Idempotencia:** Bloqueos en Redis para evitar duplicidad de transacciones ante reintentos de red de WhatsApp.
- **Autenticación:** Evolution API y Chatwoot operan con API Keys y tokens individuales encriptados.

---

## 📄 Licencia
Este sistema está construido con componentes de código abierto (**Chatwoot Community**, **Evolution API**, **FastAPI**, **Redis**, **PostgreSQL**) y es **100% libre de costos de licenciamiento ($0/mes)**.
