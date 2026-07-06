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
  <img src="https://img.shields.io/badge/Plataformas-Linux%20·%20macOS%20·%20Windows%20·%20Android-black?style=for-the-badge" alt="Plataformas">
</p>

---

**Clawksis es un agente de IA que vive en tu servidor y trabaja para vos de forma continua.** A diferencia de un chatbot común, no espera a que le hables: corre tareas programadas, reacciona a eventos y te escribe **a vos** por Telegram, WhatsApp o Discord cuando pasa algo. Conectalo con la suscripción de **Claude o ChatGPT que ya pagás** —por OAuth, sin API key— y en minutos tenés tu propio asistente autónomo, privado y sin límites impuestos por terceros.

## Tabla de contenidos

- [Características](#características)
- [Instalación](#instalación)
- [Primeros pasos](#primeros-pasos)
- [Proveedores soportados](#proveedores-soportados)
- [Comandos](#comandos)
- [Self-hosted: acceso por dominio](#self-hosted-acceso-por-dominio)
- [Mensajería](#mensajería)
- [Problemas comunes](#problemas-comunes)
- [Actualizar](#actualizar) · [Desinstalar](#desinstalar) · [Contribuir](#contribuir) · [Licencia](#licencia)

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

**Requisitos:** solo una máquina con acceso a terminal (Linux, macOS, Windows o Android). No hace falta preparar nada más: el instalador descarga el código, crea un virtualenv de Python, instala las dependencias de Node, construye el dashboard web y enlaza `clawk` en tu `PATH`.

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

¿Solo querés una respuesta rápida sin entrar al modo interactivo? Usá el modo one-shot:

```bash
clawk -z "resumime las novedades importantes de hoy"
```

Desde acá ya podés [conectar mensajería](#mensajería) para hablarle desde el celular, [programar tareas](#comandos) o [publicar el dashboard en tu dominio](#self-hosted-acceso-por-dominio).

---

## Proveedores soportados

Clawksis habla con **más de 30 proveedores LLM**, y la gran ventaja es cómo los conectás:

- 🔑 **Usá la suscripción que ya pagás** — conectá **Claude Pro/Max** o **ChatGPT Plus/Pro** por **OAuth**, sin gastar en API keys.
- 🧩 **O tu propia API key** — de casi cualquier proveedor (OpenRouter, OpenAI, DeepSeek, Gemini, Kimi…).
- 🖥️ **O modelos 100% locales** — con Ollama o LM Studio, sin mandar nada a la nube.

La forma más fácil de conectar cualquiera es **`clawk model`** (menú interactivo que te lleva de la mano). Para ir directo, usá **`clawk auth add <id>`**: auto-detecta el tipo, hace el login OAuth en el navegador o te pide la API key y la guarda en `~/.clawksis/.env`. El valor por defecto (`auto`) usa lo que tengas configurado.

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
| `clawk dashboard` | Abrir el dashboard web (chat Modern/Terminal, sesiones, media, tareas) |
| `clawk dashboard domain <dominio>` | Publicarlo en `https://<dominio>` con HTTPS, en un comando |
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
<summary><b>Dashboard web (<code>clawk dashboard</code>)</b></summary>

El dashboard es una web UI (por defecto en `http://127.0.0.1:9119`): chat en dos modos — **Modern** (burbujas, con paneles laterales de **Visualización** de agentes, **Media** generada y **Tareas** kanban) y **Terminal** (la CLI clásica) —, gestión de sesiones, modelos, skills, plugins, MCP y canales. En un servidor, `clawk dashboard` queda corriendo en segundo plano (sobrevive al cierre de SSH).

| Comando | Qué hace |
|---|---|
| `clawk dashboard` | Iniciar la web UI (en un servidor: en segundo plano) |
| `clawk dashboard --stop` · `--status` | Detener / listar los procesos del dashboard |
| `clawk dashboard --remote USER@HOST` | Abrirlo desde tu PC vía túnel SSH (sin `ssh -L` manual; `--start` lo arranca en el remoto, `--ssh-opt` pasa opciones a ssh) |
| `clawk dashboard password` | Crear/cambiar el login (usuario + contraseña; `--clear` lo borra) |
| `clawk dashboard service` | Instalarlo como servicio systemd (arranca solo al boot; `--uninstall`, `--status`, `--plain`) |
| `clawk dashboard domain <dominio>` | Publicarlo en `https://<dominio>`: systemd + login forzado + Caddy con HTTPS automático, en un comando (ver [Self-hosted](#self-hosted-acceso-por-dominio)) |
| `clawk dashboard --host 0.0.0.0 --insecure` | Exponerlo en toda interfaz (activa el login; preferí `domain` para HTTPS) |

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
| `clawk kanban` | Tablero de colaboración (tareas, links, comentarios, swarm); también como panel **Tareas** en el chat Modern del dashboard |

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

Entrá al dashboard desde `https://panel.tudominio.com` en cualquier dispositivo,
**sin túneles SSH y sin entrar al servidor a correr `clawk dashboard`**. La vía
rápida es **un solo comando**:

```bash
sudo clawk dashboard domain panel.tudominio.com
```

Eso hace todo del lado del servidor: instala el dashboard como **servicio
systemd** (arranca solo al bootear), fuerza el **login**, instala **Caddy** si
falta y escribe el reverse proxy con **HTTPS automático** (Let's Encrypt). El
único paso que queda de tu lado es crear el registro DNS `A` de tu dominio
apuntando a la IP del servidor; en cuanto propague, `https://panel.tudominio.com`
anda y la primera visita a `/login` crea tu usuario y contraseña. ¿Solo querés
el servicio, sin dominio? `sudo clawk dashboard service` (y de tu PC entrás con
`clawk dashboard --remote user@server`).

<details>
<summary><b>📖 Guía completa — montarlo a mano: systemd · login · Cloudflare Tunnel · nginx · troubleshooting</b></summary>

> **Uso local = sin contraseña.** `clawk dashboard` a secas (escucha en
> `127.0.0.1`) entra directo, sin login. La contraseña se pide **solo** cuando
> lo exponés hacia afuera (`--host 0.0.0.0` o el modo dominio de arriba): el
> gate de autenticación se enciende automáticamente en esos modos.

Son tres piezas, cada una independiente (la vía rápida las hace todas):

1. El **dashboard como servicio** (systemd) — arranca solo, sobrevive reinicios.
2. El **login** — el gate de autenticación se activa automáticamente al escuchar
   fuera de loopback (y en modo dominio se fuerza vía
   `CLAWK_DASHBOARD_FORCE_GATE=1` aunque el bind sea loopback); nadie entra sin
   usuario/contraseña.
3. La **ruta pública** — Opción A: Cloudflare Tunnel (recomendada, sin abrir
   puertos) · Opción B: nginx + certbot (clásica) · o el Caddy que instala la
   vía rápida.

### 1. Dashboard como servicio (systemd)

La vía rápida equivalente: `sudo clawk dashboard service`. A mano, creá
`/etc/systemd/system/clawk-dashboard.service`:

```ini
[Unit]
Description=Clawksis Dashboard (web UI :9119)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
Environment=HOME=/root
# (Opcional) Credenciales por env — si las omitís, la PRIMERA visita al
# dashboard te deja crear usuario y contraseña desde el navegador (sección 2).
# Env gana sobre config.yaml.
#Environment=CLAWK_DASHBOARD_BASIC_AUTH_USERNAME=tu-usuario
#Environment=CLAWK_DASHBOARD_BASIC_AUTH_PASSWORD=tu-password-fuerte
#Environment=CLAWK_DASHBOARD_BASIC_AUTH_SECRET=<64 hex aleatorios: openssl rand -hex 32>
WorkingDirectory=/usr/local/lib/clawksis-agent
ExecStart=/usr/local/lib/clawksis-agent/venv/bin/python3 -m clawk_cli.main dashboard --no-open --host 0.0.0.0 --port 9119 --skip-build
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```bash
sudo chmod 600 /etc/systemd/system/clawk-dashboard.service   # protege el password
sudo systemctl daemon-reload
sudo systemctl enable --now clawk-dashboard
systemctl status clawk-dashboard    # → active (running)
```

> `--host 0.0.0.0` es lo que **activa el login** (ver abajo). `--skip-build`
> sirve el `web_dist` ya compilado (lo reconstruye `clawk update`).
> Ajustá `WorkingDirectory`/`ExecStart` si tu instalación no está en
> `/usr/local/lib/clawksis-agent`.

### 2. Login (gate de autenticación)

El gate se **activa solo** cuando el dashboard escucha en un host no-loopback
(`--host 0.0.0.0`) sin `--insecure`: toda request sin sesión recibe la página de
login (`/` → 302) y la API responde 401. Con `--host 127.0.0.1` el gate NO se
activa — por eso nunca publiques un dashboard que escucha solo en loopback.

**Primera vez — el login se crea solo.** Si el gate está activo y todavía no
configuraste credenciales, la primera visita a `/login` muestra un formulario
de bienvenida: elegís usuario y contraseña, se guardan automáticamente en
`~/.clawksis/config.yaml` (hash scrypt + clave de firma aleatoria — nunca texto
plano) y quedás logueado en el acto. No hay que editar ningún archivo. Ese
formulario desaparece en cuanto existe un login: nadie más puede "reclamar" el
dashboard después.

**¿Olvidaste la contraseña? Se cambia con un comando:**

```bash
clawk dashboard password            # setear o CAMBIAR usuario/contraseña (interactivo)
clawk dashboard password --clear    # borrar el login (vuelve el formulario de primera vez)
```

Pide la contraseña dos veces sin mostrarla (no queda en el historial del
shell) y guarda solo el hash. Después reiniciá el dashboard para aplicar:
`sudo systemctl restart clawk-dashboard` (o cortá y relanzá `clawk dashboard`).

**Configuración manual (opcional).** El provider incluido es **basic auth**
(usuario + contraseña, sesiones HMAC sin base de datos). Si preferís
provisionarlo vos — por ejemplo en el unit de systemd — va por env (gana sobre
config.yaml) **o** directo en `~/.clawksis/config.yaml`:

```yaml
dashboard:
  basic_auth:
    username: tu-usuario
    # Opción preferida: hash scrypt (sin plaintext en disco)…
    # password_hash: "scrypt$..."
    # …o plaintext (se hashea en memoria al cargar):
    password: "tu-password-fuerte"
    secret: "<64 hex aleatorios>"      # clave de firma de sesiones (openssl rand -hex 32)
    session_ttl_seconds: 43200          # opcional (12 h por defecto)
```

> Si exponés el dashboard **antes** de crear el login, cualquiera que llegue a
> la URL podría reclamarlo primero. En la práctica: abrí `/login` apenas
> publiques el dominio, o creá las credenciales antes con
> `clawk dashboard password`.

### 3A. Ruta pública con Cloudflare Tunnel (recomendada)

Sin abrir puertos, sin certificados que renovar: HTTPS, WebSockets y DNS los
maneja Cloudflare. Requiere tu dominio en Cloudflare (plan gratis alcanza).

1. **Crear el tunnel** (una vez): [Cloudflare dashboard](https://one.dash.cloudflare.com)
   → *Zero Trust → Networks → Tunnels → Create a tunnel* (tipo `cloudflared`).
   Copiá el **token** que te da.

2. **Correr cloudflared en el servidor** (Docker, reinicia solo):

   ```bash
   docker run -d --name clawksis-cf-tunnel --restart always --network host \
     cloudflare/cloudflared:latest tunnel --no-autoupdate run --token <TU_TOKEN>
   ```

   > `--network host` permite que el tunnel llegue a `localhost:9119` directo.

3. **Publicar el hostname** (en la config del tunnel, pestaña *Public Hostname*):

   | Campo | Valor |
   |---|---|
   | Subdomain | `panel` (o el que quieras) |
   | Domain | `tudominio.com` |
   | Service | `http://localhost:9119` |

   Cloudflare crea el registro DNS automáticamente. En ~1 minuto,
   `https://panel.tudominio.com` sirve el login del dashboard. El mismo tunnel
   admite más hostnames (p. ej. el bridge u otros servicios del mismo VPS).

**Endurecimiento recomendado:** con el tunnel no hace falta el puerto 9119
abierto al mundo — bloquealo en el firewall (panel del proveedor o
`ufw deny 9119`; el tunnel entra por `localhost`, no lo afecta). Para una
segunda capa (además del login), podés poner una política de **Cloudflare
Access** sobre el hostname (Zero Trust → Access): pide verificación por email
antes de llegar siquiera al login.

### 3B. Ruta pública con nginx + HTTPS (alternativa clásica)

Si preferís no usar Cloudflare: apuntá un registro `A` de tu dominio a la IP del
servidor y usá nginx como reverse proxy (dejá el dashboard en `--host 0.0.0.0`
igual, para que el login siga activo; o `127.0.0.1` + `--insecure` NUNCA).

```nginx
server {
    listen 443 ssl;
    server_name panel.tudominio.com;

    ssl_certificate     /etc/letsencrypt/live/panel.tudominio.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/panel.tudominio.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:9119;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;   # WebSockets del chat/gateway
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d panel.tudominio.com
```

### Verificación y problemas comunes

```bash
systemctl is-active clawk-dashboard          # → active
curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:9119/            # → 302 (login: gate OK)
curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:9119/api/config  # → 401 (API protegida)
```

- **Entra directo sin login** → estás escuchando en `127.0.0.1` (el gate no se
  activa) o pasaste `--insecure`. Usá `--host 0.0.0.0`.
- **La página carga pero el chat dice "Conectando..."** → el proxy no pasa
  WebSockets: usá el tunnel de Cloudflare (los soporta nativo) o los headers
  `Upgrade`/`Connection` de nginx del ejemplo.
- **Cambié el password y no aplica** → el env del unit gana sobre config.yaml:
  editá el unit + `sudo systemctl daemon-reload && sudo systemctl restart clawk-dashboard`.
- **Actualizar Clawksis** → `clawk update` reconstruye el `web_dist`; el
  servicio sigue sirviendo la versión nueva sin reiniciar (las pestañas
  abiertas se recargan solas al detectar el bundle nuevo).

</details>

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

## Contribuir

¿Encontraste un bug o tenés una idea? Toda contribución es bienvenida:

- 🐛 **Reportar un problema** — abrí un [issue](https://github.com/samuelgradientai-sys/clawksis-agent/issues) con los pasos para reproducirlo (`clawk dump` genera un resumen del setup para adjuntar).
- 🔧 **Enviar un cambio** — hacé un fork, trabajá en una rama y mandá un Pull Request.
- 📖 **Documentación** — más contexto en [DOCUMENTATION.md](https://github.com/samuelgradientai-sys/clawksis-agent/blob/main/DOCUMENTATION.md) y en [clawksis.com](https://www.clawksis.com/).

---

## Licencia

MIT. Basado en [hermes-agent](https://github.com/NousResearch/hermes-agent) de Nous Research — copyright original conservado en `LICENSE`.
