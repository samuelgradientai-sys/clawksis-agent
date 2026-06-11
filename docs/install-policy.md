# Política de Instalación de Clawksis

> **Versión del documento:** 2.1 — Junio 2026
> **Aplica a:** `scripts/install.sh` (rama `Andresito` actualmente)
> **Estado:** Implementado y validado en 6 escenarios de prueba reales
> **Rama oficial del producto:** `Andresito` (temporal, hasta review del equipo)

---

## 1. Resumen ejecutivo

Clawksis se instala **por usuario, sin necesidad de sudo**. El instalador detecta
automáticamente cuando se le invoca con `sudo` desde una cuenta normal y se
detiene con un mensaje claro que explica el problema y propone la solución
correcta. Un administrador que de verdad necesite hacer una instalación a nivel
sistema puede confirmarlo explícitamente.

El producto soporta tres ambientes de uso:

1. **Equipo personal local** (macOS, Linux, Windows con WSL2) — caso más común
2. **VPS o servidor remoto** — para clientes que necesitan el agente 24/7
3. **Container Docker / Kubernetes** — para deployments automatizados

---

## 2. Rama oficial del producto: `Andresito`

**Durante la fase actual de desarrollo y revisión, la rama oficial del producto
es `Andresito`.** Todas las instalaciones nuevas descargan automáticamente esta
rama, que contiene los 17 bugs corregidos en junio 2026 (ver
`docs/testing-scenarios-2026-06.md`).

### Cómo funciona técnicamente

El installer `scripts/install.sh` tiene en la línea 92:

```bash
BRANCH="Andresito"
```

Cuando un usuario ejecuta el comando estándar de instalación, el installer
clona específicamente esta rama. Esto está documentado en el commit `bd889211`
con el mensaje:

> *Decisión temporal mientras validamos los 17 bugs corregidos en escenarios
> de prueba. El default vuelve a main cuando el equipo confirme la estabilidad.*

### Plan de transición a `main`

1. **Estado actual:** `Andresito` es la rama oficial. `main` permanece en el
   código upstream de Nous Research, sin nuestros fixes.
2. **Fase de revisión:** segundo desarrollador audita los commits de Andresito
   (`d7e2feb5`, `7f56f46e`, `bd889211`) y los escenarios validados.
3. **Aprobación:** una vez confirmado, se hace `git merge Andresito` en `main`.
4. **Post-merge:** se edita `install.sh` línea 92 de vuelta a `BRANCH="main"`
   y se publica un nuevo commit con el mensaje *"config: restaurar main como
   default de installer (Andresito mergeado)"*.

Durante este periodo de transición, **no se modifica `main`** para evitar
contaminar la línea de comparación que el revisor va a usar.

### Cómo forzar una rama específica si fuera necesario

Cualquier usuario puede sobrescribir el default si quisiera:

```bash
# Descargar el installer y pasarle --branch
curl -fsSL https://raw.githubusercontent.com/samuelgradientai-sys/clawksis-agent/Andresito/scripts/install.sh -o install.sh
bash install.sh --branch main        # forzar main (sin fixes)
bash install.sh --branch Andresito   # forzar Andresito (con fixes — es el default)
```

---

## 3. Por qué la política de sudo existe

### El problema histórico

Cuando un usuario hacía `curl ... | sudo bash` (un patrón aprendido de hace
años con otros productos), todos los archivos de configuración y datos de
Clawksis se creaban bajo el directorio del usuario `root` (`/root/.clawksis/`).
El usuario normal del cliente, que es donde trabaja todos los días, quedaba
**sin acceso a sus propias sesiones, memoria, skills configuradas y credenciales**.

Este es el error de instalación más común con productos CLI tipo agente, y
genera una clase entera de tickets de soporte que son imposibles de resolver:

- *"No veo mis sesiones anteriores"*
- *"El agente no se acuerda de nada que le dije ayer"*
- *"Mi configuración desapareció después de la instalación"*
- *"Instalé las skills pero `clawk skills list` no las muestra"*

Todos estos síntomas tienen la misma causa raíz: la instalación quedó en
`/root/` y el usuario está corriendo `clawk` desde su cuenta normal.

### Por qué no se permite simplemente "todo con sudo"

Tres razones de fondo:

**Seguridad.** El agente Clawksis no necesita permisos de root para funcionar.
Darle root sin necesidad expande la superficie de ataque del producto. Si una
skill o un plugin maliciosos se ejecutan, hacerlo como root es mucho peor que
como un usuario normal sin privilegios.

**Aislamiento entre usuarios.** Un VPS o servidor corporativo puede tener
varias personas usando Clawksis. Si todos comparten `/root/.clawksis/`, no hay
separación de sesiones, credenciales ni datos privados.

**Convención de la industria.** Homebrew, rustup, nvm, deno, pnpm, uv, bun —
todos los gestores y CLIs modernos serios rechazan o advierten cuando se les
invoca con sudo. Clawksis se alinea con esa práctica.

---

## 4. Cómo se debe instalar (por entorno)

### 4.1 Equipo local — el caso más común

**Linux y macOS:**

```bash
curl -fsSL https://raw.githubusercontent.com/samuelgradientai-sys/clawksis-agent/Andresito/scripts/install.sh | bash
```

> Nota: la URL apunta a `Andresito` para asegurar que el installer descargado
> tenga los fixes. Una vez Andresito se mergee a main y `BRANCH="main"`
> vuelva al default, podrás usar `/main/scripts/install.sh` indistintamente.

**Windows:**

Clawksis requiere WSL2 (Windows Subsystem for Linux). Si no lo tienes:

```powershell
# En PowerShell como administrador
wsl --install
```

Después de reiniciar, abre Ubuntu desde el menú inicio y ejecuta el mismo
comando curl de arriba.

**Termux (Android):**

El mismo comando curl detecta Termux automáticamente y usa el camino apropiado
(pip + venv en lugar de uv).

### 4.2 VPS (servidor remoto)

El instalador funciona en VPS bien configurados donde el usuario de servicio
**no tiene sudo**. Esto es la mejor práctica de seguridad: el agente corre como
un usuario sin privilegios que solo puede tocar sus propios archivos.

```bash
# Conectado por SSH como el usuario de servicio
curl -fsSL https://raw.githubusercontent.com/samuelgradientai-sys/clawksis-agent/Andresito/scripts/install.sh | bash
```

Los paquetes opcionales del sistema (`ffmpeg`, `ripgrep`, `build-essential`) se
omiten automáticamente si no hay sudo, con un mensaje claro de cómo instalarlos
manualmente más tarde. El producto funciona sin esos paquetes — son
optimizaciones, no requisitos.

### 4.3 Container Docker / Kubernetes

En containers el usuario es root sin sudo (no hay `SUDO_USER`), así que la
política no se activa y el instalador procede normalmente:

```dockerfile
FROM ubuntu:24.04
RUN apt-get update && apt-get install -y curl git
RUN curl -fsSL https://raw.githubusercontent.com/samuelgradientai-sys/clawksis-agent/Andresito/scripts/install.sh | bash -s -- --skip-setup
```

---

## 5. Qué hace el instalador detrás de escena

Después del `curl ... | bash`, el instalador ejecuta 11 etapas:

1. Detecta el sistema operativo
2. Verifica/instala `uv` (gestor de paquetes Python)
3. Verifica Python, Git y Node.js
4. Descarga el código de Clawksis desde GitHub (rama `Andresito` por default)
5. Crea entorno virtual Python aislado
6. Instala dependencias Python (~2-5 minutos)
7. Instala dependencias Node.js para herramientas de browser (~1-3 minutos)
8. Instala CLIs de agentes externos (Claude Code, Codex, OpenCode)
9. Enlaza el comando `clawk` en el PATH
10. Prepara configuración y skills predefinidas
11. Lanza wizard de configuración (a menos que uses `--skip-setup`)

Resultado al terminar:

- **Código** en `~/.clawksis/clawksis-agent/`
- **Configuración** en `~/.clawksis/config.yaml`
- **Credenciales** en `~/.clawksis/.env` (modo 600 — solo lectura del dueño)
- **Datos** en `~/.clawksis/sessions/`, `~/.clawksis/memories/`, `~/.clawksis/skills/`
- **Binario** en `~/.local/bin/clawk` (debe estar en PATH)

---

## 6. Lo que el instalador rechaza por defecto

```bash
# ❌ Patrón problemático — instala todo en /root
curl -fsSL https://raw.githubusercontent.com/samuelgradientai-sys/clawksis-agent/Andresito/scripts/install.sh | sudo bash
```

Cuando se detecta este patrón (`SUDO_USER` está definido y es distinto de
`root`), el instalador muestra un warning explícito:

```
⚠ Running under sudo (invoked by user 'andres').
⚠ Clawksis is designed to install per-user, WITHOUT sudo:
⚠   data/config →  ~/.clawksis of the installing user
⚠ Installing as root puts data in /root/.clawksis — your normal
⚠ account 'andres' will NOT see this install.

→ Recommended: exit and re-run as your normal user:
→   curl -fsSL https://raw.githubusercontent.com/.../install.sh | bash

Continue installing as root anyway? [y/N]
```

Dos comportamientos:

- **Modo interactivo** (terminal con TTY): pide confirmación explícita, default `No`.
- **Modo no-interactivo** (sin TTY, ejemplo: pipe sin `</dev/tty`): aborta automáticamente con código de salida 1.

---

## 7. Casos legítimos donde sudo es correcto

### 7.1 Container Docker que corre como root

En este caso `SUDO_USER` no está definido, la política no se activa, y el
instalador procede normalmente. Funciona out-of-the-box.

### 7.2 Instalación a nivel sistema (FHS layout)

Para máquinas pre-configuradas de servidor donde Clawksis va a estar disponible
para múltiples usuarios. El admin que entiende lo que hace puede:

```bash
sudo bash install.sh   # responder 'y' a la confirmación
```

Esto activa el layout FHS:
- Código en `/usr/local/lib/clawksis-agent/`
- Binario en `/usr/local/bin/clawk`
- Cada usuario sigue teniendo su propio `~/.clawksis/` con datos privados

### 7.3 CI/CD que corre como root

Pipelines de Docker build, GitHub Actions con `runs-on: ubuntu-latest`,
GitLab Runners, etc. Funcionan automáticamente porque no hay `SUDO_USER` —
el proceso es root nativamente, no escaló desde otro usuario.

---

## 8. Variables de entorno relevantes

| Variable | Para qué sirve | Default |
|---|---|---|
| `CLAWK_HOME` | Directorio de datos del usuario | `~/.clawksis` |
| `CLAWK_INSTALL_DIR` | Directorio del código fuente | `~/.clawksis/clawksis-agent` |
| `NPM_CONFIG_PREFIX` | Prefix de paquetes globales de npm | Heredado del sistema |

Útiles para testing o instalaciones especializadas. Ejemplo de instalación
aislada para pruebas:

```bash
export CLAWK_HOME=~/test-instance/data
export CLAWK_INSTALL_DIR=~/test-instance/code
bash install.sh --skip-setup
```

---

## 9. Flags del instalador

| Flag | Qué hace |
|---|---|
| `--branch BRANCH` | Clona una rama específica del repo. Default actual: `Andresito`. Cambiará a `main` cuando se complete el merge tras la revisión del equipo. |
| `--skip-setup` | No lanza el wizard interactivo. Implica modo no-interactivo (no pregunta nada). Útil para CI/CD y scripts automatizados. |
| `--skip-browser` | No descarga Playwright/Chromium (~300 MB). El agente sigue funcionando, solo las herramientas de browser quedan inactivas. |
| `--no-venv` | No crea entorno virtual Python. Solo recomendado para Termux. |
| `--no-skills` | No siembra las skills predefinidas. Útil cuando se quiere un agente vacío. |

---

## 10. Comparación local vs VPS

| Aspecto | Equipo local | VPS |
|---|---|---|
| Privacidad | Total — datos no salen de tu máquina | Datos en servidor externo |
| Disponibilidad | Solo cuando el equipo está encendido | 24/7 |
| Acceso desde móvil | Solo si tu equipo es accesible | Sí, vía Telegram/WhatsApp/Discord |
| Costo de infraestructura | Cero (usa tu hardware) | ~5-10 USD/mes el VPS |
| Modelos locales | Sí (Ollama, LM Studio) | Posible pero costoso |
| Setup | Más simple (suele tener sudo) | Requiere VPS y SSH |

**Casos típicos:**

- Desarrollador individual → equipo local. Para coding y experimentar.
- Profesional con cliente → equipo local. Privacidad de datos del cliente.
- Emprendedor que necesita el agente respondiendo 24/7 → VPS.
- Empresa con equipo → ambos. Cada empleado local + un VPS central para
  automatizaciones compartidas.

---

## 11. Verificación: ¿el installer descargado tiene la política?

```bash
curl -fsSL https://raw.githubusercontent.com/samuelgradientai-sys/clawksis-agent/Andresito/scripts/install.sh -o install.sh

# Verificar que apunta a Andresito por default
grep '^BRANCH=' install.sh
# Esperado: BRANCH="Andresito"

# Verificar funciones del fix de detección de sudo
grep -c "detect_sudo_capability\|HAS_USABLE_SUDO" install.sh
# Esperado: 16+ ocurrencias

# Verificar el check de SUDO_USER
grep -c "SUDO_INSTALL_ACKNOWLEDGED" install.sh
# Esperado: 3+ ocurrencias

# Verificar que el binario clawk se verifica al final
grep -c "Installation completed with warnings" install.sh
# Esperado: 1 ocurrencia
```

Si esos números son menores, el installer es de una rama o release anterior a
los fixes de junio 2026.

---

## 12. Política de detección de sudo (referencia técnica)

El instalador tiene una función `detect_sudo_capability()` que se ejecuta una
sola vez al inicio del flujo. Establece la variable `HAS_USABLE_SUDO` con dos
valores posibles:

- `true` — el usuario es root, o sudo funciona sin contraseña (NOPASSWD o
  cache válida). Todas las instalaciones de paquetes del sistema proceden
  automáticamente.
- `false` — sudo no está disponible, o requiere contraseña que no se puede
  pedir (sin TTY, en modo no-interactivo). Las instalaciones de paquetes del
  sistema se omiten silenciosamente con un mensaje informativo.

Antes de junio 2026, cada paso (`ffmpeg`, `ripgrep`, `build-essential`)
re-detectaba sudo independientemente. Cada uno se colgaba si el sudo
necesitaba contraseña sin TTY disponible. Ahora se detecta una sola vez, y
los pasos consultan el flag sin re-prompts.

---

## 13. Cómo gestionar la instalación después

### Actualizar Clawksis

```bash
clawk update
```

Trae los nuevos commits del repo, actualiza dependencias Python y Node,
reconstruye el dashboard web, migra la configuración a nuevas versiones si
es necesario. **Preserva el `.env`, sesiones, memorias y skills personalizadas.**

### Diagnosticar problemas

```bash
clawk doctor
```

Reporta el estado de todos los componentes: dependencias, configuración,
proveedores de IA, herramientas disponibles, cron scheduler, etc.

```bash
clawk doctor --fix
```

Intenta corregir automáticamente lo que puede.

### Hacer backup

```bash
clawk backup
```

Crea un zip con toda la configuración y datos en `~/clawk-backup-YYYY-MM-DD.zip`.
Excluye automáticamente node_modules y caches.

### Restaurar backup

```bash
clawk import clawk-backup-YYYY-MM-DD.zip
```

### Desinstalar

```bash
clawk uninstall
```

Elimina el código pero **preserva `~/.clawksis/`** (configuración y datos).
Reinstalar después conserva todas tus sesiones, memorias y credenciales.

---

## 14. Roadmap

Mejoras futuras a esta política, documentadas pero no implementadas todavía:

1. **Merge de Andresito a main** — paso 1 del roadmap inmediato. Una vez el
   segundo desarrollador apruebe los fixes, hacer el merge y restaurar
   `BRANCH="main"` como default del installer.

2. **Flag `--system-install`** — para admins corporativos que quieren instalar
   a nivel sistema sin pasar por el prompt de confirmación. Equivalente a
   responder `y` automáticamente al warning de sudo.

3. **Detección explícita de Docker** — distinguir "estoy en container como
   root" de "alguien hizo sudo bash". Hoy se infiere por ausencia de
   `SUDO_USER`, lo cual funciona pero no es 100% robusto.

4. **Auto-detección de PATH** — si el binario se instala en un directorio que
   no está en el PATH, el instalador podría modificar `.bashrc`/`.zshrc`
   automáticamente con confirmación, en vez de solo advertir.

5. **Shims separados por instalación** — para que reinstalar Clawksis en una
   ubicación custom no rompa el shim global existente (Bug #19).

6. **Una sola barra de progreso global** — en lugar de 11 mini-barras
   separadas, una sola barra que va de 0 a 100% con etiqueta dinámica
   abajo mostrando qué está haciendo.
