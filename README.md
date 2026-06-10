<p align="center">
  <img src="assets/banner.png" alt="Clawksis" width="80%">
</p>

# Clawksis

Agente de IA autónomo que corre en tu propio servidor. Habla con él desde Telegram, WhatsApp o Discord mientras trabaja en un VPS. Aprende de cada sesión, crea skills propias y mejora con el uso.

<p align="center">
  <a href="https://github.com/samuelgradientai-sys/clawksis-agent/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="MIT"></a>
  <a href="https://github.com/samuelgradientai-sys/clawksis-agent/issues"><img src="https://img.shields.io/badge/Issues-GitHub-red?style=for-the-badge" alt="Issues"></a>
</p>

---

## Instalación

```bash
curl -fsSL https://raw.githubusercontent.com/samuelgradientai-sys/clawksis-agent/main/scripts/install.sh | bash
```

> **Windows:** `iex (irm https://raw.githubusercontent.com/samuelgradientai-sys/clawksis-agent/main/scripts/install.ps1)`
>
> **Android/Termux:** el mismo `curl` detecta Termux automáticamente.

El instalador descarga el código, crea un virtualenv Python, instala dependencias de Node, construye el dashboard web y enlaza `clawk` en tu PATH.

---

## Primeros pasos

```bash
# 1. Configurar proveedor LLM y API key
clawk setup

# 2. Hablar con el agente
clawk

# 3. Verificar instalación
clawk doctor
```

`clawk setup` te pregunta qué proveedor usar (OpenAI, Anthropic, OpenRouter, DeepSeek, Gemini u otro), te pide la API key y configura el modelo. Todo queda en `~/.clawksis/.env` y `~/.clawksis/config.yaml`.

---

## Proveedores soportados

**Comando para conectar cualquiera:** `clawk model` (menú interactivo que te lleva de la mano), o directo por proveedor con **`clawk auth add <id>`** (los de las tablas). `clawk auth add` auto-detecta: los OAuth hacen el login en el navegador, los de API key te piden la key y la guardan en `~/.clawksis/.env`. `auto` (default) usa lo que tengas configurado.

### Con login OAuth (sin API key)
| Proveedor | id | Cómo conectarlo |
|---|---|---|
| **Claude** (Anthropic, Pro/Max) | `anthropic` | `clawk auth add anthropic --type oauth` |
| **OpenAI Codex** (ChatGPT Pro/Plus) | `openai-codex` | `clawk auth add openai-codex --type oauth` |
| **xAI Grok** (SuperGrok / Premium+) | `xai-oauth` | `clawk auth add xai-oauth --type oauth` |
| **Google Gemini** | `google-gemini-cli` | `clawk auth add google-gemini-cli --type oauth` |
| **Qwen** | `qwen-oauth` | `clawk auth add qwen-oauth --type oauth` |
| **MiniMax** | `minimax-oauth` | `clawk auth add minimax-oauth --type oauth` |
| **GitHub Copilot** | `copilot` | `GITHUB_TOKEN` |

### Con API key (te pide la key y la guarda en `~/.clawksis/.env`)
| Proveedor | Comando | Variable `.env` |
|---|---|---|
| **OpenRouter** (acceso a casi todo) | `clawk auth add openrouter` | `OPENROUTER_API_KEY` |
| **OpenAI** directo | `clawk auth add openai-api` | `OPENAI_API_KEY` |
| **Anthropic** (API key) | `clawk auth add anthropic --type api-key` | `ANTHROPIC_API_KEY` |
| **DeepSeek** | `clawk auth add deepseek` | `DEEPSEEK_API_KEY` |
| **Google AI Studio** | `clawk auth add gemini` | `GEMINI_API_KEY` / `GOOGLE_API_KEY` |
| **z.ai / ZhipuAI GLM** | `clawk auth add zai` | `GLM_API_KEY` |
| **Kimi / Moonshot** | `clawk auth add kimi-coding` | `KIMI_API_KEY` |
| **MiniMax** global / China | `clawk auth add minimax` (o `minimax-cn`) | `MINIMAX_API_KEY` / `MINIMAX_CN_API_KEY` |
| **Hugging Face** | `clawk auth add huggingface` | `HF_TOKEN` |
| **NVIDIA NIM** | `clawk auth add nvidia` | `NVIDIA_API_KEY` |
| **Xiaomi MiMo** | `clawk auth add xiaomi` | `XIAOMI_API_KEY` |
| **Arcee AI** | `clawk auth add arcee` | `ARCEEAI_API_KEY` |
| **Ollama Cloud** | `clawk auth add ollama-cloud` | `OLLAMA_API_KEY` |
| **KiloCode** | `clawk auth add kilocode` | `KILOCODE_API_KEY` |
| **Azure / Foundry** | `clawk auth add azure-foundry` | API key o Entra ID |
| **LM Studio** (local) | `clawk model` → LM Studio | opcional `LM_API_KEY` |
| **Cualquier OpenAI-compatible** | `clawk model` → Custom | `base_url` + key |

> 💡 Tip: `clawk auth add <id> --api-key TU_KEY` la pega sin prompt. Para ver/cambiar el modelo después: `clawk model`.

## Comandos

### Básicos
| Comando | Qué hace |
|---|---|
| `clawk` | Chat interactivo con el agente en la terminal |
| `clawk setup` | Wizard de configuración (proveedor, modelo, API key) |
| `clawk -z "mensaje"` | Respuesta directa one-shot (sin modo interactivo) |
| `clawk -m <modelo>` | Override de modelo para esa sesión |
| `clawk model` | Elegir modelo y proveedor por defecto |
| `clawk tools` | Activar/desactivar herramientas por plataforma |
| `clawk status` | Estado de todos los componentes |
| `clawk doctor` · `clawk doctor --fix` | Diagnóstico / autocorrección |
| `clawk update` | Actualizar a la última versión |
| `clawk dashboard` | Abrir el dashboard web |
| `clawk dashboard --remote USER@HOST` | Abrir un dashboard remoto vía túnel SSH (sin `ssh -L` manual; agregá `--start` para arrancarlo en el remoto, `--ssh-opt` para opciones de ssh) |
| `clawk uninstall` | Desinstalar (preserva `~/.clawksis/`) |

### Login y credenciales
| Comando | Qué hace |
|---|---|
| `clawk auth add anthropic --type oauth` | **Login con Claude** (suscripción Pro/Max, estilo Claude Code). En remoto/headless agregá `--manual-paste` |
| `clawk auth add openai-codex --type oauth` | **Login con Codex** (ChatGPT Pro/Plus, device-code) |
| `clawk auth add <provider> --type oauth` | Otros OAuth: `xai-oauth`, `qwen-oauth`, `google-gemini-cli`, `minimax-oauth` |
| `clawk auth list` | Listar credenciales del pool (marca la activa) |
| `clawk auth status <provider>` | Ver si estás logueado, scope y expiración |
| `clawk auth logout <provider>` | Cerrar sesión y limpiar credenciales |
| `clawk config edit` | Editar `config.yaml` en tu editor |

> 💡 Los logins OAuth (Claude, Codex…) son 100% navegador — **no instalan ninguna CLI**.

### Personalidad, memoria y perfil
| Comando | Qué hace |
|---|---|
| `clawk soul` | Ver/editar la **personalidad** del agente (SOUL.md) |
| `clawk memory show` · `clawk memory edit` | Ver / **editar** la memoria del agente (MEMORY.md) |
| `clawk user` · `clawk user edit` | Ver / **editar** el perfil del usuario (USER.md) |

### Mensajería y proactividad
| Comando | Qué hace |
|---|---|
| `clawk gateway run` | Gateway de mensajería en primer plano |
| `clawk gateway install` | Gateway como servicio del sistema (boot + auto-restart) |
| `clawk gateway status` | Ver si el gateway está corriendo |
| `clawk cron` | Tareas programadas (`list`, `add`, `trigger`…) |
| `clawk webhook` | Webhooks dinámicos (suscripciones a eventos) |
| `clawk pairing` | Códigos de pairing para autorizar usuarios |
| `clawk send` | Enviar un mensaje a una plataforma (scripts/cron/CI) |
| `clawk whatsapp` · `clawk slack` | Integración WhatsApp / Slack |

### Capacidades (skills, plugins, MCP)
| Comando | Qué hace |
|---|---|
| `clawk skills` | Buscar, instalar y gestionar skills |
| `clawk plugins` | Instalar / actualizar / quitar plugins |
| `clawk mcp` | Gestionar servidores MCP (y correr Clawksis como MCP server) |
| `clawk bundles` | Bundles de skills (alias de varias skills) |
| `clawk curator` | Mantenimiento automático de skills (status/run/pause) |

### Sesiones y mantenimiento
| Comando | Qué hace |
|---|---|
| `clawk sessions` | Historial de sesiones (list/rename/export/prune/delete) |
| `clawk logs` | Ver y filtrar logs |
| `clawk insights` | Uso y analytics |
| `clawk backup` · `clawk import` | Backup / restaurar `~/.clawksis/` |
| `clawk checkpoints` | Inspeccionar / limpiar checkpoints |
| `clawk profile` | Perfiles (instancias aisladas de Clawksis) |
| `clawk security` | Auditoría supply-chain (OSV.dev) |
| `clawk kanban` | Tablero de colaboración (tareas, links, comentarios) |
| `clawk version` | Mostrar versión |

---

## Self-hosted: acceso por dominio

### 1. Instalar y configurar

```bash
curl -fsSL https://raw.githubusercontent.com/samuelgradientai-sys/clawksis-agent/main/scripts/install.sh | bash
clawk setup
```

### 2. Gateway como servicio (arranca solo al reiniciar)

```bash
sudo clawk gateway install --system
clawk gateway status
```

### 3. Reverse proxy con nginx + HTTPS

El dashboard corre en `127.0.0.1:9119` por defecto. Config nginx:

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

### 4. Login y dashboard

Configura la contraseña del dashboard en `~/.clawksis/config.yaml`:

```yaml
dashboard:
  password: "tu-password-aqui"
```

Luego entra a `https://tudominio.com` — verás el login y después el dashboard.

---

## Mensajería (Telegram, WhatsApp, Discord)

```bash
# Telegram — requiere bot token de @BotFather
clawk gateway install --telegram --token TU_BOT_TOKEN

# Ver estado
clawk gateway status
```

Agrega tokens en `~/.clawksis/.env`:

```bash
TELEGRAM_BOT_TOKEN=tu_token
DISCORD_BOT_TOKEN=tu_token
```

---

## Problemas comunes

**`clawk` no se encuentra después de instalar:**
```bash
source ~/.bashrc   # o ~/.zshrc / ~/.config/fish/config.fish
clawk doctor --fix
```

**Error de API key:**
```bash
clawk setup        # reconfigurar desde el wizard
# o editar directamente:
nano ~/.clawksis/.env
```

**Gateway no arranca:**
```bash
clawk gateway status   # ver el error específico
clawk doctor           # diagnóstico completo
```

**Diagnóstico completo:**
```bash
clawk doctor
```
Muestra Python version, configuración, herramientas disponibles y qué configurar para activar funciones opcionales (búsqueda web, generación de imágenes, etc.).

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

Elimina el código y el comando `clawk`. Tu configuración en `~/.clawksis/` no se toca.

---

## Licencia

MIT. Basado en [hermes-agent](https://github.com/NousResearch/hermes-agent) de Nous Research — copyright original conservado en `LICENSE`.

Modificaciones adicionales © 2026 Gradient AI / Samuel Gomez.
