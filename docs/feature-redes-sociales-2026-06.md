# Feature: Generación de contenido para redes sociales

**Fecha**: junio 2026
**Cliente piloto**: Agencia de viajes PyME (5-20 clientes/mes)
**Status**: decisiones de diseño aprobadas, listo para arquitectura

---

## Las 5 decisiones (sesión del 30 jun)

### 1. Imágenes
**Híbrido**: Unsplash API (fotos reales gratis) + Flux Schnell vía fal.ai (overlays con texto sobre fondo).

- Costo Unsplash: $0
- Costo Flux: ~$0.003/imagen
- Costo mensual estimado: $0.27/mes para 90 imágenes

### 2. Contexto del negocio
**B + C combinados**:
- B) Perfil de negocio persistente (setup inicial 1 vez)
- C) Análisis de posts existentes (sube 5-10 posts, Clawksis aprende estilo)

### 3. Generación de texto
**Mismo texto para las 3 redes** (Nivel 1).
- Razón: arrancar rápido, evitar costos hasta validar.
- Si la agencia pide adaptación por red → 30 min de upgrade después.

### 4. Invocación
**Por chat** ("generame un post sobre Bali").
- Razón: cero UI nueva, máxima velocidad.
- Después: cuando exista sistema de empleados, migra al chat de "Lucas — CM".

### 5. API keys
**Híbrido**:
- Free tier: 10 generaciones con la key de Andres (para demo/prueba)
- Después: el usuario pone su propia key (alineado con self-hosting)

---

## Output esperado del feature

Por cada generación, Clawksis entrega un .zip con:

- `instagram-post.jpg` (1080×1350 vertical)
- `instagram-caption.txt`
- `tiktok-portada.jpg` (1080×1920 vertical)
- `tiktok-descripcion.txt`
- `youtube-thumb.jpg` (1280×720 horizontal)
- `youtube-titulo-desc.txt`

Entrega por: descarga directa + opcional Telegram (cron job).

---

## Arquitectura (pendiente de detallar)

### Backend
- Nueva tabla `business_profiles` (id, user_id, name, tone, destinos, hashtags, embeddings_posts)
- Skill nuevo `generate_social_content` con pipeline:
  1. Cargar business_profile
  2. Generar caption + hashtags
  3. Buscar fotos en Unsplash matching el tema
  4. Generar overlay con Flux Schnell (texto sobre foto)
  5. Redimensionar para cada red (PIL)
  6. Empaquetar .zip
  7. Retornar URL de descarga + opcional enviar por Telegram

### Frontend
- Setup wizard inicial (2 pasos) en `/onboarding/business`
- Sección "API keys" en Settings (OpenAI + fal.ai + Unsplash opcional)
- Chat normal — el skill se dispara cuando el usuario menciona contenido/post/redes

---

## Roadmap de implementación

### Sesión 1 (próxima) — Arquitectura + setup base (2-3h)
- [ ] Crear migración SQL para `business_profiles`
- [ ] Crear endpoints CRUD del perfil
- [ ] Skill `generate_social_content` con stub (devuelve placeholder)
- [ ] Integración Unsplash API (buscar y descargar)
- [ ] Testing manual con prompt simple

### Sesión 2 — Generación de texto (3-4h)
- [ ] Skill genera caption + hashtags usando perfil
- [ ] Lógica de selección de foto desde resultados Unsplash
- [ ] Output: foto + texto sin overlay (V1)

### Sesión 3 — Overlay con Flux (3-4h)
- [ ] Setup de fal.ai (key + cliente)
- [ ] Generación de overlay con texto sobre foto base
- [ ] Redimensionado por red (PIL)

### Sesión 4 — Empaquetado + entrega (2-3h)
- [ ] Empaquetar .zip con archivos finales
- [ ] Integración con sistema de archivos del dashboard
- [ ] Opcional: entrega por Telegram (reusa infraestructura existente)

### Sesión 5 — Testing con agencia real (2-3h)
- [ ] Onboarding de la agencia piloto
- [ ] Generación de 10 posts de prueba
- [ ] Ajustes según feedback

### Sesiones futuras (si la agencia lo pide)
- Texto adaptado por red (Nivel 1 pro)
- Posteo automático (Nivel 3)
- Calendarios editoriales sugeridos
- Plantillas guardadas

---

## Decisiones explícitamente DESCARTADAS

- ❌ Stable Diffusion self-hosted (VPS no tiene GPU)
- ❌ Solo DALL-E (más caro, no aporta sobre Flux Schnell)
- ❌ Solo Flux (sin Unsplash → todo inventado, no sirve para viajes reales)
- ❌ Texto adaptado por red en V1 (sobre-ingeniería antes de validar)
- ❌ Página dedicada /contenido en V1 (chat es más rápido para arrancar)
- ❌ Solo mi key (no escala) o solo key del usuario (fricción inicial)

---

## Limitaciones aceptadas para V1

- Sin adaptación por red (mismo texto para IG/TikTok/YouTube)
- Sin posteo automático (usuario sube manualmente)
- Sin generación de video (solo imágenes)
- Sin scheduling complejo (cron simple si lo piden)

Estas limitaciones son intencionales para validar rápido.

---

*Brief de decisiones tomadas el 30 jun 2026.*
*Próxima sesión: presentar arquitectura visual + arrancar Sesión 1 del roadmap.*

---

## Validación visual del concepto (30 jun 2026)

✅ **Test visual exitoso con script de prueba** (pre-implementación).

Resultado: imagen 1080×1920 con foto real de Bali de Unsplash, gradient
elegante de abajo hacia arriba, tipografía DejaVu Sans Bold, sombras
sutiles para legibilidad. Aprobado por Andres como "MUY MEJOR que la
prueba básica anterior".

Referencia visual guardada en: `docs/concept-images/bali-concept-validated-2026-06-30.jpg`

Stack confirmado funcional:
- Unsplash API (Access Key configurada en .env)
- Pillow 12.2.0 (instalada en .venv)
- DejaVu Sans Bold (en assets/fonts/)

**Tiempo de generación**: ~3 segundos por imagen (1s Unsplash + 2s PIL).
**Calidad final**: 92, ~300-500KB por imagen.

### Pregunta de Andres sobre carruseles

"Si por ejemplo le pedimos un carrusel para IG podría hacerlo?"

**Respuesta**: Sí, totalmente factible. El código que tendremos para UN post
se reutiliza ~90%. Carrusel = loop por N slides. El LLM decide la estructura
(qué slides, qué texto) y el helper compone cada slide.

Estimación adicional para soportar carruseles: ~2h después del feature base.
Esto SE VA al roadmap como Sesión 3 (post-MVP).

