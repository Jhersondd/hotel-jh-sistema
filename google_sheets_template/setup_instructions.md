# 📊 Configuración de Google Sheets para Hotel JH

Para que el sistema sincronice las habitaciones, disponibilidad y reservas con Google Sheets, sigue estos sencillos pasos:

---

## 1. Crear el Libro de Google Sheets

Crea una hoja de cálculo nueva en tu Google Drive (ejemplo: `Gestión Hotel JH`) y crea exactamente estas 4 pestañas (hojas) con sus encabezados:

### Pestaña 1: `Habitaciones`
Coloca estos nombres en la Fila 1:
| A | B | C | D | E | F |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `id_habitacion` | `tipo` | `precio_base` | `estado_operativo` | `id_cerradura_iot` | `descripcion` |

*Ejemplo de filas iniciales:*
* `HAB-101` | `Matrimonial Estándar` | `150.00` | `Disponible` | `lock_101` | `Cama Queen, baño privado, TV Smart, Wi-Fi 200MB, agua caliente.`
* `HAB-102` | `Doble Superior` | `190.00` | `Disponible` | `lock_102` | `2 camas de 1.5 plazas, baño privado, escritorio, vista panorámica.`
* `HAB-201` | `Suite Matrimonial Jacuzzi` | `280.00` | `Disponible` | `lock_201` | `Cama King, Jacuzzi privado, minibar, aire acondicionado, balcón.`

---

### Pestaña 2: `Reservas`
Coloca estos nombres en la Fila 1:
| A | B | C | D | E | F | G | H | I | J | K | L |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `id_reserva` | `id_habitacion` | `nombre_huesped` | `telefono_wa` | `fecha_ingreso` | `fecha_salida` | `pin_acceso` | `estado_reserva` | `monto_total` | `estado_pago` | `metodo_pago` | `fecha_creacion` |

---

### Pestaña 3: `Leads_CRM`
Coloca estos nombres en la Fila 1:
| A | B | C | D | E | F |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `id_lead` | `telefono_wa` | `nombre` | `etapa_embudo` | `agente_asignado` | `ultimo_contacto` |

---

### Pestaña 4: `Ventas` (Base de Ventas e Ingresos)
Coloca estos nombres en la Fila 1:
| A | B | C | D | E | F | G | H | I | J | K | L | M |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `ID_Venta` | `Fecha_Venta` | `ID_Reserva` | `Habitacion` | `Huesped` | `DNI` | `Telefono` | `Noches` | `Monto_Total` | `Metodo_Pago` | `Estado_Pago` | `Canal_Venta` | `Agente_Cierre` |

---

### Pestaña 5: `Logs_Conversaciones` (Auditoría de Chats y Optimización de Ventas)
Coloca estos nombres en la Fila 1:
| A | B | C | D | E | F | G | H |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `Timestamp` | `Telefono` | `Huesped` | `Rol` | `Mensaje` | `Estado_Flujo` | `Intencion_Detectada` | `Exito` |

---

### Pestaña 6: `Chats_Ignorados` (Contactos Personales / Archivados)
Coloca estos nombres en la Fila 1:
| A | B | C | D |
| :--- | :--- | :--- | :--- |
| `Telefono` | `Nombre` | `Motivo` | `Fecha_Agregado` |

---

## 2. Obtener el ID de la Hoja de Google Sheets
En la barra de direcciones de tu navegador, cuando tienes abierta la hoja, la URL se ve así:
```
https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit
```
El ID es el texto largo entre `/d/` y `/edit`:
👉 `1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms`

Copia ese ID y colócalo en tu archivo `.env`:
```env
GOOGLE_SHEET_ID=1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms
```

---

## 3. Crear Cuenta de Servicio Gratuita (Google Cloud)
1. Ve a [Google Cloud Console](https://console.cloud.google.com/) (100% gratis).
2. Crea un proyecto nuevo llamado `Hotel-JH`.
3. En el menú lateral, ve a **APIs y servicios > Biblioteca**, busca **Google Sheets API** y haz clic en **Habilitar**.
4. Ve a **APIs y servicios > Credenciales**, haz clic en **+ Crear credenciales > Cuenta de servicio**.
5. Ponle de nombre `hotel-sheets-bot` y haz clic en Crear y Continuar.
6. En la lista de cuentas de servicio, haz clic sobre la cuenta creada, ve a la pestaña **Claves (Keys)** > **Agregar clave** > **Crear clave nueva** > Selecciona **JSON** y descárgala.
7. Renombra ese archivo descargado a `credentials.json` y colócalo dentro de la carpeta `bot/` de este proyecto (`c:\Users\ACER\Documents\HOTEL JH\bot\credentials.json`).
8. Abre tu Google Sheet, haz clic en el botón verde **Compartir** (arriba a la derecha), pega el correo de la cuenta de servicio (ejemplo: `hotel-sheets-bot@hotel-jh.iam.gserviceaccount.com`) y dale permisos de **Editor**.
