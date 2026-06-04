#!/usr/bin/env bash
# =============================================================================
# rebrand.sh -- Convierte el fork samuelgradientai-sys/clawksis-agent a Clawksis/clawk
#
# Uso: bash rebrand.sh [GITHUB_USER] [REPO_NAME]
#   Defaults: samuelgradientai-sys  clawksis-agent
#
# Requisito: correr desde la raiz del fork clonado (donde esta pyproject.toml)
# Idempotente: si se corre dos veces no rompe nada.
# =============================================================================
set -euo pipefail

GITHUB_USER="${1:-samuelgradientai-sys}"
REPO_NAME="${2:-clawksis-agent}"

GRN='\033[0;32m'; YLW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()    { echo -e "${YLW}[rebrand]${NC} $*"; }
ok()      { echo -e "${GRN}[  ok  ]${NC} $*"; }
die()     { echo -e "${RED}[error ]${NC} $*"; exit 1; }

# -- Verificar ubicacion -------------------------------------------------------
[[ -f "pyproject.toml" ]] || die "Corre desde la raiz del fork (donde esta pyproject.toml)."

# -- Detectar Python -----------------------------------------------------------
PYTHON=""
for cmd in \
  python3 python \
  "/c/Users/$USERNAME/AppData/Local/Programs/Python/Python312/python.exe" \
  "/c/Users/$USERNAME/AppData/Local/Programs/Python/Python311/python.exe" \
  "C:/Python312/python.exe" "C:/Python311/python.exe"; do
  if "$cmd" -c "print('ok')" &>/dev/null 2>&1; then
    PYTHON="$cmd"; break
  fi
done
[[ -n "$PYTHON" ]] || die "Python no encontrado. Instala Python 3.x."

info "Python: $PYTHON"
info "Rebrand: clawksis-agent -> clawksis / clawk -> clawk"
info "Repo destino: github.com/${GITHUB_USER}/${REPO_NAME}"
echo

# -- Script Python para reemplazos en archivos ---------------------------------
PYREPLACE=$(mktemp /tmp/replace_XXXXXX.py)
cat > "$PYREPLACE" << 'EOF'
import sys, os

old  = sys.argv[1]
new  = sys.argv[2]
exts = {'.py','.toml','.json','.md','.sh','.ps1','.yml','.yaml',
        '.html','.tsx','.ts','.js','.txt','.cfg','.ini','.rst'}

skip_dirs = {'.git','node_modules','.venv','venv','__pycache__','.mypy_cache'}

changed = 0
for root, dirs, files in os.walk('.'):
    dirs[:] = [d for d in dirs if d not in skip_dirs]
    for fname in files:
        _, ext = os.path.splitext(fname)
        if ext.lower() not in exts and fname not in ('Dockerfile','dockerfile'):
            continue
        fpath = os.path.join(root, fname)
        try:
            raw = open(fpath, 'rb').read()
            text = raw.decode('utf-8', errors='replace')
            if old in text:
                open(fpath, 'w', encoding='utf-8', newline='').write(text.replace(old, new))
                changed += 1
        except Exception:
            pass

print(f"  {changed} archivo(s) modificados")
EOF

replace_all() {
  local FROM="$1" TO="$2"
  "$PYTHON" "$PYREPLACE" "$FROM" "$TO"
}

# =============================================================================
# PASO 1 -- Reemplazos en contenido (mas especifico primero)
# =============================================================================
info "Paso 1/4: Reemplazos en contenido..."

replace_all "samuelgradientai-sys/clawksis-agent"   "${GITHUB_USER}/${REPO_NAME}"
ok "URLs"

replace_all "clawk_cli"         "clawk_cli"
replace_all "clawk_bootstrap"   "clawk_bootstrap"
replace_all "clawk_constants"   "clawk_constants"
replace_all "clawk_logging"     "clawk_logging"
replace_all "clawk_state"       "clawk_state"
replace_all "clawk_time"        "clawk_time"
ok "Modulos Python"

replace_all "clawksis-agent"       "clawksis-agent"
replace_all "clawksis-web"         "clawksis-web"
replace_all "clawk-acp"         "clawk-acp"
replace_all "clawksis-dashboard"   "clawksis-dashboard"
ok "Paquetes y servicios"

replace_all "CLAWK_HOME"          "CLAWK_HOME"
replace_all "CLAWK_INSTALL_DIR"   "CLAWK_INSTALL_DIR"
replace_all "CLAWK_TUI_DIR"       "CLAWK_TUI_DIR"
replace_all "CLAWK_WEB_DIST"      "CLAWK_WEB_DIST"
replace_all "CLAWK_UID"           "CLAWK_UID"
replace_all "CLAWK_GID"           "CLAWK_GID"
replace_all "CLAWK_GIT_BASH_PATH" "CLAWK_GIT_BASH_PATH"
ok "Variables de entorno"

replace_all "/opt/clawksis"               "/opt/clawksis"
replace_all "~/.clawksis"                 "~/.clawksis"
replace_all 'clawksis-agent/venv'         "clawksis-agent/venv"
replace_all 'LocalAppData\clawk'       'LocalAppData\clawksis'
replace_all 'LocalAppData/clawk'       'LocalAppData/clawksis'
ok "Rutas de sistema"

replace_all "clawksis-agent:latest"       "clawksis-agent:latest"
replace_all "container_name: clawksis"    "container_name: clawksis"
replace_all 'CLAWK_UID=$(id -u)'       'CLAWK_UID=$(id -u)'
replace_all 'CLAWK_GID=$(id -g)'       'CLAWK_GID=$(id -g)'
ok "Docker"

replace_all "--clawk-home"    "--clawk-home"
replace_all "ClawkHome"       "ClawkHome"
ok "Flags CLI"

replace_all "Clawksis"            "Clawksis"
replace_all "Clawksis"            "Clawksis"
replace_all "<title>Clawksis</title>"   "<title>Clawksis</title>"
replace_all '"Clawksis"'                '"Clawksis"'
replace_all "'Clawksis'"                "'Clawksis'"
ok "Marca visible (UI/docs)"

replace_all "clawk setup"      "clawk setup"
replace_all "clawk chat"       "clawk chat"
replace_all "clawk gateway"    "clawk gateway"
replace_all "clawk update"     "clawk update"
replace_all "clawk config"     "clawk config"
replace_all "clawk dashboard"  "clawk dashboard"
replace_all "clawk model"      "clawk model"
replace_all "clawk doctor"     "clawk doctor"
replace_all '$ clawk'          '$ clawk'
replace_all '"clawk"'          '"clawk"'
ok "Ejemplos de comandos en docs"

# Entry points exactos (por si quedan residuos)
replace_all 'clawk = "clawk_cli.main:main"'        'clawk = "clawk_cli.main:main"'
replace_all 'clawk = "clawk_cli.main:main"'         'clawk = "clawk_cli.main:main"'
replace_all 'clawksis-agent = "run_agent:main"'        'clawk-agent = "run_agent:main"'
replace_all 'clawk-acp = "acp_adapter.entry:main"'  'clawk-acp = "acp_adapter.entry:main"'

rm -f "$PYREPLACE"

# =============================================================================
# PASO 2 -- Renombrar archivos y directorios con git mv
# =============================================================================
info "Paso 2/4: Renombrando archivos y directorios..."

mv_if() {
  if [[ -e "$1" && ! -e "$2" ]]; then
    git mv "$1" "$2" && ok "  $1 -> $2"
  elif [[ -e "$2" ]]; then
    ok "  $2 ya existe"
  fi
}

mv_if "clawk_cli"           "clawk_cli"
mv_if "clawk_bootstrap.py"  "clawk_bootstrap.py"
mv_if "clawk_constants.py"  "clawk_constants.py"
mv_if "clawk_logging.py"    "clawk_logging.py"
mv_if "clawk_state.py"      "clawk_state.py"
mv_if "clawk_time.py"       "clawk_time.py"
mv_if "setup-clawk.sh"      "setup-clawk.sh"
mv_if "clawk"               "clawk"

# =============================================================================
# PASO 3 -- pyproject.toml: nombre de paquete + entry points
# =============================================================================
info "Paso 3/4: Verificando pyproject.toml..."

PYFIX=$(mktemp /tmp/fix_toml_XXXXXX.py)
cat > "$PYFIX" << 'EOF'
import re
path = "pyproject.toml"
c = open(path, encoding="utf-8").read()
orig = c
c = re.sub(r'^name\s*=\s*"clawksis-agent"', 'name = "clawksis-agent"', c, flags=re.MULTILINE)
replacements = [
    ('clawk = "clawk_cli.main:main"',          'clawk = "clawk_cli.main:main"'),
    ('clawk = "clawk_cli.main:main"',            'clawk = "clawk_cli.main:main"'),
    ('clawksis-agent = "run_agent:main"',           'clawk-agent = "run_agent:main"'),
    ('clawk-acp = "acp_adapter.entry:main"',     'clawk-acp = "acp_adapter.entry:main"'),
]
for old, new in replacements:
    c = c.replace(old, new)
if c != orig:
    open(path, "w", encoding="utf-8").write(c)
    print("  pyproject.toml actualizado")
else:
    print("  pyproject.toml sin cambios")
EOF
"$PYTHON" "$PYFIX"
rm -f "$PYFIX"
ok "pyproject.toml"

# =============================================================================
# PASO 4 -- Licencia
# =============================================================================
info "Paso 4/4: Actualizando LICENSE..."

COPYRIGHT="Additional modifications Copyright (c) 2026 Gradient AI / Samuel Gomez"
if [[ -f LICENSE ]] && ! grep -qF "Gradient AI" LICENSE; then
  printf "\n%s\n" "$COPYRIGHT" >> LICENSE
  ok "Copyright adicional agregado a LICENSE"
else
  ok "LICENSE ya actualizado"
fi

# =============================================================================
# RESUMEN
# =============================================================================
echo
echo -e "${GRN}============================================================${NC}"
echo -e "${GRN}  Rebrand completado: clawksis-agent -> Clawksis (clawk)${NC}"
echo -e "${GRN}============================================================${NC}"
echo
echo "  Proximos pasos:"
echo "  1. Revisar cambios:    git diff --stat"
echo "  2. Instalar local:     bash setup-clawk.sh"
echo "  3. Configurar:         clawk setup"
echo "  4. Smoke test:         clawk -z 'hola'"
echo "  5. Push:"
echo "     git add -A"
echo "     git commit -m 'chore: rebrand clawk -> clawksis (clawk)'"
echo "     git push origin main"
echo
echo "  One-liner instalable:"
echo "  curl -fsSL https://raw.githubusercontent.com/${GITHUB_USER}/${REPO_NAME}/main/scripts/install.sh | bash"
echo
