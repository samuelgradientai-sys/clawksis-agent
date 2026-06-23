# Roadmap Clawksis — Notas de Andres (junio 2026)

## Estado actual (post sesión maratónica de hoy)

**Chat moderno completo en producción:**
- Toggle Terminal/Modern persistido
- WebSocket JSON-RPC con streaming + tools + markdown
- Sidebar de sesiones con switching
- File picker funcional (texto plano, hasta 100KB)
- Auto-titulado inteligente (heurística sobre system prompts tóxicos)

**Stack actual:**
- Backend: Python + tui_gateway (JSON-RPC 2.0 / WebSocket)
- Frontend: React + Vite + Tailwind + lucide
- Persistencia: SQLite (sessions, messages, titles, preview)
- Modelos: DeepSeek, Anthropic, OpenAI, OpenRouter, etc

## Pendientes por categoría

### Pulido del chat (★★ — bajo impacto producto, alto impacto UX dev)
- [ ] Search bar en sidebar para filtrar por título
- [ ] Agrupación por fecha (Hoy/Ayer/Semana)
- [ ] Atajos de teclado (Ctrl+K nueva, Ctrl+/ buscar)
- [ ] Rename manual de sesión en hover
- [ ] Delete/Archive sesiones viejas

### Multimodal (★★★ — sesión propia cada una)
- [ ] B2 — Subir imágenes (requiere endpoint POST upload + integración image.attach)
- [ ] B3 — Grabación de voz (decidir proveedor STT: Whisper API vs Web Speech)

### Producto (★★★★★ — donde está la aguja)
- [ ] Onboarding del primer minuto (wizard + 3 demos curadas)
- [ ] Marketplace/galería de skills (search, install, ratings)
- [ ] Promover capacidad agentic (renombrar Cron, home destaca tareas autónomas)

### Bugs conocidos no críticos
- [ ] 401 Unauthorized en /api/auth/me (cosmético)
- [ ] Bug #30: clawk dashboard --status no detecta duplicados

## Decisión estratégica pendiente

¿Cuál es el target principal de Clawksis?
- **Devs power users** → priorizar marketplace skills + agentic
- **Público amplio** → priorizar onboarding + simplicidad

Esa decisión cambia el orden del roadmap completo.

## Commits clave de esta sesión
