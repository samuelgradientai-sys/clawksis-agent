<p align="center">
  <img src="assets/banner.png" alt="Clawksis" width="80%">
</p>

<h1 align="center">Clawksis</h1>

<p align="center">
  <b>Tu agente de IA autónomo, self-hosted.</b><br>
  Hablale desde Telegram, WhatsApp o Discord mientras trabaja en tu VPS.<br>
  Aprende de cada sesión, crea sus propias skills y mejora con el uso.
</p>

<p align="center">
  <a href="https://github.com/samuelgradientai-sys/clawksis-agent/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="MIT"></a>
  <a href="https://github.com/samuelgradientai-sys/clawksis-agent/issues"><img src="https://img.shields.io/badge/Issues-GitHub-red?style=for-the-badge" alt="Issues"></a>
  <a href="https://github.com/samuelgradientai-sys/clawksis-agent/blob/main/DOCUMENTATION.md"><img src="https://img.shields.io/badge/Docs-Timeline-6C4FD6?style=for-the-badge" alt="Documentación"></a>
  <a href="https://www.clawksis.com/"><img src="https://img.shields.io/badge/Web-clawksis.com-blue?style=for-the-badge" alt="Website"></a>
</p>

---

## Tabla de contenidos

- [Características](#características)
- [Instalación](#instalación)
- [Primeros pasos](#primeros-pasos)
- [Proveedores soportados](#proveedores-soportados)
- [Comandos](#comandos)
- [Self-hosted: acceso por dominio](#self-hosted-acceso-por-dominio)
- [Mensajería](#mensajería)
- [Problemas comunes](#problemas-comunes)
- [Actualizar](#actualizar) · [Desinstalar](#desinstalar) · [Licencia](#licencia)

---

## Características

- 🏠 **100% self-hosted** — corre en tu propio servidor o VPS. Vos tenés el control: sin nube de terceros y sin límites impuestos por nadie.
- 💬 **Mensajería multiplataforma** — chateá con tu agente desde Telegram, WhatsApp, Discord, Slack o Signal. Te responde donde estés.
- 🧠 **Aprende y evoluciona** — recuerda contexto entre sesiones (`MEMORY.md`), tiene personalidad propia (`SOUL.md`) y crea sus propias skills con el uso.
- 🔌 **+30 proveedores LLM** — Claude, GPT, Gemini, Grok, DeepSeek, Qwen, Kimi y más. Conectá por **OAuth** (usá tu suscripción Claude Pro/Max o ChatGPT Plus, sin API key) o por API key.
- ⏰ **Proactivo, no solo reactivo** — tareas programadas (cron), webhooks y hooks de shell: el agente te escribe **a vos** cuando pasa algo.
- 🧩 **Extensible** — skills, plugins, servidores MCP y bundles. Un ecosistema que crece con vos.
- 🖥️ **CLI + Dashboard web + App de escritorio** — usalo como prefieras, incluido acceso remoto por dominio con HTTPS.
- 📦 **Multiplataforma** — Linux, macOS, Windows y Android (Termux).

---

## Instalación

```bash
curl -fsSL https://raw.githubusercontent.com/samuelgradientai-sys/clawksis-agent/main/scripts/install.sh | bash
clawk setup
```

> **Windows:** `iex (irm https://raw.githubusercontent.com/samuelgradientai-sys/clawksis-agent/main/scripts/install.ps1)`
>
> **Android/Termux:** el mismo `curl` detecta Termux automáticamente.

El instalador descarga el código, crea un virtualenv de Python, instala las dependencias de Node, construye el dashboard web y enlaza `clawk` en tu `PATH`.

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

La forma más fácil de conectar cualquier proveedor es **`clawk model`** (menú interactivo que te lleva de la mano). Para ir directo, usá **`clawk auth add <id>`**: auto-detecta el tipo, hace el login OAuth en el navegador o te pide la API key y la guarda en `~/.clawksis/.env`. El valor por defecto (`auto`) usa lo que tengas configurado.

> 💡 **Tip:** `clawk auth add <id> --api-key TU_KEY` la pega sin prompt. Para ver o cambiar el modelo después: `clawk model`.

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

> 💡 Los logins OAuth (Claude, Codex…) son 100% navegador — **no instalan ninguna CLI**.

### Con API key (Clawksis te pide la key y la guarda en `~/.clawksis/.env`)

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
| **Modelos locales (Ollama)** | `clawk cookbook` → ver qué corre, bajar y usar | Ollama instalado |
| **Cualquier OpenAI-compatible** | `clawk model` → Custom | `base_url` + key |

---

## Comandos

> 💡 Todos los comandos tienen ayuda integrada: `clawk <comando> --help` muestra subcomandos y flags completos.

### Esenciales

| Comando | Qué hace |
|---|---|
| `clawk` | Chat interactivo con el agente en la terminal |
| `clawk setup` | Wizard de configuración (proveedor, modelo, API key) |
| `clawk -z "mensaje"` | Respuesta directa one-shot (sin modo interactivo) |
| `clawk model` | Elegir modelo y proveedor por defecto |
| `clawk cookbook` | Ver/buscar (`clawk cookbook qwen`) qué modelos abiertos corren en tu máquina, bajarlos (Ollama) y usarlos |
| `clawk status` | Estado de todos los componentes |
| `clawk doctor` · `clawk doctor --fix` | Diagnóstico / autocorrección |
| `clawk update` | Actualizar a la última versión |
| `clawk dashboard` | Abrir el dashboard web |
| `clawk gateway install` | Mensajería como servicio del sistema |
| `clawk cron add "<schedule>" "<prompt>"` | Programar una tarea recurrente |
| `clawk skills` | Buscar, instalar y gestionar skills |

La referencia completa está organizada por categoría — expandí la que necesites:

<details>
<summary><b>Básicos y sesión</b></summary>

| Comando | Qué hace |
|---|---|
| `clawk -m <modelo>` | Override de modelo para esa sesión |
| `clawk -c` · `clawk -r <sesión>` | Continuar la última sesión / retomar una sesión por nombre |
| `clawk fallback` | Proveedores de respaldo (se usan cuando el modelo primario falla) |
| `clawk tools` | Activar/desactivar herramientas por plataforma (incluye CLIs de coding externas: Codex, Claude Code, OpenCode) |
| `clawk dashboard --remote USER@HOST` | Abrir un dashboard remoto vía túnel SSH (sin `ssh -L` manual; agregá `--start` para arrancarlo en el remoto, `--ssh-opt` para opciones de ssh) |
| `clawk desktop` (alias `gui`) | Compilar y abrir la app de escritorio nativa |
| `clawk version` | Mostrar versión |
| `clawk uninstall` | Desinstalar (preserva `~/.clawksis/`) |

</details>

<details>
<summary><b>Configuración (<code>clawk config</code>)</b></summary>

| Comando | Qué hace |
|---|---|
| `clawk config show` | Ver la configuración actual |
| `clawk config edit` | Abrir `config.yaml` en tu editor |
| `clawk config set <clave> <valor>` | Setear un valor (ej: `clawk config set model gpt-5`, `clawk config set terminal.backend tmux`) |
| `clawk config path` · `clawk config env-path` | Imprimir la ruta de `config.yaml` / de `.env` |
| `clawk config check` | Detectar configuración faltante o desactualizada |
| `clawk config migrate` | Actualizar el config con opciones nuevas |

</details>

<details>
<summary><b>Login y credenciales</b></summary>

| Comando | Qué hace |
|---|---|
| `clawk auth add anthropic --type oauth` | **Login con Claude** (suscripción Pro/Max, estilo Claude Code). En remoto/headless agregá `--manual-paste` |
| `clawk auth add openai-codex --type oauth` | **Login con Codex** (ChatGPT Pro/Plus, device-code) |
| `clawk auth add <provider> --type oauth` | Otros OAuth: `xai-oauth`, `qwen-oauth`, `google-gemini-cli`, `minimax-oauth` |
| `clawk auth list` | Listar credenciales del pool (marca la activa) |
| `clawk auth status <provider>` | Ver si estás logueado, scope y expiración |
| `clawk auth remove <provider> <target>` | Quitar una credencial del pool (por índice, id o label) |
| `clawk auth reset <provider>` | Limpiar el estado de agotamiento de las credenciales de un proveedor |
| `clawk auth logout <provider>` | Cerrar sesión y limpiar credenciales |
| `clawk login` · `clawk logout` | Login/logout OAuth directo con un proveedor de inferencia (device-flow) |
| `clawk secrets` | Fuentes externas de secretos — Bitwarden Secrets Manager (`setup`, `status`, `sync`, `disable`, `install`) |

</details>

<details>
<summary><b>Cron — tareas programadas (<code>clawk cron</code>)</b></summary>

El scheduler corre dentro del gateway. Los schedules aceptan intervalos (`30m`), lenguaje natural (`every 2h`) o cron clásico (`0 9 * * *`).

| Comando | Qué hace |
|---|---|
| `clawk cron list` · `--all` | Listar jobs programados (con `--all` incluye los deshabilitados) |
| `clawk cron create "<schedule>" "<prompt>"` (alias `add`) | Crear un job programado |
| `clawk cron edit <job_id> [flags]` | Editar schedule, prompt, nombre, skills, script, workdir o perfil de un job |
| `clawk cron run <job_id>` | Disparar un job en el próximo tick del scheduler |
| `clawk cron pause <job_id>` · `clawk cron resume <job_id>` | Pausar / reanudar un job |
| `clawk cron remove <job_id>` (alias `rm`, `delete`) | Eliminar un job |
| `clawk cron status` | Ver si el scheduler está corriendo |
| `clawk cron tick` | Ejecutar los jobs vencidos una vez y salir (debug) |

**Flags de `create` / `edit`:**

- `--name <nombre>` — nombre legible del job
- `--deliver <destino>` — a dónde va el resultado: `origin`, `local`, `telegram`, `discord`, `signal` o `<plataforma>:<chat_id>`
- `--repeat <N>` — cantidad de repeticiones
- `--skill <skill>` (repetible) — adjuntar skills al job; `edit` además acepta `--add-skill`, `--remove-skill` y `--clear-skills`
- `--script <ruta>` — script en `~/.clawksis/scripts/`; su stdout se inyecta al prompt del agente en cada corrida
- `--no-agent` — sin LLM: el script ES el job y su stdout se entrega tal cual (stdout vacío = silencio); patrón watchdog clásico. En `edit`, `--agent` lo revierte
- `--workdir </ruta>` — directorio de trabajo del job (inyecta `AGENTS.md` / `CLAUDE.md` / `.cursorrules` de ese directorio)
- `--profile <nombre>` — perfil de Clawksis bajo el que corre el job (`default` = perfil raíz)

```bash
# Resumen cada mañana a las 9 por Telegram
clawk cron add "0 9 * * *" "Armá un resumen de mi día y novedades importantes" --name resumen-diario --deliver telegram

# Watchdog de disco sin LLM, cada 30 minutos
clawk cron add 30m --script check_disk.sh --no-agent --name disco
```

</details>

<details>
<summary><b>Personalidad, memoria y perfil</b></summary>

| Comando | Qué hace |
|---|---|
| `clawk soul` · `clawk soul show` · `clawk soul path` | Ver/editar la **personalidad** del agente (`SOUL.md`) |
| `clawk memory show` · `clawk memory edit` | Ver / **editar** la memoria del agente (`MEMORY.md`) |
| `clawk memory setup` · `status` · `off` · `reset` | Configurar / consultar / apagar el proveedor externo de memoria |
| `clawk user` · `clawk user show` · `clawk user path` | Ver / **editar** el perfil del usuario (`USER.md`) |

</details>

<details>
<summary><b>Mensajería y proactividad</b></summary>

| Comando | Qué hace |
|---|---|
| `clawk gateway run` | Gateway de mensajería en primer plano |
| `clawk gateway install` | Gateway como servicio del sistema (boot + auto-restart) |
| `clawk gateway start` · `stop` · `restart` · `status` | Controlar el servicio del gateway |
| `clawk gateway setup` | Configurar plataformas de mensajería |
| `clawk gateway uninstall` | Quitar el servicio del sistema |
| `clawk webhook subscribe <nombre>` (alias `add`) | Crear un webhook dinámico (activación del agente por eventos, ruta `/webhooks/<nombre>`) |
| `clawk webhook list` · `remove <nombre>` · `test <nombre>` | Listar / quitar / probar suscripciones webhook |
| `clawk hooks list` · `test <evento>` · `revoke <cmd>` · `doctor` | Hooks de shell declarados en `config.yaml` (allowlist de consentimiento incluida) |
| `clawk pairing list` · `approve <código>` · `revoke` | Aprobar/revocar usuarios por código de pairing |
| `clawk send` | Enviar un mensaje a una plataforma ya configurada (scripts/cron/CI — sin LLM ni gateway corriendo) |
| `clawk whatsapp` · `clawk slack` | Integración WhatsApp / Slack |

</details>

<details>
<summary><b>Capacidades (skills, plugins, MCP)</b></summary>

| Comando | Qué hace |
|---|---|
| `clawk skills` | Buscar, instalar y gestionar skills (`browse`, `search`, `install`, `list`, `inspect`, `update`, `audit`, `uninstall`, `publish`, `snapshot`, `tap`…) |
| `clawk plugins` | Plugins (`install`, `update`, `remove`, `list`, `enable`, `disable`) |
| `clawk mcp` | Servidores MCP (`add`, `remove`, `list`, `test`, `login`, `install`) y correr Clawksis como MCP server (`serve`) |
| `clawk bundles` | Bundles de skills — alias de varias skills (`list`, `show`, `create`, `delete`, `reload`) |
| `clawk curator` | Mantenimiento automático de skills (`status`, `run`, `pause`, `resume`, `pin`, `unpin`, `restore`, `prune`…) |
| `clawk computer-use` | Backend Computer Use / cua-driver (macOS) |

</details>

<details>
<summary><b>Sesiones y mantenimiento</b></summary>

| Comando | Qué hace |
|---|---|
| `clawk sessions` | Historial de sesiones (`list`, `rename`, `export`, `prune`, `delete`, `stats`, `browse`) |
| `clawk logs` | Ver y filtrar logs (agent / errors / gateway / gui) |
| `clawk insights` | Uso y analytics |
| `clawk backup` · `clawk import` | Backup / restaurar `~/.clawksis/` |
| `clawk checkpoints` | Checkpoints del filesystem (`status`, `list`, `prune`, `clear`) |
| `clawk profile` | Perfiles — instancias aisladas de Clawksis (`list`, `create`, `use`, `show`, `delete`, `export`, `import`…) |
| `clawk security audit` | Auditoría supply-chain (OSV.dev) |
| `clawk kanban` | Tablero de colaboración (tareas, links, comentarios, swarm) |

</details>

<details>
<summary><b>Avanzados y soporte</b></summary>

| Comando | Qué hace |
|---|---|
| `clawk completion <bash\|zsh\|fish>` | Script de autocompletado para tu shell |
| `clawk acp` | Correr Clawksis como servidor ACP para editores (VS Code, Zed, JetBrains) |
| `clawk claw migrate` · `clawk claw cleanup` | Migrar settings, memorias, skills y API keys desde OpenClaw |
| `clawk migrate` | Migrar configuración de modelos retirados o settings deprecados |
| `clawk proxy start` · `status` | Proxy local OpenAI-compatible hacia los proveedores OAuth |
| `clawk postinstall` | Instalar dependencias no-Python para installs por pip (node, browser, ripgrep, ffmpeg) |
| `clawk dump` | Resumen plano del setup para soporte/debugging |
| `clawk debug` | Herramientas de debug (compartir logs y system info para soporte) |
| `clawk prompt-size` | Desglose en bytes del system prompt + schemas de tools |

</details>

> Los plugins instalados pueden registrar comandos top-level propios — usá `clawk <plugin> --help` para verlos.

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

## Mensajería

Telegram, WhatsApp, Discord, Slack y Signal.

```bash
# Telegram — requiere bot token de @BotFather
clawk gateway install --telegram --token TU_BOT_TOKEN

# Ver estado
clawk gateway status
```

Agregá los tokens en `~/.clawksis/.env`:

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
Muestra la versión de Python, la configuración, las herramientas disponibles y qué configurar para activar funciones opcionales (búsqueda web, generación de imágenes, etc.).

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
