"""
make_pdf.py - builds ONE PDF with every question, graph and summary paragraph.

Usage (from the project root):
    python src/make_pdf.py            # build the PDF from what the notebooks already saved
    python src/make_pdf.py --run      # first execute notebooks 01-07, then build the PDF

Needs:  pip install reportlab pillow kaleido
        (--run also needs: pip install nbformat nbclient ipykernel)
Output: reports/Climate_Emissions_Report.pdf
"""
import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph,
                                SimpleDocTemplate, Spacer)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from report import PARTS_DIR, ROOT_DIR, TOPICS  # noqa: E402

OUT_PDF = ROOT_DIR / "reports" / "Climate_Emissions_Report.pdf"
NOTEBOOK_DIR = ROOT_DIR / "notebook"
NAVY = colors.HexColor("#1f3b5c")

# Built-in PDF fonts lack many glyphs (they show as black boxes), so swap them.
SUBSCRIPTS = {"₀": "0", "₁": "1", "₂": "2", "₃": "3", "₄": "4", "₅": "5"}
REPLACE = {"−": "-", "≥": ">=", "≤": "<=", "ρ": "rho", "→": "->", "µ": "µ",
           "’": "'", "“": '"', "”": '"'}


def clean(text):
    for k, v in {**SUBSCRIPTS, **REPLACE}.items():
        text = text.replace(k, v)
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"(CO|CH|N)(\d)(?=\D|$)", r"\1<sub>\2</sub>", text)   # CO2 -> CO<sub>2</sub>
    text = re.sub(r"PM2\.5", "PM<sub>2.5</sub>", text)
    return text.encode("cp1252", "replace").decode("cp1252")


def styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=base["Title"], textColor=NAVY, fontSize=26, leading=32),
        "sub": ParagraphStyle("s", parent=base["Normal"], fontSize=12, textColor=colors.grey, alignment=1),
        "topic": ParagraphStyle("h1", parent=base["Heading1"], textColor=NAVY, fontSize=20, spaceAfter=10),
        "q": ParagraphStyle("h2", parent=base["Heading2"], textColor=NAVY, fontSize=13, leading=16,
                            spaceBefore=6, spaceAfter=6),
        "body": ParagraphStyle("b", parent=base["BodyText"], fontSize=10.5, leading=15,
                               alignment=TA_JUSTIFY, spaceAfter=6),
        "label": ParagraphStyle("l", parent=base["Normal"], fontSize=9, textColor=colors.grey, spaceAfter=2),
    }


def scaled_image(path, max_w, max_h):
    w, h = PILImage.open(path).size
    ratio = min(max_w / w, max_h / h)
    return Image(str(path), width=w * ratio, height=h * ratio)


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.grey)
    canvas.drawRightString(A4[0] - 0.75 * inch, 0.5 * inch, f"Page {doc.page}")
    canvas.drawString(0.75 * inch, 0.5 * inch, "Climate, Emissions and Air Quality Analysis")
    canvas.restoreState()


def qnum(path):
    m = re.search(r"(\d+)", path.stem)
    return int(m.group(1)) if m else 0


def build():
    if not PARTS_DIR.exists():
        raise SystemExit(f"Nothing to build: {PARTS_DIR} does not exist. Run notebooks 01-07 first.")

    st = styles()
    doc = SimpleDocTemplate(str(OUT_PDF), pagesize=A4, leftMargin=0.75 * inch, rightMargin=0.75 * inch,
                            topMargin=0.75 * inch, bottomMargin=0.8 * inch,
                            title="Climate, Emissions and Air Quality Analysis")
    max_w = A4[0] - 1.5 * inch
    story = [Spacer(1, 2.5 * inch),
             Paragraph("Climate, Emissions and Air Quality Analysis", st["title"]),
             Spacer(1, 12),
             Paragraph(f"Questions, graphs and findings from all topics<br/>Generated {date.today():%d %B %Y}",
                       st["sub"]),
             PageBreak()]

    n_questions = 0
    for topic_dir in sorted(p for p in PARTS_DIR.iterdir() if p.is_dir()):
        slug = topic_dir.name.split("_", 1)[1]
        title = TOPICS.get(slug, (0, slug.replace("_", " ").title()))[1]
        records = sorted(topic_dir.glob("q*.json"), key=qnum)
        if not records:
            continue
        story.append(Paragraph(clean(title), st["topic"]))

        for jf in records:
            rec = json.loads(jf.read_text(encoding="utf-8"))
            imgs = [topic_dir / name for name in rec["images"] if (topic_dir / name).exists()]
            head = Paragraph(f"{rec['qid'].upper()}. {clean(rec['question'])}", st["q"])
            if imgs:
                story.append(KeepTogether([head, scaled_image(imgs[0], max_w, 4.6 * inch)]))
                for extra in imgs[1:]:
                    story.append(Spacer(1, 6))
                    story.append(scaled_image(extra, max_w, 4.6 * inch))
            else:
                story.append(head)
            story.append(Spacer(1, 6))
            story.append(Paragraph("SUMMARY", st["label"]))
            for para in re.split(r"\n\s*\n", rec["summary"]):
                if para.strip():
                    story.append(Paragraph(clean(" ".join(para.split())), st["body"]))
            story.append(Spacer(1, 14))
            n_questions += 1
        story.append(PageBreak())

    if n_questions == 0:
        raise SystemExit("No saved questions found. Run notebooks 01-07 first.")
    story = story[:-1] if isinstance(story[-1], PageBreak) else story
    OUT_PDF.parent.mkdir(parents=True, exist_ok=True)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print(f"PDF created: {OUT_PDF}  ({n_questions} questions)")


def run_notebooks():
    import nbformat
    from nbclient import NotebookClient

    for nb_path in sorted(NOTEBOOK_DIR.glob("0[1-7]_*.ipynb")):
        print(f"Running {nb_path.name} ...")
        nb = nbformat.read(nb_path, as_version=4)
        NotebookClient(nb, timeout=900, kernel_name="python3",
                       resources={"metadata": {"path": str(NOTEBOOK_DIR)}}).execute()
        nbformat.write(nb, nb_path)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true", help="execute notebooks 01-07 before building")
    args = ap.parse_args()
    if args.run:
        run_notebooks()
    build()
