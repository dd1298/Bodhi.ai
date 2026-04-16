"""PDF utilities: text extraction, chunking, and paper rendering."""
import io
from typing import List

from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def extract_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    pieces: List[str] = []
    for page in reader.pages:
        try:
            t = page.extract_text() or ""
        except Exception:
            t = ""
        if t.strip():
            pieces.append(t)
    return "\n\n".join(pieces)


def chunk_text(text: str, chunk_size: int = 2500, overlap: int = 200) -> List[str]:
    text = text.strip()
    if not text:
        return []
    chunks: List[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + chunk_size, n)
        # try to break on a paragraph / sentence
        if end < n:
            br = text.rfind("\n\n", start, end)
            if br > start + chunk_size // 2:
                end = br
        chunks.append(text[start:end].strip())
        if end == n:
            break
        start = max(end - overlap, start + 1)
    return [c for c in chunks if c]


def render_paper_pdf(paper: dict) -> bytes:
    """Render the structured paper dict into a printable PDF."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=paper.get("title", "Question Paper"),
    )
    styles = getSampleStyleSheet()

    h1 = ParagraphStyle(
        "H1",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        alignment=1,
        spaceAfter=4,
    )
    meta = ParagraphStyle(
        "meta",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        alignment=1,
        textColor=colors.HexColor("#525252"),
    )
    section_h = ParagraphStyle(
        "section",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        spaceBefore=10,
        spaceAfter=6,
        textColor=colors.HexColor("#002FA7"),
    )
    q_style = ParagraphStyle(
        "q",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=11,
        leading=15,
        spaceAfter=6,
    )
    tag_style = ParagraphStyle(
        "tag",
        parent=styles["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#525252"),
    )

    story = []
    story.append(Paragraph(paper.get("title", "Question Paper"), h1))

    subject = paper.get("subject", "")
    klass = paper.get("class_name", "")
    marks = paper.get("total_marks", "")
    duration = paper.get("duration_minutes", "")
    story.append(
        Paragraph(
            f"Class: <b>{klass}</b> &nbsp;&nbsp; Subject: <b>{subject}</b> &nbsp;&nbsp; "
            f"Total Marks: <b>{marks}</b> &nbsp;&nbsp; Duration: <b>{duration} min</b>",
            meta,
        )
    )
    story.append(Spacer(1, 6 * mm))

    # Separator line
    sep = Table(
        [[""]],
        colWidths=[doc.width],
        rowHeights=[0.6 * mm],
        style=TableStyle(
            [("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0A0A0A"))]
        ),
    )
    story.append(sep)
    story.append(Spacer(1, 4 * mm))

    instructions = paper.get("instructions")
    if instructions:
        story.append(
            Paragraph(
                f"<b>Instructions:</b> {instructions}", q_style
            )
        )
        story.append(Spacer(1, 4 * mm))

    # Group questions by section (type)
    sections = paper.get("sections") or []
    if not sections:
        # fallback: flat list in paper['questions']
        sections = [{"title": "Questions", "questions": paper.get("questions", [])}]

    q_counter = 1
    for section in sections:
        story.append(Paragraph(section.get("title", "Section"), section_h))
        for q in section.get("questions", []):
            marks_q = q.get("marks", 0)
            difficulty = q.get("difficulty", "")
            qtype = q.get("type", "")
            important = "★ " if q.get("important") else ""
            story.append(
                Paragraph(
                    f"<b>Q{q_counter}.</b> {important}{q.get('question','')} "
                    f"<font color='#525252'>[{marks_q} marks]</font>",
                    q_style,
                )
            )
            tags = [t for t in [qtype, difficulty] if t]
            if tags:
                story.append(Paragraph(" · ".join(tags), tag_style))
            story.append(Spacer(1, 2 * mm))
            q_counter += 1

    doc.build(story)
    return buf.getvalue()
