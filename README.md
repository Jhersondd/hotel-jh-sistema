# 🏨 Sistema Hotelero Autónomo - Hotel JH ($0 Costo)

Sistema de gestión hotelera autónomo con interfaz WhatsApp, consola comercial CRM multiagente (Chatwoot), base de datos operativa en Google Sheets y control de cerraduras inteligentes (TTLock).

---

## 🚀 Arquitectura del Sistema
* **Evolution API v2:** Conector de WhatsApp Web sin costos de Meta por conversación.
* **Chatwoot Community:** CRM comercial multiagente para asesores humanos con soporte para handover.
* **Hotel Bot (FastAPI):** Orquestador de reservas, máquina de estados, retención de 15 minutos en Redis y entrega de llaves digitales.
* **PostgreSQL 16 & Redis 7:** Almacenamiento transaccional de alta velocidad y bloqueos atómicos contra sobreventas (*overbooking*).
* **Google Sheets:** Base de datos operativa y de reportería para la administración.
* **TTLock API:** Emisión autónoma de códigos numéricos para las cerraduras inteligentes.

---

## 🛠️ Requisitos Previos
* **Docker Desktop** (con WSL2 activado en Windows) o **Docker** en Linux.
* Número de WhatsApp activo para el hotel (puede ser el que usas en el teléfono).

---

## 📦 Puesta en Marcha Rápida (Paso a Paso)

### Paso 1: Inicializar la Base de Datos de Chatwoot (Solo la 1ª vez)
Abre PowerShell o terminal en esta carpeta y ejecuta:
```powershell
docker compose run --rm chatwoot_web bundle exec rails db:chatwoot_prepare
```
*(Esto crea las tablas de usuarios y configuraciones en PostgreSQL).*

---

### Paso 2: Iniciar Todos los Contenedores
```powershell
docker compose up -d
```
Verifica que los contenedores estén activos:
```powershell
docker compose ps
```

---

### Paso 3: Configurar Chatwoot (Consola de Asesores)
1. Abre tu navegador en `http://localhost:3000`.
2. Completa el registro del Administrador del Hotel.
3. Ve a **Ajustes de Perfil** (abajo a la izquierda) y copia tu **Token de Acceso de Usuario** (*Access Token*).
4. Abre el archivo `.env` y pega tu token en:
   ```env
   CHATWOOT_API_TOKEN=tu_token_aqui
   ```
5. Reinicia el bot para que tome el token:
   ```powershell
   docker compose restart hotel_bot
   ```

---

### Paso 4: Conectar WhatsApp (Evolution API)
1. Abre tu navegador o ejecuta en PowerShell para crear la instancia de WhatsApp conectada a Chatwoot:
```powershell
Invoke-RestMethod -Uri "http://localhost:8080/instance/create" -Method Post -Headers @{"apikey"="EvolutionHotelSecretKey2026!"; "Content-Type"="application/json"} -Body '{
  "instanceName": "hotel_principal",
  "token": "hotel2026",
  "qrcode": true,
  "chatwoot_account_id": 1,
  "chatwoot_token": "TU_CHATWOOT_API_TOKEN",
  "chatwoot_url": "http://chatwoot_web:3000",
  "chatwoot_sign_msg": true,
  "chatwoot_reopen_conversation": true,
  "chatwoot_conversation_pending": true
}'
```
2. Obtén el código QR para escanear con tu celular:
   * Visita en tu navegador: `http://localhost:8080/instance/connect/hotel_principal`
   * O abre WhatsApp en tu teléfono > **Dispositivos vinculados** > **Vincular un dispositivo** y escanea el QR.

---

### Paso 5: Configurar el Webhook del Bot Hotelero
Dile a Evolution API que envíe los mensajes entrantes a nuestro bot hotelero:
```powershell
Invoke-RestMethod -Uri "http://localhost:8080/webhook/set/hotel_principal" -Method Post -Headers @{"apikey"="EvolutionHotelSecretKey2026!"; "Content-Type"="application/json"} -Body '{
  "webhook": {
    "enabled": true,
    "url": "http://hotel_bot:5000/webhook/evolution",
    "byEvents": false,
    "events": ["MESSAGES_UPSERT"]
  }
}'
```

---

## 🤖 ¿Cómo interactúa el Huésped y el Asesor?

1. **Flujo Autónomo:**
   * El cliente escribe `"Hola"` a tu WhatsApp.
   * El bot muestra el menú interactivo con tarifas de habitaciones.
   * El cliente elige fechas (ej. `2026-11-15 al 2026-11-17`).
   * El bot verifica disponibilidad en Google Sheets y aplica un **bloqueo de 15 minutos en Redis** para que nadie más tome esa habitación mientras paga.
   * Al confirmar pago, el bot genera el PIN de la cerradura inteligente (TTLock) y se lo envía al cliente junto con la ubicación y las instrucciones.
   * La reserva queda registrada en la hoja de Google Sheets.

2. **Intervención Humana (Handover):**
   * Si el cliente escribe `3` ("Hablar con un asesor comercial"), el bot transfiere la conversación a la bandeja de **Chatwoot**.
   * Cualquier asesor de ventas puede responder desde la consola web `http://localhost:3000`.
   * **El bot se silencia automáticamente** mientras el asesor humano atiende al cliente.

---

## 📊 Configuración de Google Sheets
Revisa la guía detallada en [`google_sheets_template/setup_instructions.md`](./google_sheets_template/setup_instructions.md).
