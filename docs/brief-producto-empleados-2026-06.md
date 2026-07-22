# Brief de Producto: Clawksis como "Empleado-Herramienta"

**Fecha**: junio 2026
**Autor**: Andres (entrevista de producto guiada con copiloto)
**Status**: aprobado para implementación
**Próxima revisión**: después del MVP del onboarding

---

## TL;DR (1 párrafo)

Clawksis se reposiciona de "chat con IA" a **"contratá tu primer empleado-herramienta"**.
El usuario no abre un chatbot, contrata un staff de 4 empleados especializados
(Sofía, Marcos, Diego, Carla) que trabajan en su computadora/server, ejecutando
tareas autónomas programadas. El momento "wow" del onboarding es ver al primer
empleado **entregar un reporte por Telegram** sin que el usuario tenga que
intervenir manualmente.

---

## Target primario

**Profesionales no-técnicos** (consultores independientes, escritores, dueños de
micro-empresas) **+ pequeñas empresas/equipos** que quieren self-hosting por
privacidad de sus documentos.

**NO es el target**: devs que ya usan Cursor/Copilot, hackers/makers que
disfrutan tinkerear.

## Dolor real (martes 10am)

> "Tengo tareas recurrentes que requieren contexto mantenido en el tiempo,
> y no quiero ni explicar todo cada vez ni contratar a alguien para hacerlas."

Síntomas que el usuario reporta:
1. Gasta horas en tareas repetitivas (reportes semanales, resúmenes, organización)
2. Necesita procesos automatizados pero no sabe programar
3. ChatGPT no tiene memoria entre sesiones, reexplica cada vez el contexto

## Propuesta de valor

> "Clawksis es como Notion AI + Zapier + tu equipo de freelancers, corriendo en
> tu propio server, sin lock-in."

No competimos con ChatGPT. **Competimos con "contratar 3 freelancers"**.
Diferenciación: privacidad + cero salarios + escala infinita + ejecuta tareas
autónomas (no solo conversa).

---

## Modelo conceptual: VARIOS empleados especializados

Rechazamos el modelo "un chat genérico" (modelo A) y "un agente con proyectos"
(modelo C). Vamos con **modelo B**: cada empleado es una entidad propia con:

- Nombre + identidad propia
- Skills específicas habilitadas (no las 78, solo las suyas)
- System prompt/contexto propio
- Memoria persistente entre sesiones
- Cron jobs propios (lo que hace mientras no estás)
- Sesiones de chat propias

El **centro del producto deja de ser "Chat"**. Pasa a ser "Mi equipo".

## Los 4 empleados pre-armados

| Empleado | Rol | Skills primarias |
|---|---|---|
| **Sofía** | Asistente Personal | Agenda, recordatorios, organización |
| **Marcos** | Analista de Datos | CSVs, reportes, gráficos, code execution |
| **Diego** | Investigador | Research, scrapping, síntesis de fuentes |
| **Carla** | Contadora | Facturas, gastos, reportes financieros |

**Tomás (Desarrollador) queda FUERA del onboarding default** — disponible en
galería separada "Para usuarios avanzados". Razón: contradice el target de
"profesionales no-técnicos".

---

## Momento "wow" del onboarding

Escena concreta de 3 minutos con **Marcos**:

> Usuario: "Marcos, todos los viernes a las 9am quiero un ranking de los 5
> productos más vendidos por Telegram."
>
> Marcos: "Listo. Te lo armo de ventas.csv. ¿Querés que lo envíe al chat
> que tengo configurado contigo o agregás otro destinatario?"
>
> Usuario: "Al mío nomás."
>
> Marcos: "Hecho. Primer envío: este viernes 21/06 a las 9:00am.
> Te muestro un preview de cómo se verá ahora →"

El viernes a las 9am el usuario recibe en Telegram el reporte. **Ahí se enamora.**

## Canal del MVP: Telegram

**Razones objetivas de elegir Telegram primero**:
1. El backend YA lo tiene (`tools/cronjob_tools.py` soporta `deliver=telegram:...`)
2. Setup más rápido que SMTP (escanear QR del bot)
3. Móvil-first: notificación instantánea, no enterrado en email
4. Cubre el perfil "empresas/equipos" que ya usan canales modernos

Email queda como **segunda fase**, decidido por feedback real, no por
asunción anticipada.

---

## Roadmap de implementación

### Fase 3.1 — Onboarding wizard (sesión propia, 6-8h)
- Primera carga muestra wizard: "¿Conocé a tu equipo?"
- 4 cards de empleados con descripción breve
- Usuario elige UNO para empezar (Marcos sugerido por default)
- Setup de Telegram: QR del bot + confirmación de conexión
- Demo guiada: "Programá tu primera tarea" → CSV + cron + Telegram

### Fase 3.2 — Página "Mi equipo" (sesión propia, 6-8h)
- Reemplaza el actual "Chat" como home
- Cards de empleados con avatar, rol, tareas activas
- Click en card → chat con ese empleado
- Botón "Contratar otro empleado" → galería

### Fase 3.3 — Galería de empleados/skills (sesión propia, 8-10h)
- Templates de empleados (los 4 + extras de comunidad)
- Filtros por área (operaciones, datos, finanzas, etc)
- "Agregar al equipo" con 1 click
- Tomás vive aquí (para usuarios avanzados)

### Fase 3.4 — Renombrar "Cron" → "Tareas autónomas" (sesión propia, 2-4h)
- Cambio nominal en UI + docs
- Promover en home: "Tu equipo trabaja mientras dormís"
- Onboarding muestra esta capacidad antes del chat

---

## Lo que NO hacemos (descartado conscientemente)

- ❌ Modelo "asistente generalista único" (sería ChatGPT clon)
- ❌ Modelo "un agente con proyectos" (más complejo para target no-técnico)
- ❌ Email como canal del MVP (Telegram primero)
- ❌ Tomás (dev) en onboarding default (contradice target)
- ❌ Search bar / rename / archive del sidebar de sesiones por ahora
  (son features técnicas que NO mueven la aguja del producto)

## Métricas de éxito (para evaluar después del MVP)

1. **Activación**: % de usuarios que completan el onboarding (contratan empleado)
2. **Wow point**: % que recibe su primer reporte autónomo (viernes 9am)
3. **Retención día 7**: % que sigue teniendo tareas activas a la semana
4. **Equipo activo**: # promedio de empleados activos por usuario

---

## Decisiones pendientes (para próximas sesiones)

- ¿Pricing futuro? Por empleado, por uso, freemium?
- ¿Marketplace de empleados creados por la comunidad?
- ¿Sistema de templates/scripts que se comparten entre empleados?
- ¿Slack/Discord/SMS llegan como canales después de email?

---

*Este brief es el resultado de 7 preguntas estructuradas en una entrevista
guiada el día Thursday, June 18, 2026. Refleja las decisiones del founder
(Andres) con criterio de producto del copiloto.*
