---
name: docx
description: "Create, read, edit Word .docx (python-docx); convert md→docx (pandoc) and docx→pdf (LibreOffice)."
version: 1.0.0
author: Clawksis
license: MIT
platforms: [linux, macos, windows]
metadata:
  clawk:
    tags: [Word, DOCX, Documents, Reports, Conversion, Productivity]
    related_skills: [pdf, doc-coauthoring, ocr-and-documents]
---

# Word (.docx) Toolkit

Create, read and edit Word documents with open-source tooling. Use this skill
whenever a `.docx` is involved — as input, output, or both: drafting contracts,
reports or letters; reading/extracting text from a Word file; editing an
existing document; converting Markdown → docx or docx → PDF.

**Routing:** PDF output/manipulation → `pdf` skill · text extraction from scans
→ `ocr-and-documents` · co-writing the *content* of a doc with the user →
`doc-coauthoring` (then produce the file here).

## Prerequisites

```bash
pip install python-docx
# opcionales según tarea:
#   pandoc       → markdown → docx con estilos (https://pandoc.org)
#   libreoffice  → docx → pdf headless
```

## Create a document (python-docx)

```python
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

doc = Document()

doc.add_heading("Propuesta comercial", level=0)
p = doc.add_paragraph("Preparado para ")
p.add_run("Cliente S.A.").bold = True
p.add_run(" — julio 2026.")

doc.add_heading("Alcance", level=1)
for item in ["Descubrimiento", "Implementación", "Soporte"]:
    doc.add_paragraph(item, style="List Bullet")

table = doc.add_table(rows=1, cols=2)
table.style = "Light Grid Accent 1"
hdr = table.rows[0].cells
hdr[0].text, hdr[1].text = "Concepto", "Precio"
row = table.add_row().cells
row[0].text, row[1].text = "Plan Pro", "$99/mes"

doc.add_picture("logo.png", width=Cm(4))
doc.save("propuesta.docx")
```

Styling a run: `run.font.size = Pt(12)`, `run.font.color.rgb = RGBColor(0x6C, 0x4F, 0xD6)`,
`paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER`.

## Read / extract text

```python
from docx import Document

doc = Document("contrato.docx")
text = "\n".join(p.text for p in doc.paragraphs)

for table in doc.tables:
    for row in table.rows:
        print([c.text for c in row.cells])
```

(Headers/footers live in `section.header.paragraphs`; comments and tracked
changes are not exposed by python-docx — flag that limitation if it matters.)

## Edit an existing document

```python
from docx import Document

doc = Document("plantilla.docx")


# Replace placeholders run-safe (a naive paragraph.text= drops formatting)
def replace_everywhere(doc, mapping):
    def _replace_in(paragraphs):
        for p in paragraphs:
            for run in p.runs:
                for k, v in mapping.items():
                    if k in run.text:
                        run.text = run.text.replace(k, v)

    _replace_in(doc.paragraphs)
    for t in doc.tables:
        for row in t.rows:
            for cell in row.cells:
                _replace_in(cell.paragraphs)


replace_everywhere(doc, {"{{NOMBRE}}": "Ada Lovelace", "{{FECHA}}": "2026-07-01"})
doc.save("contrato_final.docx")
```

⚠️ A placeholder split across runs (Word does this after manual edits) won't
match — normalize the template or join runs first. Always save to a **new file**.

## Markdown → docx (pandoc)

```bash
pandoc informe.md -o informe.docx
# con estilos corporativos: usar un docx de referencia
pandoc informe.md --reference-doc=estilos.docx -o informe.docx
```

This is the fastest path when the content already exists as Markdown (agent
output, notes). Generate `estilos.docx` once from Word with the brand fonts.

## docx → PDF (LibreOffice headless)

```bash
soffice --headless --convert-to pdf --outdir . propuesta.docx
```

Cross-platform and faithful. On Windows, `soffice` lives under
`C:\Program Files\LibreOffice\program\`. (`docx2pdf` works too but requires MS
Word installed — prefer LibreOffice on servers.)

## Tips

- python-docx **cannot open .doc** (legacy) — convert first:
  `soffice --headless --convert-to docx viejo.doc`.
- Spanish characters are native UTF-8 — no font juggling needed, but embed the
  brand font in the reference/template docx if the target machine may lack it.
- For repeated documents (invoices, contracts), keep a `{{placeholder}}`
  template under the project and fill it with `replace_everywhere` — do not
  rebuild the layout in code every time.
- Deliver via chat/WhatsApp: save under the exports dir so it can be downloaded.
