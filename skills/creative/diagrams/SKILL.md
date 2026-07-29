---
name: diagrams
description: "Create visual diagrams: hand-drawn Excalidraw JSON diagrams or dark-themed SVG architecture/cloud/infra diagrams as HTML."
version: 1.0.0
author: Clawksis
license: MIT
platforms: [linux, macos, windows]
metadata:
  clawk:
    tags: [diagrams, excalidraw, architecture, svg, visualization, infrastructure, diagramming]
    related_skills: [sketch, design-md, ui-design]
---

# Diagrams

Generate two styles of technical diagrams, depending on the audience and context:

| Style | Tool | Output | Best for |
|-------|------|--------|----------|
| **Hand-drawn / Whiteboard** | Excalidraw JSON | `.excalidraw` files (drag-and-drop onto excalidraw.com) | Architecture sketches, flowcharts, sequence diagrams — informal, collaborative, editable |
| **Dark-themed / Production** | SVG-as-HTML | Standalone `.html` file | System architecture, cloud infra, microservice topology — polished, shareable, self-contained |

---

## Excalidraw (Hand-drawn style)

Uses the standard Excalidraw element JSON format. Files can be opened at [excalidraw.com](https://excalidraw.com) for viewing and editing — no accounts or API keys needed.

### Workflow

1. Write an array of Excalidraw element objects
2. Wrap in the standard `.excalidraw` envelope and save with `write_file`
3. Optionally upload for a shareable link using the upload script

### File Format

Wrap your elements in this envelope:

```json
{
  "type": "excalidraw",
  "version": 2,
  "source": "clawksis-agent",
  "elements": [ /* ... */ ],
  "appState": { "viewBackgroundColor": "#ffffff" }
}
```

### Element Types

| Element | Type | Key fields |
|---------|------|------------|
| Rectangle | `"rectangle"` | `x`, `y`, `width`, `height`; `roundness: { "type": 3 }` for rounded |
| Ellipse | `"ellipse"` | `x`, `y`, `width`, `height` |
| Diamond | `"diamond"` | `x`, `y`, `width`, `height` |
| Arrow | `"arrow"` | `points: [[dx,dy],...]`, `endArrowhead`, `startBinding`/`endBinding` |
| Text (standalone) | `"text"` | `text`, `fontSize: 20`, `fontFamily: 1` |

### Labeled Shapes (Container Binding)

Use `boundElements` on the shape and `containerId` on the text:

```json
{ "type": "rectangle", "id": "r1", "x": 100, "y": 100, "width": 200, "height": 80,
  "backgroundColor": "#a5d8ff", "fillStyle": "solid",
  "boundElements": [{ "id": "t_r1", "type": "text" }] },
{ "type": "text", "id": "t_r1", "x": 105, "y": 110, "width": 190, "height": 25,
  "text": "Label", "fontSize": 20, "fontFamily": 1, "strokeColor": "#1e1e1e",
  "textAlign": "center", "verticalAlign": "middle",
  "containerId": "r1", "originalText": "Label", "autoResize": true }
```

**Critical:** Do NOT use `"label": { "text": "..." }` — this is silently ignored by Excalidraw.

### Arrow Bindings

```json
{ "type": "arrow", "id": "a1", "x": 300, "y": 150, "width": 150, "height": 0,
  "points": [[0,0],[150,0]], "endArrowhead": "arrow",
  "startBinding": { "elementId": "r1", "fixedPoint": [1, 0.5] },
  "endBinding": { "elementId": "r2", "fixedPoint": [0, 0.5] } }
```

### Z-Order Rules

Array order = z-order (first = back, last = front). Emit progressively:
`bg_zone → shape1 → text_for_shape1 → arrow1 → arrow_label → shape2 → text_for_shape2 → ...`

### Color Palette

| Use | Fill | Hex |
|-----|------|-----|
| Primary / Input | Light Blue | `#a5d8ff` |
| Success / Output | Light Green | `#b2f2bb` |
| Warning / External | Light Orange | `#ffd8a8` |
| Processing | Light Purple | `#d0bfff` |
| Error / Critical | Light Red | `#ffc9c9` |
| Notes / Decisions | Light Yellow | `#fff3bf` |
| Storage / Data | Light Teal | `#c3fae8` |

### Tips

- Minimum `fontSize`: 16 for body, 20 for headings
- Minimum shape size: 120x60
- Minimum gap between elements: 20px
- Never use emoji in text (doesn't render in Excalidraw's font)
- Text contrast: minimum `#757575` on white backgrounds

---

## Architecture Diagram (Dark-themed SVG)

Professional, dark-themed technical architecture diagrams as standalone HTML files with inline SVG. No external tools, API keys, or rendering libraries.

### When to use

**Best suited for:** software system architecture, cloud infrastructure (VPC/subnets/services), microservice topology, database + API maps, deployment diagrams.

**Look elsewhere for:** scientific subjects, physical objects, floor plans, hand-drawn sketches (use Excalidraw above).

### Visual Design System

| Component Type | Fill | Stroke |
|---------------|------|--------|
| Frontend | `rgba(8, 51, 68, 0.4)` | `#22d3ee` (cyan) |
| Backend | `rgba(6, 78, 59, 0.4)` | `#34d399` (emerald) |
| Database | `rgba(76, 29, 149, 0.4)` | `#a78bfa` (violet) |
| AWS/Cloud | `rgba(120, 53, 15, 0.3)` | `#fbbf24` (amber) |
| Security | `rgba(136, 19, 55, 0.4)` | `#fb7185` (rose) |
| Message Bus | `rgba(251, 146, 60, 0.3)` | `#fb923c` (orange) |
| External | `rgba(30, 41, 59, 0.5)` | `#94a3b8` (slate) |

- **Font:** JetBrains Mono (Google Fonts CDN)
- **Sizes:** 12px names, 9px sublabels, 8px annotations
- **Background:** Slate-950 `#020617` with 40px grid pattern

### Component Rendering

Components are rounded rectangles (`rx="6"`) with 1.5px strokes. Use **double-rect masking** (opaque background rect first, then semi-transparent styled rect on top) to prevent arrow bleed-through.

### Connection Rules

- Draw arrows in SVG **before** component boxes (behind them visually)
- Security flows: dashed rose `#fb7185`
- Security groups: dashed `4,4` rose
- Regions: large dashed `8,4` amber, `rx="12"`
- Standard height: 60px, vertical gap: minimum 40px

### Document Structure

Four-part layout:
1. **Header** — title with pulsing dot + subtitle
2. **Main SVG** — the diagram in a rounded border card
3. **Summary cards** — grid of three info cards
4. **Footer** — minimal metadata

**Single file:** self-contained HTML, no external deps except Google Fonts, no JavaScript.

### Legend Placement

**Critical.** Must be placed outside all boundary boxes. Calculate lowest Y-coordinate and place legend at least 20px below it.

---

## Common Pitfalls

- **Excalidraw labels:** `"label": { "text": "..." }` on shapes is NOT valid — use `boundElements` + separate text element with `containerId`
- **Excalidraw z-order:** all rectangles, then all texts = bad. Interleave shape → its text → its arrows
- **Architecture legend:** must be placed outside all boundary boxes
- **Arrow under components:** draw arrows before component rects in SVG
- **Font compatibility:** architecture diagrams need JetBrains Mono from Google Fonts for the monospace aesthetic

## References

See full details in:
- `references/excalidraw-full.md` — complete Excalidraw element reference (fonts, sizing, dark mode, examples)
- `references/architecture-diagram-full.md` — complete architecture diagram template and component examples
