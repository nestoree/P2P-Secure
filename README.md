# SecureChat 🔐

Chat grupal en tiempo real, cifrado y autohospedado. Se levanta con un solo comando de Python y es accesible desde cualquier navegador en la red local.

---

## Características

- **Sin registro** — solo elige un nombre y entra
- **Nombres únicos** — el servidor rechaza nombres ya en uso (case-insensitive)
- **Sin límite de usuarios** — todos los que quieran pueden conectarse
- **Lista de usuarios con IP** — sidebar con `nombre <ip>` de cada conectado
- **Indicador de escritura** — muestra quién está escribiendo en tiempo real
- **Un solo puerto** — HTTP y WebSocket comparten el puerto 8765
- **Auto-instala dependencias** — instala `aiohttp` solo si no está disponible

---

## Requisitos

- Python 3.8 o superior
- `aiohttp` (se instala automáticamente si no está)

---

## Instalación y uso

```bash
# Clonar o descargar el archivo
# (opcional) instalar dependencia manualmente
pip install aiohttp

# Ejecutar
python3 secure-chat.py
```

El navegador se abre solo en `http://localhost:8765`.

Para acceder desde **otros dispositivos en la misma red**, usa la IP local que muestra el servidor al arrancar:

```
  ┌──────────────────────────────────────────────┐
  │           SecureChat  🔐                      │
  ├──────────────────────────────────────────────┤
  │  Local:      http://localhost:8765            │
  │  Red local:  http://192.168.1.x:8765          │
  └──────────────────────────────────────────────┘
```

---

## Cómo funciona

### Seguridad

| Capa | Detalle |
|------|---------|
| Transporte | WebSocket sobre HTTP (usa HTTPS/WSS para cifrado en tránsito) |
| Unicidad de nombres | Verificación case-insensitive en el servidor |
| IP visible | Cada usuario ve la IP de los demás en el sidebar |
| Sin persistencia | Los mensajes no se almacenan; al cerrar el servidor se pierden |

> Para habilitar **HTTPS/WSS** (cifrado en tránsito real), coloca el servidor detrás de un proxy inverso como nginx o Caddy con certificado TLS.

---

## Estructura del archivo

`secure_chat.py` es un único archivo autocontenido:

```
secure_chat.py
├── Dependencias          auto-instalación de aiohttp
├── Estado global         dict de clientes conectados {ws → {nick, ip}}
├── Helpers               broadcast, send, online_list, get_ip
├── ws_handler()          lógica WebSocket (join, msg, typing)
├── HTML                  interfaz completa embebida (HTML + CSS + JS)
├── http_handler()        sirve el HTML en GET /
└── main()                arranca el servidor en 0.0.0.0:8765
```

---

## Mensajes WebSocket

### Cliente → Servidor

| Tipo | Campos | Descripción |
|------|--------|-------------|
| `join` | `nick` | Solicitar entrada con ese nombre |
| `msg` | `text` | Enviar mensaje (máx. 4000 caracteres) |
| `typing` | `state` (bool) | Indicar si está escribiendo |

### Servidor → Cliente

| Tipo | Campos | Descripción |
|------|--------|-------------|
| `joined` | `nick`, `online` | Entrada aceptada |
| `error` | `msg` | Nombre en uso u otro error |
| `msg` | `nick`, `text`, `ts` | Mensaje de alguien |
| `user_joined` | `nick`, `online` | Nuevo usuario conectado |
| `user_left` | `nick`, `online` | Usuario desconectado |
| `typing` | `nick`, `state` | Estado de escritura de un peer |

---

## Acceso desde internet (opcional)

Para exponer el chat fuera de la red local sin configurar routers, usa un túnel:

```bash
# Con ngrok
ngrok http 8765

# Con Cloudflare Tunnel
cloudflared tunnel --url http://localhost:8765
```

Comparte la URL que te den con quien quieras.

---

## Cambiar el puerto

Edita la línea al final del archivo:

```python
PORT = 8765  # ← cámbialo aquí
```

---

## Limitaciones conocidas

- Los mensajes **no se persisten** — si el servidor se reinicia, el historial se pierde
- No hay autenticación de usuarios — cualquiera en la red puede entrar con cualquier nombre libre
- El cifrado en tránsito requiere configurar TLS externamente (nginx, Caddy, etc.)
- Pensado para redes locales de confianza o túneles controlados

---

## Licencia

Uso libre. Sin garantías.
