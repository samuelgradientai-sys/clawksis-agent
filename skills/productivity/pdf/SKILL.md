---
name: pdf
description: "Create, merge, split, fill forms, watermark, convert PDFs (pypdf, reportlab, pdfplumber, pymupdf)."
version: 1.0.0
author: Clawksis
license: MIT
platforms: [linux, macos, windows]
metadata:
  clawk:
    tags: [PDF, Documents, Forms, Reports, Conversion, Productivity]
    related_skills: [nano-pdf, ocr-and-documents, docx]
---

# PDF Toolkit

Create and manipulate PDFs end-to-end with open-source Python tooling. Use this
skill whenever a `.pdf` must be **produced or transformed**: generating reports
or invoices, merging/splitting, rotating, watermarking, stamping page numbers,
filling forms, encrypting, or converting between PDF and images.

**Routing — pick the right skill first:**

- **Extract text/tables/OCR from a PDF** → use `ocr-and-documents` (pymupdf, marker-pdf).
- **Edit existing text with natural language** ("fix this typo on page 3") → use `nano-pdf`.
- **Create a Word doc instead** → use `docx` (LibreOffice converts docx → pdf).
- **Everything else PDF** (create/merge/split/forms/watermark/encrypt/convert) → this skill.

## Prerequisites

```bash
pip install pypdf reportlab pdfplumber pymupdf
```

All four are permissively licensed (BSD/MIT/AGPL-free paths) and pure-Python or
wheel-installable on Linux/macOS/Windows. Install only what the task needs.

## Create a PDF from scratch (reportlab)

Simple text/report generation:

```python
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

doc = SimpleDocTemplate("informe.pdf", pagesize=letter)
styles = getSampleStyleSheet()
story = [
    Paragraph("Informe mensual", styles["Title"]),
    Spacer(1, 0.5 * cm),
    Paragraph("Resumen ejecutivo del período.", styles["BodyText"]),
    Spacer(1, 0.5 * cm),
    Table(
        [["Concepto", "Total"], ["Ventas", "$1.200"], ["Gastos", "$800"]],
        style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#6C4FD6")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ]),
    ),
]
doc.build(story)
```

For pixel-perfect layouts (invoices with logos), use `reportlab.pdfgen.canvas`
directly: `canvas.drawString(x, y, text)`, `canvas.drawImage(...)`, `canvas.showPage()`.

Markdown/HTML → PDF alternative: `pandoc informe.md -o informe.pdf` (needs a
LaTeX engine) or render HTML with `weasyprint` when styling matters.

## Merge / split / rotate / reorder (pypdf)

```python
from pypdf import PdfReader, PdfWriter

# Merge several PDFs
w = PdfWriter()
for path in ["a.pdf", "b.pdf", "c.pdf"]:
    w.append(path)
w.write("combinado.pdf")

# Split: one file per page
r = PdfReader("combinado.pdf")
for i, page in enumerate(r.pages):
    out = PdfWriter()
    out.add_page(page)
    out.write(f"pagina_{i + 1}.pdf")

# Extract a page range (1-based inclusive) / reorder
w = PdfWriter()
w.append("combinado.pdf", pages=(0, 3))  # pages 1-3
w.write("extracto.pdf")

# Rotate a page 90° clockwise
r = PdfReader("in.pdf")
w = PdfWriter(clone_from=r)
w.pages[0].rotate(90)
w.write("rotado.pdf")
```

## Watermark / stamp / page numbers

```python
from pypdf import PdfReader, PdfWriter

# Watermark: overlay watermark.pdf (page 1) onto every page
stamp = PdfReader("watermark.pdf").pages[0]
w = PdfWriter(clone_from="doc.pdf")
for page in w.pages:
    page.merge_page(stamp, over=False)  # under the content; over=True stamps on top
w.write("con_marca.pdf")
```

Generate the watermark/page-number overlay itself with reportlab (a canvas with
semi-transparent text via `canvas.setFillAlpha(0.3)`), then merge as above.

## Fill PDF forms (AcroForm)

```python
from pypdf import PdfReader, PdfWriter

r = PdfReader("formulario.pdf")
print(r.get_fields().keys())  # discover field names first

w = PdfWriter(clone_from=r)
w.update_page_form_field_values(
    w.pages[0],
    {"nombre": "Ada Lovelace", "fecha": "2026-07-01", "acepta": "/Yes"},
    auto_regenerate=False,
)
w.write("formulario_lleno.pdf")
```

Checkboxes use their export value (usually `/Yes`). If the PDF has no AcroForm
fields (a scanned form), stamp text at coordinates with a reportlab overlay instead.

## Encrypt / decrypt

```python
from pypdf import PdfReader, PdfWriter

w = PdfWriter(clone_from="doc.pdf")
w.encrypt(user_password="1234", algorithm="AES-256")
w.write("protegido.pdf")

r = PdfReader("protegido.pdf")
r.decrypt("1234")
```

## PDF ↔ images (pymupdf)

```python
import fitz  # pymupdf

# PDF pages → PNG (e.g. for WhatsApp previews)
doc = fitz.open("doc.pdf")
for i, page in enumerate(doc):
    page.get_pixmap(dpi=150).save(f"pagina_{i + 1}.png")

# Images → one PDF
imgdoc = fitz.open()
for img in ["foto1.jpg", "foto2.jpg"]:
    src = fitz.open(img)
    rect = src[0].rect
    pdfbytes = src.convert_to_pdf()
    imgdoc.insert_pdf(fitz.open("pdf", pdfbytes))
imgdoc.save("fotos.pdf")
```

## Quick inspection (pdfplumber)

```python
import pdfplumber

with pdfplumber.open("doc.pdf") as pdf:
    print(len(pdf.pages), "páginas")
    print(pdf.pages[0].extract_text()[:500])
    print(pdf.pages[0].extract_tables())
```

For serious extraction (scans, OCR, layout-aware markdown) switch to the
`ocr-and-documents` skill.

## Tips

- Always write to a **new output file** — never overwrite the input in place.
- Spanish/accented text: reportlab's built-in Helvetica covers Latin-1; for full
  Unicode register a TTF (`pdfmetrics.registerFont(TTFont("DejaVu", path))`).
- Large merges: `PdfWriter.append()` streams page-by-page; avoid loading
  hundreds of readers simultaneously.
- When sending the result via WhatsApp/chat, save it under the exports dir so
  the platform can serve/download it.
