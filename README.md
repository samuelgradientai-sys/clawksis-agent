![Clawksis](assets/banner.png)

# Clawksis

Agente de IA autónomo que corre en tu propio servidor. Habla con él desde
Telegram, WhatsApp o Discord mientras trabaja en un VPS. Aprende de cada
sesión, crea skills propias y mejora con el uso.

[![MIT](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)
[![Issues](https://img.shields.io/badge/Issues-GitHub-red?style=for-the-badge)](https://github.com/samuelgradientai-sys/clawksis-agent/issues)

---

## Índice

1. [Instalación](#instalación)
2. [Primeros pasos](#primeros-pasos)
3. [Proveedores de IA](#proveedores-de-ia)
4. [Comandos](#comandos)
5. [Dashboard](#dashboard)
6. [Mensajería](#mensajería-telegram-whatsapp-discord)
7. [Cron — tareas programadas](#cron--tareas-programadas)
8. [Self-hosted con dominio propio](#self-hosted-con-dominio-propio)
9. [Actualizar](#actualizar)
10. [Desinstalar](#desinstalar)
11. [Problemas comunes](#problemas-comunes)
12. [Licencia](#licencia)

---

## Instalación

### Linux, macOS, WSL2, Termux

```bash
curl -fsSL https://raw.githubusercontent.com/samuelgradientai-sys/clawksis-agent/main/scripts/install.sh | bash
```

> **Windows:** ejecuta esto en PowerShell:
> ```powershell
> iex (irm https://raw.githubusercontent.com/samuelgradientai-sys/clawksis-agent/main/scripts/install.ps1)
> ```
>
> **Android/Termux:** el mismo `curl` detecta Termux automáticamente.

El instalador descarga el código, crea un entorno Python, instala dependencias
de Node, construye el dashboard web y enlaza `clawk` en tu PATH.

> ⚠️ **Importante:** no ejecutes el instalador con `sudo`. Clawksis se instala
> como tu usuario. Si lo corres como root en Linux, el código irá a
> `/usr/local/lib/clawksis-agent` y el comando a `/usr/local/bin/clawk`.

Después de instalar recarga tu shell:

```bash
source ~/.bashrc   # o: source ~/.zshrc
```

---

## Primeros pasos

Sigue este orden la primera vez:

```bash
# 1. Configurar proveedor de IA y API key
clawk setup

# 2. Verificar que todo esté bien
clawk doctor

# 3. Hablar con el agente
clawk
```

`clawk setup` te guía paso a paso: elige proveedor, pide la API key y la
guarda de forma segura en `~/.clawksis/.env`. Si algo falla, `clawk doctor`
te dice exactamente qué corregir.

---

## Proveedores de IA

Cambia de proveedor en cualquier momento con `clawk model` — sin tocar código.

### Con login OAuth (sin API key)

| Proveedor | Comando |
|-----------|---------|
| **Claude** (Anthropic Pro/Max) | `clawk auth add anthropic --type oauth` |
| **OpenAI Codex** (ChatGPT Pro/Plus) | `clawk auth add openai-codex --type oauth` |
| **xAI Grok** (SuperGrok) | `clawk auth add xai-oauth --type oauth` |
| **Google Gemini** | `clawk auth add google-gemini-cli --type oauth` |
| **Qwen** | `clawk auth add qwen-oauth --type oauth` |
| **MiniMax** | `clawk auth add minimax-oauth --type oauth` |

### Con API key

| Proveedor | Comando | Variable `.env` |
|-----------|---------|-----------------|
| **OpenRouter** (200+ modelos) | `clawk auth add openrouter` | `OPENROUTER_API_KEY` |
| **OpenAI** directo | `clawk auth add openai-api` | `OPENAI_API_KEY` |
| **Anthropic** API key | `clawk auth add anthropic --type api-key` | `ANTHROPIC_API_KEY` |
| **DeepSeek** | `clawk auth add deepseek` | `DEEPSEEK_API_KEY` |
| **Google AI Studio** | `clawk auth add gemini` | `GEMINI_API_KEY` |
| **Hugging Face** | `clawk auth add huggingface` | `HF_TOKEN` |
| **NVIDIA NIM** | `clawk auth add nvidia` | `NVIDIA_API_KEY` |
| **LM Studio** (local) | `clawk model` → LM Studio | — |
| **Cualquier OpenAI-compatible** | `clawk model` → Custom | `base_url` + key |

> 💡 Para pegar una key sin prompt: `clawk auth add <proveedor> --api-key TU_KEY`

---

## Comandos

### Básicos

| Comando | Qué hace |
|---------|----------|
| `clawk` | Inicia el chat interactivo con el agente |
| `clawk -z "mensaje"` | Respuesta directa sin modo interactivo |
| `clawk -m <modelo>` | Usa un modelo específico solo para esa sesión |
| `clawk setup` | Wizard de configuración completa |
| `clawk status` | Estado de todos los componentes |
| `clawk doctor` | Diagnóstico del sistema |
| `clawk doctor --fix` | Diagnóstico con autocorrección |
| `clawk version` | Muestra la versión instalada |
| `clawk update` | Actualiza a la última versión |
| `clawk uninstall` | Desinstala (preserva `~/.clawksis/`) |

### Modelos y proveedores

| Comando | Qué hace |
|---------|----------|
| `clawk model` | Menú interactivo para elegir modelo y proveedor |
| `clawk auth add <proveedor>` | Agrega credenciales de un proveedor |
| `clawk auth list` | Lista todas las credenciales configuradas |
| `clawk auth status <proveedor>` | Ver estado de autenticación |
| `clawk auth logout <proveedor>` | Cierra sesión y borra credenciales |
| `clawk fallback` | Gestiona proveedores de respaldo |

### Configuración

| Comando | Qué hace |
|---------|----------|
| `clawk config show` | Muestra la configuración actual |
| `clawk config edit` | Abre `config.yaml` en tu editor |
| `clawk config set <clave> <valor>` | Cambia un valor de configuración |
| `clawk config path` | Muestra la ruta del archivo de configuración |
| `clawk config env-path` | Muestra la ruta del archivo `.env` |
| `clawk config check` | Verifica configuración faltante o desactualizada |
| `clawk config migrate` | Actualiza configuración con nuevas opciones |

### Personalidad, memoria y perfil

| Comando | Qué hace |
|---------|----------|
| `clawk soul` | Ver o editar la personalidad del agente (SOUL.md) |
| `clawk memory show` | Ver la memoria del agente |
| `clawk memory edit` | Editar la memoria del agente |
| `clawk user` | Ver el perfil del usuario |
| `clawk user edit` | Editar el perfil del usuario |

### Sesiones

| Comando | Qué hace |
|---------|----------|
| `clawk sessions list` | Lista las sesiones recientes |
| `clawk sessions browse` | Explorador interactivo de sesiones |
| `clawk sessions rename <id>` | Cambia el nombre de una sesión |
| `clawk sessions export` | Exporta sesiones a archivo JSONL |
| `clawk sessions delete <id>` | Elimina una sesión específica |
| `clawk sessions prune` | Elimina sesiones antiguas |
| `clawk sessions stats` | Estadísticas del historial de sesiones |
| `clawk sessions optimize` | Libera espacio en disco (VACUUM) |

### Cron — tareas programadas

| Comando | Qué hace |
|---------|----------|
| `clawk cron list` | Lista todas las tareas programadas |
| `clawk cron add` | Crea una nueva tarea programada |
| `clawk cron edit <id>` | Edita una tarea existente |
| `clawk cron pause <id>` | Pausa una tarea |
| `clawk cron resume <id>` | Reanuda una tarea pausada |
| `clawk cron run <id>` | Ejecuta una tarea en el próximo tick |
| `clawk cron remove <id>` | Elimina una tarea |
| `clawk cron status` | Verifica si el scheduler está corriendo |
| `clawk cron tick` | Ejecuta las tareas pendientes una vez y sale |

**Ejemplo — reporte diario por Telegram:**

```bash
# Crear una tarea que envíe un resumen cada día a las 8am
clawk cron add \
  --schedule "0 8 * * *" \
  --prompt "Genera un resumen del día y envíalo por Telegram" \
  --delivery telegram
```

### Mensajería y proactividad

| Comando | Qué hace |
|---------|----------|
| `clawk gateway run` | Inicia el gateway en primer plano |
| `clawk gateway install` | Instala el gateway como servicio del sistema |
| `clawk gateway status` | Estado del gateway |
| `clawk send` | Envía un mensaje a una plataforma desde scripts o CI |
| `clawk webhook` | Gestiona webhooks dinámicos |
| `clawk pairing` | Códigos de autorización para nuevos usuarios |
| `clawk whatsapp` | Configuración de integración WhatsApp |
| `clawk slack` | Configuración de integración Slack |

### Capacidades (skills, plugins, MCP)

| Comando | Qué hace |
|---------|----------|
| `clawk skills` | Buscar, instalar y gestionar skills |
| `clawk bundles` | Crear y gestionar bundles de skills |
| `clawk plugins` | Instalar, actualizar y quitar plugins |
| `clawk curator` | Mantenimiento automático de skills |
| `clawk mcp` | Gestionar servidores MCP |
| `clawk tools` | Activar o desactivar herramientas |

### Backup y mantenimiento

| Comando | Qué hace |
|---------|----------|
| `clawk backup` | Crea un backup de `~/.clawksis/` en un zip |
| `clawk import` | Restaura un backup desde un zip |
| `clawk checkpoints` | Inspeccionar o limpiar checkpoints |
| `clawk security` | Auditoría de seguridad de dependencias (OSV.dev) |
| `clawk logs` | Ver y filtrar logs del agente |
| `clawk insights` | Estadísticas de uso y analytics |

### Avanzado

| Comando | Qué hace |
|---------|----------|
| `clawk profile` | Gestiona perfiles (instancias aisladas) |
| `clawk acp` | Protocolo de comunicación entre agentes (ACP) |
| `clawk lsp` | Gestión del servidor de lenguaje |
| `clawk proxy` | Proxy local compatible con OpenAI para proveedores OAuth |
| `clawk hooks` | Inspeccionar y gestionar hooks de shell |
| `clawk kanban` | Tablero de colaboración (tareas, links, comentarios) |
| `clawk prompt-size` | Estima el tamaño del prompt antes de enviarlo |
| `clawk dump` | Resumen del sistema para soporte |

---

## Dashboard

El dashboard es la interfaz web del agente. Corre localmente en el VPS en
`127.0.0.1:9119` y **nunca se expone directamente a internet**.

### Acceso seguro desde tu computador (recomendado)

La forma más segura de abrir el dashboard es a través de un túnel SSH.
No abre ningún puerto público — la conexión va cifrada por SSH:

```bash
# Desde tu computador local
clawk dashboard --remote usuario@ip-del-vps
```

O manualmente desde PowerShell en Windows:

```powershell
ssh -L 9119:127.0.0.1:9119 clawksis-vps
```

Luego abre `http://localhost:9119` en tu navegador. El dashboard se mantiene
actualizado en tiempo real mientras el túnel esté abierto.

### Acceso con dominio propio (opcional)

Si quieres acceder desde cualquier lugar sin abrir una terminal, puedes
configurar un reverse proxy con nginx y HTTPS:

```bash
# 1. Instalar y configurar
clawk setup

# 2. Instalar gateway como servicio
sudo clawk gateway install --system
clawk gateway status
```

Configuración nginx (`/etc/nginx/sites-available/clawksis`):

```nginx
server {
    listen 443 ssl;
    server_name tudominio.com;

    ssl_certificate     /etc/letsencrypt/live/tudominio.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/tudominio.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:9119;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d tudominio.com
```

Configura la contraseña del dashboard en `~/.clawksis/config.yaml`:

```yaml
dashboard:
  password: "tu-password-segura"
```

---

## Mensajería (Telegram, WhatsApp, Discord)

```bash
# Telegram — necesitas un bot token de @BotFather
clawk gateway install --telegram --token TU_BOT_TOKEN
clawk gateway status
```

Agrega los tokens en `~/.clawksis/.env`:

```bash
TELEGRAM_BOT_TOKEN=tu_token
DISCORD_BOT_TOKEN=tu_token
```

---

## Cron — tareas programadas

Clawksis incluye un scheduler integrado. Las tareas pueden entregar resultados
por cualquier plataforma de mensajería configurada.

```bash
# Ver tareas activas
clawk cron list

# Crear una tarea (el agente te guía paso a paso)
clawk cron add

# Ver si el scheduler está corriendo
clawk cron status
```

**Ejemplos de tareas útiles:**

```bash
# Reporte semanal de ventas todos los lunes a las 7am
clawk cron add --schedule "0 7 * * 1" \
  --prompt "Genera el reporte semanal de ventas y envíalo por Telegram"

# Backup automático cada noche a las 2am
clawk cron add --schedule "0 2 * * *" \
  --prompt "Haz un backup de la configuración"

# Resumen de noticias cada mañana
clawk cron add --schedule "0 8 * * *" \
  --prompt "Busca las noticias más importantes del día y envíamelas"
```

---

## Self-hosted con dominio propio

Ver sección [Dashboard — acceso con dominio propio](#acceso-con-dominio-propio-opcional).

---

## Actualizar

```bash
clawk update
```

Actualiza desde el repositorio y preserva tu configuración en `~/.clawksis/`.

---

## Desinstalar

```bash
clawk uninstall
```

Elimina el código y el comando `clawk`. Tu configuración en `~/.clawksis/`
no se toca — tus sesiones, memoria y skills quedan guardados.

---

## Problemas comunes

**`clawk` no se encuentra después de instalar:**

```bash
source ~/.bashrc   # o: source ~/.zshrc
clawk doctor --fix
```

**Error de API key:**

```bash
clawk setup        # reconfigurar desde el wizard
# o editar directamente:
clawk config edit
```

**Gateway no arranca:**

```bash
clawk gateway status   # ver el error específico
clawk doctor           # diagnóstico completo
```

**El dashboard no carga:**

```bash
clawk status           # ver si el dashboard está corriendo
clawk dashboard        # iniciarlo manualmente
```

**Diagnóstico completo:**

```bash
clawk doctor
```

---

## Licencia

MIT. Basado en [hermes-agent](https://github.com/NousResearch/hermes-agent)
de Nous Research — copyright original conservado en `LICENSE`.

Modificaciones adicionales © 2026 Gradient AI / Samuel Gomez.