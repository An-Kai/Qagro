---
name: pdf
description: Create and manipulate PDFs with Python (ReportLab Platypus/Canvas, pypdf merge/split, pdfplumber tables). Use when building Qagro PDF reports, fixing Cyrillic fonts, or processing PDF documents programmatically.
compatibility: opencode
---

# PDF Processing Guide

Core patterns adapted from `agent-skills-hub/agent-skills-hub`
(`document-skills/pdf`) for Qagro's ReportLab-based reporting.

## Quick Start

```python
from pypdf import PdfReader, PdfWriter

reader = PdfReader("document.pdf")
print(f"Pages: {len(reader.pages)}")
text = "".join(page.extract_text() or "" for page in reader.pages)
```

## pypdf - merge / split / metadata / rotate

```python
from pypdf import PdfReader, PdfWriter

# Merge
writer = PdfWriter()
for pdf_file in ["doc1.pdf", "doc3.pdf"]:
    for page in PdfReader(pdf_file).pages:
        writer.add_page(page)
with open("merged.pdf", "wb") as f:
    writer.write(f)

# Split
reader = PdfReader("input.pdf")
for i, page in enumerate(reader.pages):
    w = PdfWriter()
    w.add_page(page)
    with open(f"page_{i+1}.pdf", "wb") as f:
        w.write(f)
```

## pdfplumber - text and table extraction

```python
import pdfplumber

with pdfplumber.open("document.pdf") as pdf:
    for page in pdf.pages:
        print(page.extract_text())
        for table in page.extract_tables():
            print(table)
```

## reportlab - Create PDFs

```python
from reportlab.lib.pagesizes import letter
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
from reportlab.lib.styles import getSampleStyleSheet

doc = SimpleDocTemplate("report.pdf", pagesize=letter)
styles = getSampleStyleSheet()
doc.build([
    Paragraph("Report Title", styles["Title"]),
    Spacer(1, 12),
    Paragraph("Body text.", styles["Normal"]),
])
```

## Command-Line Tools

```bash
pdftotext -layout input.pdf output.txt   # poppler-utils, keep layout
qpdf --empty --pages file1.pdf file2.pdf -- merged.pdf
qpdf input.pdf --pages . 1-5 -- pages1-5.pdf
```

## Quick Reference

| Task | Best Tool |
|---|---|
| Merge/split PDFs | pypdf (`PdfWriter.add_page`) |
| Extract text/tables | pdfplumber |
| Create PDFs | reportlab (Canvas or Platypus) |
| CLI merge/split | qpdf |
| Scanned PDFs (OCR) | pytesseract + pdf2image |

---

## Qagro appendix (project-specific, takes precedence in this repo)

Reports: `src/report_pdf.py` (`build_report_pdf(...)`), served by
`POST /report` (`src/api.py`) and the bot/Streamlit PDF buttons.

Hard rules (Cyrillic correctness depends on them):

- Pins: `reportlab==4.2.5` (`requirements.txt`). Fonts: **DejaVu**
  (`fonts-dejavu` installed in `Dockerfile` via apt) — the ONLY fonts that
  render RU/KZ Cyrillic in PDFs. Register DejaVu Sans / Sans-Bold explicitly
  with `pdfmetrics.registerFont(TTFont(...))`; never use Helvetica for
  user-visible text (it has no Cyrillic glyphs → tofu boxes).
- Content: forecast table (y_pred/lo/hi) + insurance + decade risk + sowing
  recommendation + C8 blocks (calendar/elevator/alerts best-effort). All strings
  in request `lang` (ru/kz/en parity); missing online data → honest
  "unavailable" line, never blank/mocked.
- Keep the builder signature stable (`district_en, crop, lang, pred, ins, risk,
  rec, district_ru, calendar, alerts, alerts_error, elevator`) — three callers
  depend on it (API, bot, Streamlit). Test locally:
  `python -c "from src.report_pdf import build_report_pdf; ..."` and open the
  bytes; verify Cyrillic renders before committing.
