---
name: document-creation
description: "Create Word documents (.docx) with APA formatting and custom styling preferences — including Normas APA layout, color accents, Times New Roman, and reference sections."
version: 1.0.0
author: Clawksis
license: MIT
metadata:
  clawk:
    tags: [documents, word, apa, formatting, office, docx]
---

# Document Creation

## Overview

Create professional Word documents (.docx) using `python-docx`. This skill covers the user's preferred formatting: **Normas APA** with custom color accents.

## Triggers

- "haz un documento Word"
- "dame un ensayo en Word"
- "formato APA"
- "Times New Roman"
- "Normas APA"
- "documento con referencias"

## User Preferences

| Element | Preference |
|---|---|
| **Font** | Times New Roman 12pt |
| **Spacing** | Double (2.0) for APA; 1.5 for La Sabana style |
| **Margins** | 1 inch (2.54 cm) |
| **Heading color** | Orange (`RGBColor(0xFF, 0x6B, 0x00)`) |
| **Format** | Normas APA |
| **References** | APA style (7th ed.), hanging indent |
| **Title page** | Centered, APA-compliant |
| **Tone** | Humanized/natural — like a person talking, NOT robotic/formal |
| **Length** | Content = 1 page max (not counting cover) |
| **Cover style** | Universidad de La Sabana style (dark blue + orange) |

## Tone Guide

The user explicitly rejected formal/robotic academic language. Write essays as if you're casually explaining your opinion to a classmate. Use:
- First person ("creo que", "me parece", "analizándolo bien")
- Contractions and natural phrasing
- Short paragraphs
- Conversational transitions ("eso sí", "a simple vista", "por otro lado")
- NO bullet lists in the essay body (save those for data tables)
- NO numbered sections in the essay body (save headings for the analysis structure)

❌ Bad (robotic): "La primera oferta corresponde a Seguros Bolívar, la cual ofrece estabilidad laboral mediante un contrato indefinido."

✅ Good (humanized): "La primera era de Seguros Bolívar, buscando un Ingeniero de Riesgos Logísticos en Medellín, con modalidad híbrida y contrato indefinido."

## Dependencies

```bash
uv pip install python-docx
```

## Template Structure

### 1. APA Setup

```python
from docx import Document
from docx.shared import Inches, Pt, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH

doc = Document()

# Font
style = doc.styles['Normal']
font = style.font
font.name = 'Times New Roman'
font.size = Pt(12)
style.paragraph_format.line_spacing = 2.0
style.paragraph_format.space_after = Pt(0)

# Margins
for section in doc.sections:
    section.top_margin = Cm(2.54)
    section.bottom_margin = Cm(2.54)
    section.left_margin = Cm(2.54)
    section.right_margin = Cm(2.54)

# Colors
ORANGE = RGBColor(0xFF, 0x6B, 0x00)
BLACK = RGBColor(0x00, 0x00, 0x00)
```

### 2. Helper Functions

```python
def set_font(run, name='Times New Roman', size=12, bold=False, italic=False, color=BLACK):
    run.font.name = name
    run.font.size = Pt(size)
    run.bold = bold
    run.italic = italic
    run.font.color.rgb = color

def add_apa_heading(doc, text, level):
    h = doc.add_heading(text, level=level)
    for run in h.runs:
        run.font.name = 'Times New Roman'
        run.font.color.rgb = ORANGE
        run.bold = True
    h.paragraph_format.line_spacing = 2.0
    return h
```

### 3. Title Page (APA)

```python
for _ in range(4):
    doc.add_paragraph()

add_para(doc, 'Title', bold=True, size=16, color=ORANGE, alignment=WD_ALIGN_PARAGRAPH.CENTER)
add_para(doc, 'Author Name', size=12, alignment=WD_ALIGN_PARAGRAPH.CENTER)
add_para(doc, 'Course', size=12, alignment=WD_ALIGN_PARAGRAPH.CENTER)
add_para(doc, 'Professor', size=12, alignment=WD_ALIGN_PARAGRAPH.CENTER)
add_para(doc, 'Year', size=12, alignment=WD_ALIGN_PARAGRAPH.CENTER)
doc.add_page_break()
```

### 3b. La Sabana Style Cover

For the user's university assignments (Universidad de La Sabana):

```python
DARK_BLUE = RGBColor(0x00, 0x2B, 0x5C)
ORANGE = RGBColor(0xFF, 0x6B, 0x00)

def mkp(text, bold=False, size=14, align=WD_ALIGN_PARAGRAPH.CENTER, color=None):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.font.name = 'Times New Roman'
    r.font.size = Pt(size)
    r.bold = bold
    if color:
        r.font.color.rgb = color
    p.alignment = align
    p.paragraph_format.line_spacing = 1.5
    return p

# Header
mkp('UNIVERSIDAD DE LA SABANA', bold=True, size=20, color=DARK_BLUE)
mkp('Facultad de Ingeniería', size=14, color=DARK_BLUE)

# Orange separator
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run('─' * 50)
r.font.color.rgb = ORANGE
r.font.size = Pt(8)

# Title
mkp('ENSAYO COMPARATIVO', bold=True, size=18, color=ORANGE)
mkp('Subtítulo del trabajo', bold=True, size=16, color=DARK_BLUE)

# Course & professor
mkp('PPCO | Micros', size=14)
mkp('Prof. William Javier Guerrero Rueda', size=13)

# Author
mkp('Samuel Gómez', bold=True, size=14, color=DARK_BLUE)

# Location & date
mkp('Chía, Cundinamarca', size=12)
mkp('Julio 2026', size=12)
```

Spacing for La Sabana covers: use 1.5 (not 2.0), with extra blank paragraphs between sections for visual balance.

### 4. References (APA Hanging Indent)

```python
p.paragraph_format.left_indent = Cm(1.27)
p.paragraph_format.first_line_indent = Cm(-1.27)
```

### 4b. LinkedIn Job Citation Format (APA)

When citing LinkedIn job postings in references:

```python
# Format:
# Company. (Year, Month). Job Title [Anuncio de empleo]. LinkedIn. URL

# Example:
'Seguros Bolívar. (2026, julio). Ingeniero de Riesgos Logísticos [Anuncio de empleo]. LinkedIn. https://www.linkedin.com/jobs/search/?currentJobId=4435809899'
```

### 4c. One-Page Humanized Essay Pattern

For the user's PPCO essays:

1. **Cover page** (page 1): La Sabana style
2. **Content** (page 2): Exactly 1 page, humanized tone
3. Title heading in ORANGE at level 1
4. Body uses `WD_ALIGN_PARAGRAPH.JUSTIFY` alignment
5. References on page 3 if needed
6. Total = cover + 1 page content + (optional) references page

## Pitfalls

- `python-docx` is NOT in the default Python env — always `uv pip install python-docx` first
- The `execute_code` sandbox may not have `python-docx` — use `terminal()` for the install, then `terminal()` for the script run
- Use `terminal()` with multi-line Python to run the full document generation — `execute_code` may fail on `from docx import Document`
  - Alternative: write the script to a file with `write_file()`, then run it with `terminal()`
- For paragraph spacing: always set `line_spacing = 2.0` AND `space_after = Pt(0)` to avoid extra gaps
- For bullet lists in APA: set `left_indent` and `first_line_indent` properly (negative for hanging)
- **For multi-line Python scripts**: use `terminal()` with a heredoc (`python3 << 'PYEOF'`) to avoid escaping issues. Do NOT use `execute_code` for docx generation — it often fails on import.
- **Page breaks in python-docx**: Use `doc.add_page_break()` — do NOT try to construct XML page breaks manually (lxml parsing errors)
- **Cover page centering**: Set alignment on each paragraph AFTER they're all created, or inline in the add function. Setting alignment on the Paragraph element works. Running `WD_ALIGN_PARAGRAPH.CENTER` on the Normal style won't center the cover page text.

## OCR for extracting assignment requirements

When the user sends a screenshot (Teams assignment, class instructions, cover page image), use the OCR workflow in `references/ocr-image-text-extraction.md` to extract text before creating the document.

## Verification Checklist

- [ ] Font is Times New Roman 12pt throughout
- [ ] Line spacing is exactly 2.0 (double)
- [ ] Margins are 1 inch all around
- [ ] Headings use orange color
- [ ] References have hanging indent
- [ ] No extra spaces between paragraphs
- [ ] File saves to `/root/<filename>.docx`
- [ ] Send via MEDIA: path to deliver to user
