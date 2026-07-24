---
name: notion-mcp
description: "Conectar y gestionar Notion desde Clawksis via MCP server oficial. Instalación, configuración, query de bases de datos, enriquecimiento de registros, y automatización con cron jobs. Cubre toda la integración con la API de Notion."
version: 1.0.0
author: Clawksis
metadata:
  clawk:
    tags: [notion, mcp, database, enrichment, cron, automation, no-code]
    related_skills: [clawksis-agent, supabase]
---

# Notion MCP Integration

Conecta Clawksis a tu workspace de Notion para leer, escribir y enriquecer bases de datos automáticamente.

## Instalación

### 1. Obtener token de Notion
1. Ve a https://www.notion.so/profile/integrations
2. Click **"New Integration"** → nombre: ej. "Clawksis"
3. Selecciona el workspace
4. Copia el **Internal Integration Secret** (token `ntn_...`)

### 2. Compartir páginas con la integración
Cada página/BD que quieras consultar debe compartirse explícitamente:
- Abre la página en Notion
- Click `···` (menú superior derecho)
- **Add connections** → selecciona tu integración

⚠️ Si no compartes las páginas, la API devuelve `401 API token is invalid`.

### 3. Configurar MCP server en Clawksis

Agregar a `~/.clawksis/config.yaml` bajo `mcp_servers`:

```yaml
mcp_servers:
  notion:
    command: npx
    args: ["-y", "@notionhq/notion-mcp-server"]
    enabled: true
    env:
      NOTION_API_KEY: '{{ .Env.NOTION_API_KEY }}'
```

Agregar el token a `~/.clawksis/.env`:

```bash
NOTION_API_KEY=ntn_your_notion_token_here
```

Reiniciar gateway:

```bash
clawk gateway restart
# o si estás dentro del gateway:
systemctl restart clawk-gateway
```

### 4. Verificar conexión
Buscar bases de datos:
```
mcp_notion_API_post_search(filter={"property":"object","value":"data_source"})
```
Si ves resultados → ✅ conectado. Si ves `401` → la integración no tiene acceso a esa página.

## Herramientas MCP de Notion

| Tool | Función |
|---|---|
| `mcp_notion_API_post_search` | Buscar páginas y bases de datos |
| `mcp_notion_API_query_data_source` | Consultar registros de una BD |
| `mcp_notion_API_retrieve_a_page` | Leer una página |
| `mcp_notion_API_patch_page` | Actualizar propiedades de una página |
| `mcp_notion_API_retrieve_a_data_source` | Ver estructura de una BD |
| `mcp_notion_API_update_a_data_source` | Modificar schema de una BD (añadir/quitar columnas) |
| `mcp_notion_API_create_a_data_source` | Crear nueva BD |
| `mcp_notion_API_post_page` | Crear nueva página |
| `mcp_notion_API_append_block_children` | Añadir bloques de contenido |
| `mcp_notion_API_retrieve_page_markdown` | Leer página como Markdown |
| `mcp_notion_API_update_page_markdown` | Actualizar contenido como Markdown |

## Patrones de uso

### Query una base de datos
```python
# Todas las BDs del workspace
mcp_notion_API_post_search(filter={"property":"object","value":"data_source"})

# Registros de una BD específica
mcp_notion_API_query_data_source(data_source_id="<uuid>", page_size=20)

# Schema/estructura de una BD
mcp_notion_API_retrieve_a_data_source(data_source_id="<uuid>")
```

### Añadir columnas a una BD
```json
{
  "Nombre columna": {"type": "date", "date": {}},
  "Prioridad": {
    "type": "select",
    "select": {
      "options": [
        {"name": "Alta", "color": "red"},
        {"name": "Media", "color": "yellow"},
        {"name": "Baja", "color": "green"}
      ]
    }
  }
}
```

### Actualizar campos de un registro
```json
{
  "Cliente": {"relation": [{"id": "<page-id>"}]},
  "Fecha de inicio": {"date": {"start": "2026-07-01", "end": null}},
  "Prioridad": {"select": {"name": "Alta"}},
  "Notas": {"rich_text": [{"type": "text", "text": {"content": "nota..."}}]}
}
```

## Modos de trabajo con proyectos

### Modo A: Enriquecimiento automático (con permiso explícito)
Activa solo cuando el usuario diga explícitamente "enriquece", "llena", "actualiza" o "mejora la info". Por defecto NO enriquezcas automáticamente — el usuario prefiere control sobre qué se escribe.

### Modo B: Reporte de solo lectura (default recomendado)
Cron diario que SOLO consulta y reporta estado. Nunca modifica datos. Este es el modo preferido para crones automáticos sin supervisión.

### Modo C: Enriquecimiento controlado (híbrido)
Cuando el usuario te pide enriquecer, hazlo manualmente durante la conversación (no en crones). Reporta qué cambios hiciste.

**Regla de oro:** Si no estás seguro de si el usuario quiere enriquecimiento automático, usa Modo B (solo lectura) y menciona qué mejorarías si él lo autoriza.

## Enriquecimiento de datos (bajo pedido)

Cuando el usuario pide enriquecer datos:

### Principios
1. **Nunca preguntes "¿qué pongo aquí?"** — usa el contexto disponible (nombre del proyecto, notas existentes, relaciones con otras tablas, conocimiento del negocio)
2. **Estructura las notas** con objetivos numerados y tareas concretas
3. **Añade columnas faltantes** que aporten valor (fechas, prioridades, estados)
4. **Vincula relaciones** entre tablas por nombre (ej: proyecto "3pl" ↔ cliente "3PL")
5. **Actualiza estado** solo si hay info suficiente para inferirlo

### Workflow paso a paso
1. Query la estructura de la BD → identificar columnas actuales
2. Query los registros → ver qué datos faltan
3. Añadir columnas útiles (fecha, prioridad, tipo, etc.)
4. Enriquecer cada registro con:
   - Notas estructuradas (objetivos numerados)
   - Relaciones vinculadas por nombre
   - Fechas estimadas basadas en created_time o contexto
   - Prioridades según relevancia del proyecto
5. Reportar los cambios al usuario

### Ejemplo de nota enriquecida
```
"Proyecto integral de IA para 3PL. Objetivos:
1) Integrar Clawksis como agente inteligente en el Dashboard
2) Desarrollar módulo de automatización para seguimiento de envíos
3) Implementar chatbot de atención al cliente con IA
4) Generar reportes automatizados de trazabilidad
Pendiente: definir alcance del MVP y APIs a integrar."
```

## Personalización visual de BDs

El usuario Samuel valora MUCHO la estética visual. Prefiere que tomes iniciativa para mejorar el diseño sin preguntar ("hazlo tú, sorpréndeme"). Aplica estas técnicas siempre que organices o mejores una BD.

### Workflow completo de embellecimiento visual

1. **Iconos emoji** → cada página con emoji representativo
2. **Portadas Unsplash** → cada página con cover image relevante
3. **Cliente Tag (select con colores)** → etiqueta de color por cliente/tipo
4. **Columna de Progreso (%)** → barra visual de avance (formato percent)
5. **Notas estructuradas** → bold + bullets + secciones
6. **Página interna con markdown** → callout + checklist + tablas
7. **Columnas de negocio** → Valor mensual (COP), Día de pago, Estado cliente
8. **Fechas con recordatorio** → Notion alerta nativa al configurar fechas
9. **Categorías para credenciales** → organizar credenciales por tipo de servicio

### Sistema de colores consistente entre BDs

Cuando varias BDs comparten los mismos clientes (PROYECTOS, CLIENTES, CREDENCIALES), USA EL MISMO COLOR para el mismo cliente en todas:

| Cliente | Color | Tipo |
|---|---|---|
| GRADIENT AI (empresa propia) | 🔵 blue | Propia |
| 3PL (logística, propia) | 🟠 orange | Propia |
| AVO (cliente externo) | 🟡 yellow | Externo |
| ÓPTICA LUZ DE VIDA (cliente) | 🟣 purple | Externo |
| BARBEROS (cliente retirado) | ⚫ gray | Retirado |
| EKLAT (óptica, nuevo) | 🩷 pink | Externo |

**Implementación:** Añade una columna `Cliente Tag` tipo `select` con las opciones de colores en CADA BD que tenga relación con clientes. Así visualmente se agrupan rápido.

```python
mcp_notion_API_update_a_data_source(
    data_source_id="<uuid>",
    properties={
        "Cliente Tag": {
            "select": {
                "options": [
                    {"name": "GRADIENT AI", "color": "blue"},
                    {"name": "3PL", "color": "orange"},
                    {"name": "AVO", "color": "yellow"},
                    {"name": "ÓPTICA LUZ DE VIDA", "color": "purple"}
                ]
            }
        }
    }
)
```

#### 1. Iconos de páginas (emojis)

Cada registro puede tener un emoji como icono. Se actualiza vía `patch_page`:

```python
mcp_notion_API_patch_page(
    page_id="<uuid>",
    icon={"emoji": "🚚"}
)
```

**Buenas prácticas por tipo de proyecto:**
- 📦 Logística / 3PL
- 🤖 Agente IA / automatización
- ☁️ Cloud / infraestructura
- 👓 Óptica / salud visual
- 📢 Marketing / publicidad
- 🔄 Migración / integración
- 🛒 E-commerce
- 📊 Consultoría / análisis
- 💼 Empresa / corporativo
- 🏢 Cliente empresa
- 💈 Barbería / salón
- 🏭 Empresa tech
- 💻 GitHub / repositorio
- 📧 Correo / email
- 🌐 Hosting / web
- 💬 WhatsApp / Meta
- 🔄 API / integración
- 🔒 Credencial genérica

#### 2. Portadas (cover images)
Actualiza todos los iconos en paralelo para ser eficiente.

#### 2. Portadas (cover images)

```python
mcp_notion_API_patch_page(
    page_id="<uuid>",
    cover={
        "type": "external",
        "external": {
            "url": "https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?w=1200&h=400&fit=crop"
        }
    }
)
```

⚠️ **Importante:** `cover` y `properties` NO se pueden mezclar en la misma llamada si `properties` tiene errores de validación — toda la llamada se rechaza. Siempre SEPARAR: primero properties, luego covers en otra tanda.

**Buenas prácticas de covers (Unsplash photo IDs):**
- Logística/3PL: `photo-1586528116311-ad8dd3c8310d` (bodega)
- Tech/cloud: `photo-1544197150-b99a580bb7a8` (servidores)
- IA/robot: `photo-1677442136019-21780ecad995` (AI)
- Marketing: `photo-1460925895917-afdab827c52f` (dashboard)
- Oficina/empresa: `photo-1497366216548-37526070297c` (oficina)
- Óptica/lentes: `photo-1574258495973-f010dfbb5371` (lentes)
- Barbería: `photo-1585747861115-8f4b9e8b3c6f` (barbería)
- Negocios/reuniones: `photo-1559136555-9303baea8ebd` (team)

#### 3. Notas estructuradas con rich_text

Para notas profesionales, usa secciones con emojis y bullets:

```python
{
    "Notas": {
        "rich_text": [
            {
                "annotations": {"bold": true},
                "text": {"content": "🎯 Objetivo: "},
                "type": "text"
            },
            {
                "text": {
                    "content": "Descripción.\n\n📋 Pendientes:\n• Tarea 1\n• Tarea 2\n\n💡 Nota: Contexto."
                },
                "type": "text"
            }
        ]
    }
}
```

⚠️ **PIEDRA FRECUENTE:** `bold` y otros annotations van dentro de `annotations`, NO dentro de `text`:
- ✅ Correcto: `{"annotations": {"bold": true}, "text": {"content": "..."}}`
- ❌ Incorrecto: `{"text": {"bold": true, "content": "..."}}`

#### 4. Columna de Progreso (barras de porcentaje)

Añade columna numérica formato "percent" para barras visuales:

```python
# Añadir columna al schema
mcp_notion_API_update_a_data_source(
    data_source_id="<uuid>",
    properties={"Progreso": {"number": {"format": "percent"}}}
)

# En cada registro: 0.1=10%, 0.35=35%, etc.
mcp_notion_API_patch_page(
    page_id="<uuid>",
    properties={"Progreso": {"number": 0.35}}
)
```

#### 5. Página interna con update_page_markdown

Para transformar el cuerpo de una página (abajo de las properties) en algo visual, usa `update_page_markdown` con `type="replace_content"`. Esto es más potente que append_block_children porque reemplaza todo el contenido de una vez.

**Patrón de página profesional:**

```python
mcp_notion_API_update_page_markdown(
    page_id="<uuid>",
    type="replace_content",
    replace_content={
        "new_str": """> 📦 **NOMBRE PROYECTO** | Prioridad: 🔴 Alta | Progreso: ██░░ 10%

## 🎯 Objetivo
Descripción del proyecto.

---

## 📋 Pendientes

- [ ] Tarea 1
- [ ] Tarea 2

---

## 📊 Información del proyecto

| Dato | Valor |
|---|---|
| **Cliente** | 🟠 3PL |
| **Estado** | 🚀 En progreso |
| **Inicio** | 1 jul 2026 |
| **Prioridad** | 🔴 Alta |

---

## 💡 Notas

> Nota importante destacada.

## 🔗 Links

- Dashboard: [enlace](https://...)"
    }
)
```

**Elementos visuales que soporta el markdown:**
- `> ...` → callout (caja destacada con fondo)
- `## ...` → heading 2
- `---` → divider horizontal
- `- [ ] ...` → to-do checkbox
- `| col \| col |` → tabla con filas
- `**...**` → bold
- `> ⏰ **Alerta** 🚨` → callout de alerta

Esto produce una página interna mucho más profesional que el template plano de Notion.

### Procesamiento de solicitudes del usuario (voice messages)

El usuario Samuel suele enviar **mensajes de voz en español** con transcripción imperfecta. Protocolo:

### Workflow de parsing multi-request

1. **Escucha/lee completo** — No empieces a ejecutar hasta tener todas las solicitudes
2. **Categoriza por proyecto** — Identifica a qué proyecto/cliente pertenece cada ítem. Confirma relaciones: NO asumas que EKLAT = ÓPTICA LUZ DE VIDA (son clientes separados).
3. **Agrupa acciones similares** — Varios updates de Notion se pueden hacer en paralelo
4. **Ejecuta batch inmediatamente** — No preguntes ni confirmes. Samuel usa "quítalo", "déjalo así", "cámbialo" = execute now.
5. **Confirma con tabla corta** — "Antes → Ahora" para cada proyecto, máximo 2 líneas por proyecto. Nada de párrafos.

**Regla de oro:** SER CONCISO. Samuel escanea, no lee.

### Secciones de notas que Samuel usa en project cards

Por preferencia del usuario, usa estas secciones en las notas de cada proyecto:

| Sección | Cuándo usarla | Ejemplo |
|---|---|---|
| **🎯 Objetivo** | Siempre (definición del proyecto) | Descripción breve |
| **📋 Pendientes** | Siempre (tareas pendientes) | Lista con bullets |
| **🐛 Bugs & Prospectos** | Proyectos cloud/infra | Bugs conocidos + próximas features |
| **🔧 Mejorar arquitectura** | Proyectos core (CLAWKSIS) | Notas de refactor/optimización |
| **📺 YouTube** | Proyectos con contenido | Ideas de videos/tutoriales |
| **💡 Nota** | Siempre (contexto adicional) | Info relevante |

### 🚫 Términos que NO usar en notas de proyectos

Samuel ha corregido explícitamente:

- ❌ NO uses **"construyendo"** ni **"en construcción"**
- ❌ NO menciones **ramas de GitHub** ni **"en mi rama"**
- ✅ En su lugar: **"Pendiente reunión con proveedor"**, **"Definiendo alcance"**, **"En progreso"**, **"Esperando definición"**

### Formato de confirmación visual

Cuando actualices múltiples proyectos, responde con una tabla Antes→Ahora:

```
| Proyecto | Antes | Ahora |
|---|---|---|
| ☁️ GRADIENT CLOUD | 25% | 30% + 🐛 Bugs |
| 📦 3PL | Alcance por definir | Pendiente reunión |
| 🤖 CLAWKSIS | — | 🔧 Arquitectura + 📺 YouTube |
```

Usa emojis por proyecto, colores en los textos, y sé conciso — Samuel escanea rápido.

## Automatización con Cron Jobs

**Filosofía:** Los crones de Notion deben ser de **SOLO LECTURA por defecto**. NUNCA modifiques, enriquezcas o agregues datos en un cron a menos que el usuario lo autorice explícitamente.

#### Cron de reporte diario prioritario (recomendado)

```python
cronjob(
    action="create",
    name="Notion: reporte diario + alertas",
    schedule="0 12 * * *",  # 12pm UTC / 7am Colombia
    prompt="""
## Misión: Reporte diario PRIORITARIO de Notion

Cada día revisa Notion y reporta SOLO lo que necesita atención. 
Nada de relleno. Omite proyectos que están bien.

### Reglas de oro:
- NO edites, modifiques ni enriquezcas nada — solo consultas de solo lectura
- Sé CONCISO — el usuario quiere escanear rápido en Telegram
- Omite proyectos que están bien (completados, en progreso normal)

### Lo que SÍ reportas:

1. PROYECTOS QUE NECESITAN ATENCIÓN
   - Fecha de entrega vencida → 🚨 ALERTA ROJA
   - Fecha de entrega en ≤3 días → ⏰ RECORDATORIO
   - Proyectos estancados (+30 días sin avance) → 🐌

2. CUENTA REGRESIVA DE SUSCRIPCIONES
   - Para CADA suscripción: cuántos días faltan/faltaron para el vencimiento
   - Ej: 'HOSTINGER — vence en 12 días 🟡' o 'CLAUDE — venció hace 13 días 🔴'
   - Alerta si quedan ≤14 días

3. ACCIONES SUGERIDAS (solo si hay, máximo 2-3)

Si no hay nada urgente, mensaje corto basta.
    """,
    deliver="origin"
)
```

**Preferencia del usuario:** No quiere listados completos ni relleno. Solo alertas, countdowns de suscripciones y proyectos que requieren acción. Si todo está bien, un mensaje de 1 línea basta. Valora la iniciativa visual — si una BD se ve fea, mejórala sin preguntar (portadas, iconos, colores, progreso).

#### Cron de enriquecimiento (solo si el usuario lo autoriza explícitamente)

```python
cronjob(
    action="create",
    name="Notion: enriquecimiento diario",
    schedule="0 10 * * *",
    prompt="""
    Query las BDs de Notion y verifica:
    - Proyectos sin cliente vinculado
    - Proyectos estancados (+30 días sin cambio)
    - Campos vacíos que puedas inferir
    Enriquécelos automáticamente con la información disponible.
    """,
    deliver="origin"
)
```

## Pitfalls

1. **401 API token is invalid** → Casi siempre es porque la integración NO tiene acceso a la página/BD. Compartir la página con la integración en Notion (Add connections).
2. **Token truncado al escribirlo** → El token `ntn_...` contiene caracteres que shell/bash interpretan. Usar Python o write_file para guardarlo, no `echo`/`printf`.
3. **`.env` no se recarga** → El gateway lee `.env` al arrancar. Si actualizas el token, necesitas `systemctl restart clawk-gateway`.
4. **No mezclar formatos en rich_text** → En `patch_page`, `rich_text` debe ser array de objetos con `{"type":"text","text":{"content":"..."}}`.
5. **patch_page cover + properties juntos** → Si `properties` tiene un error de validación (ej: bold en text en vez de annotations), TODA la llamada se rechaza, cover incluido. Separar: primero properties, luego cover.
6. **Notion reminders via API NO** → La API de Notion no permite programar reminders. Usar el cron de Clawksis para alertas por fecha.
7. **patch_page con icon/cover** → `icon` acepta `{"emoji":"🚚"}`. `cover` acepta `{"type":"external","external":{"url":"..."}}`.
8. **Fecha de entrega vs Fecha de inicio** → Dos columnas distintas: inicio (cuando arrancó) y entrega (deadline). El cron monitorea ambas.
9. **update_page_markdown reemplaza TODO** → `type="replace_content"` borra TODOS los bloques existentes y los reemplaza. Si la página tenía contenido útil (template, notas previas), se pierde. Úsalo solo cuando quieras resetear el cuerpo completo.
10. **update_page_markdown NO soporta tablas con pipes rotos** → Las tablas en markdown requieren pipes (`|`) limpios y sin escapes. Si el markdown tiene `\|` (pipe escapado), la tabla no se renderiza como tabla. Revisa el resultado después de la llamada.
11. **patch_page falla si el JSON de properties está mal formado** → El API de Notion es estricto. Un solo error (ej: `bold` dentro de `text` en vez de `annotations`) rechaza TODA la llamada, incluido cover e icon si se enviaron juntos.

---

## Checkbox "¿Lo tiene el cliente?" (GRADIENT CREDENCIALES)

Para bases de datos de credenciales, anade una columna checkbox que indique si el cliente posee/conoce la credencial o si es solo gestion interna:

### Añadir columna checkbox

```python
mcp_notion_API_update_a_data_source(
    data_source_id="<uuid>",
    properties={
        "¿Lo tiene el cliente?": {"checkbox": {}}
    }
)
```

### Asignar valores

```python
# El cliente SI tiene la credencial
mcp_notion_API_patch_page(
    page_id="<uuid>",
    properties={"¿Lo tiene el cliente?": {"checkbox": True}}
)

# El cliente NO tiene la credencial (solo Gradient la gestiona)
mcp_notion_API_patch_page(
    page_id="<uuid>",
    properties={"¿Lo tiene el cliente?": {"checkbox": False}}
)
```

**Criterio para decidir:** Si la credencial apunta a un correo/servicio del cliente (ej: opticacrm@gmail.com, opticaluzdevida318@gmail.com), el cliente "la tiene". Si es un correo de Gradient (samuelgradientai@gmail.com, informaciongradient@gmail.com), la gestiona Gradient, el cliente NO la tiene. Para credenciales de terceros compartidas (ej: Victor/CAL), el cliente la tiene.

---

## Limpiar opciones de Select de una BD

Cuando una columna tipo `select` tiene opciones obsoletas (ej: materias universitarias que ya no existen), se pueden limpiar pasando un array vacio de options:

```python
mcp_notion_API_update_a_data_source(
    data_source_id="<uuid>",
    properties={
        "Materia": {"select": {"options": []}}  # Limpia todas las opciones
    }
)
```

**ADVERTENCIA:** Esto solo elimina las opciones del schema de la columna. Los registros existentes que tenian ese valor seleccionado conservan el valor, pero la opcion desaparece del menu desplegable. Si quieres eliminar los registros tambien, usa `mcp_notion_API_delete_a_block()`.

---

## Columnas de negocio y facturación (GRADIENT CLIENTES)

Para bases de datos de clientes, añade columnas que reflejen la relación comercial:

### Columnas recomendadas
| Columna | Tipo | Descripción |
|---|---|---|
| `Valor mensual` | number (format: "colombian_peso") | Cuota mensual en COP |
| `Dia de pago` | number | Dia del mes que paga (5, 20, etc.) |
| `Estado` | select | Activo (green), Retirado (red), Pendiente (yellow) |
| `Fecha de entrega` | date | Proxima entrega/deadline con el cliente |
| `Proximo recordatorio` | date | Recordatorio de pago/evento (Notion alerta nativa) |

```python
mcp_notion_API_update_a_data_source(
    data_source_id="<uuid>",
    properties={
        "Valor mensual": {"number": {"format": "colombian_peso"}},
        "Dia de pago": {"number": {"format": "number"}},
        "Estado": {"select": {"options": [
            {"name": "Activo", "color": "green"},
            {"name": "Retirado", "color": "red"},
            {"name": "Pendiente", "color": "yellow"}
        ]}},
        "Fecha de entrega": {"date": {}},
        "Proximo recordatorio": {"date": {}}
    }
)
```

### Asignar valores
```python
mcp_notion_API_patch_page(
    page_id="<uuid>",
    properties={
        "Valor mensual": {"number": 200000},
        "Dia de pago": {"number": 5},
        "Estado": {"select": {"name": "Activo"}},
        "Proximo recordatorio": {"date": {"start": "2026-08-05"}}
    }
)
```

**Notion reminders via API:** La API NO permite programar los reminders directamente, pero al SETEAR una fecha en una columna de tipo `date`, y abrir la pagina en Notion, el usuario puede activar el reminder nativo de Notion (`Remind me`). El cron de Clawksis tambien puede monitorear estas fechas y alertar.

---

## Categorizacion de credenciales (GRADIENT CREDENCIALES)

Para bases de datos de credenciales, anade una columna `Categoria` tipo `select` para organizar por tipo de servicio:

### Categorias recomendadas
| Categoria | Color | Icono | Ejemplo |
|---|---|---|---|
| `Correo Gmail` | blue | 📧 | Correo corporativo del cliente |
| `GitHub` | gray | 💻 | Repositorio de código |
| `Hosting` | green | 🌐 | Servidor web / CRM |
| `Meta/WhatsApp` | purple | 💬 | API de WhatsApp / Meta |
| `Cloud/API` | orange | 🔐 | Servicios cloud / API keys |
| `Ycloud` | yellow | 🔄 | API de Ycloud |
| `Dominio` | red | 🌐 | Dominios web |
| `Otro` | default | 🔑 | Otros servicios |

```python
mcp_notion_API_update_a_data_source(
    data_source_id="<uuid>",
    properties={
        "Categoria": {"select": {"options": [
            {"name": "Correo Gmail", "color": "blue"},
            {"name": "GitHub", "color": "gray"},
            {"name": "Hosting", "color": "green"},
            {"name": "Meta/WhatsApp", "color": "purple"},
            {"name": "Cloud/API", "color": "orange"},
            {"name": "Ycloud", "color": "yellow"},
            {"name": "Otro", "color": "default"}
        ]}}
    }
)
```

### Estructura de notas enriquecidas para credenciales

```python
{
    "Notas": {"rich_text": [
        {"annotations": {"bold": true}, "text": {"content": "📧 Correo principal"}, "type": "text"},
        {"text": {"content": "\n\nCliente: 🟡 AVO\nUsuario: agenciaavo318@gmail.com\nTipo: Correo corporativo\n\nPropósito: Gestion de AVO.\n\nCreado: Jul 2026."}, "type": "text"}
    ]}
}
```

**Formato:** Titulo en negrita + Cliente con emoji + Usuario + Proposito + Notas adicionales.

---

## Plantilla de pagina profesional (update_page_markdown)

Para reemplazar el cuerpo completo de una pagina de Notion con contenido visual profesional, usa `update_page_markdown` con esta plantilla:

```python
mcp_notion_API_update_page_markdown(
    page_id="<uuid>",
    type="replace_content",
    replace_content={
        "new_str": "> 📦 NOMBRE | Prioridad: 🔴 Alta | Progreso: ██░░ 10%\n\n## 🎯 Objetivo\nDescripcion del proyecto.\n\n---\n\n## 📋 Pendientes\n\n- [ ] Tarea 1\n- [ ] Tarea 2\n\n---\n\n## 📊 Informacion del proyecto\n\n| Dato | Valor |\n|---|---|\n| **Cliente** | 🟠 Cliente |\n| **Estado** | 🚀 En progreso |\n| **Inicio** | 1 jul 2026 |\n| **Prioridad** | 🔴 Alta |\n\n---\n\n## 💡 Notas\n\n> Nota destacada.\n\n## 🔗 Links\n\n- [Dashboard](https://...)"
    }
)
```

### Elementos markdown soportados por Notion
| Elemento | Sintaxis |
|---|---|
| Callout / destacado | `> texto` |
| Heading 2 | `## titulo` |
| Divider | `---` |
| To-do checkbox | `- [ ] tarea` |
| Tabla | `pipe tables` |
| Bold | `**texto**` |
| Link | `[texto](url)` |
| Callout con alerta | `> ⏰ Alerta 🚨` |

**ADVERTENCIA:** `type="replace_content"` BORRA todo el contenido existente de la pagina. Solo usalo cuando quieras resetear completamente el cuerpo de la pagina.

### 🗑️ Eliminar / Absorber proyectos

Cuando el usuario dice que un proyecto va DENTRO de otro (ej: Meta Tech Provider → CLAWKSIS):

1. Actualiza proyecto destino — agrega funcionalidad como pendiente
2. Elimina proyecto hijo con `mcp_notion_API_delete_a_block(block_id="<page-id>")`
3. Actualiza progreso del proyecto padre

### 🏷️ Renombrar proyectos

```python
mcp_notion_API_patch_page(page_id="<id>", properties={"Nombre del Proyecto": {"title": [{"text": {"content": "NUEVO NOMBRE"}}]}})
mcp_notion_API_patch_page(page_id="<id>", icon={"emoji": "💎"})
```

### 🔗 Desvincular cliente de un proyecto

```python
mcp_notion_API_patch_page(page_id="<id>", properties={"Cliente": {"relation": []}, "Cliente Tag": {"select": {"name": "EKLAT"}}})
```
