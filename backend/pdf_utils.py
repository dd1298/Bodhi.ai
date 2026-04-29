"""PDF utilities: text extraction, chunking, and paper rendering."""
import io
import os
import re
import tempfile
import uuid
from typing import List

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


# Cache rendered math equations across a single PDF render so repeated
# expressions don't get rasterised twice.
_MATH_CACHE: dict = {}


def _render_math_png(latex: str, fontsize: int = 11) -> str | None:
    """Render a LaTeX expression to a transparent PNG using matplotlib mathtext.
    Returns the file path, or None on failure."""
    key = (latex, fontsize)
    if key in _MATH_CACHE:
        return _MATH_CACHE[key]
    try:
        fig = plt.figure(figsize=(0.01, 0.01))
        fig.text(0, 0, f"${latex}$", fontsize=fontsize)
        out = os.path.join(
            tempfile.gettempdir(), f"qpgen_math_{uuid.uuid4().hex}.png"
        )
        fig.savefig(
            out,
            dpi=220,
            bbox_inches="tight",
            pad_inches=0.02,
            transparent=True,
        )
        plt.close(fig)
        _MATH_CACHE[key] = out
        return out
    except Exception:
        try:
            plt.close("all")
        except Exception:
            pass
        return None


def _math_to_paragraph_html(text: str) -> str:
    """Convert a string with LaTeX delimiters ($...$ and $$...$$) into a
    ReportLab Paragraph-compatible HTML string with inline math images."""
    if not text:
        return ""
    # Escape ReportLab/Paragraph special characters first, BUT preserve $ markers
    # by extracting math segments before escaping.
    segments: list = []  # list of ("text"|"math", value)
    i = 0
    while i < len(text):
        if text.startswith("$$", i):
            end = text.find("$$", i + 2)
            if end == -1:
                segments.append(("text", text[i:]))
                break
            segments.append(("math", text[i + 2 : end]))
            i = end + 2
        elif text[i] == "$":
            end = text.find("$", i + 1)
            if end == -1:
                segments.append(("text", text[i:]))
                break
            segments.append(("math", text[i + 1 : end]))
            i = end + 1
        else:
            # accumulate plain text until next $
            nxt = text.find("$", i)
            if nxt == -1:
                segments.append(("text", text[i:]))
                break
            segments.append(("text", text[i:nxt]))
            i = nxt

    out_parts: list = []
    for kind, val in segments:
        if kind == "text":
            esc = (
                val.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\n", "<br/>")
            )
            out_parts.append(esc)
        else:
            png = _render_math_png(val.strip())
            if png:
                out_parts.append(
                    f'<img src="{png}" valign="middle" height="14"/>'
                )
            else:
                # fallback: keep the raw expression
                out_parts.append(
                    val.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                )
    return "".join(out_parts)


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


def render_paper_pdf(paper: dict, diagram_loader=None) -> bytes:
    """Render the structured paper dict into a printable PDF.

    diagram_loader: optional callable(question_id, diagram_path) -> bytes|None,
    used to embed diagram images next to questions.
    """
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
            q_html = _math_to_paragraph_html(q.get("question", ""))
            story.append(
                Paragraph(
                    f"<b>Q{q_counter}.</b> {important}{q_html} "
                    f"<font color='#525252'>[{marks_q} marks]</font>",
                    q_style,
                )
            )
            tags = [t for t in [qtype, difficulty] if t]
            if tags:
                story.append(Paragraph(" · ".join(tags), tag_style))

            # Embed diagram if present
            if q.get("diagram_path") and diagram_loader:
                try:
                    img_bytes = diagram_loader(q.get("id"), q["diagram_path"])
                    if img_bytes:
                        img = Image(io.BytesIO(img_bytes), width=80 * mm, height=80 * mm)
                        img.hAlign = "LEFT"
                        story.append(Spacer(1, 2 * mm))
                        story.append(img)
                except Exception:
                    pass

            story.append(Spacer(1, 2 * mm))
            q_counter += 1

    doc.build(story)
    out = buf.getvalue()
    # Clean up temp math PNGs
    for path in list(_MATH_CACHE.values()):
        try:
            os.remove(path)
        except Exception:
            pass
    _MATH_CACHE.clear()
    return out


def render_solution_pdf(paper: dict, diagram_loader=None) -> bytes:
    """Render the answer-key PDF for a paper. Mirrors the paper structure but
    places each question's answer below it."""
    sol = paper.get("solution") or {}
    answers_by_qid = {}
    for sec in sol.get("sections") or []:
        for a in sec.get("answers") or []:
            answers_by_qid[a.get("question_id")] = a.get("answer", "")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"{paper.get('title', 'Question Paper')} — Answer Key",
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
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=15,
        spaceAfter=3,
    )
    a_style = ParagraphStyle(
        "a",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=11,
        leading=15,
        spaceAfter=8,
        leftIndent=12,
        textColor=colors.HexColor("#0A0A0A"),
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
    story.append(Paragraph("— ANSWER KEY —", meta))
    story.append(
        Paragraph(
            f"Class: <b>{paper.get('class_name','')}</b> &nbsp;&nbsp; "
            f"Subject: <b>{paper.get('subject','')}</b> &nbsp;&nbsp; "
            f"Total Marks: <b>{paper.get('total_marks','')}</b>",
            meta,
        )
    )
    story.append(Spacer(1, 6 * mm))

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

    if sol.get("is_stale"):
        story.append(
            Paragraph(
                "<i>Note: The question paper has been edited after this solution "
                "was generated. Some answers may be out of date.</i>",
                tag_style,
            )
        )
        story.append(Spacer(1, 3 * mm))

    sections = paper.get("sections") or []
    q_counter = 1
    for section in sections:
        story.append(Paragraph(section.get("title", "Section"), section_h))
        for q in section.get("questions", []):
            qtext_html = _math_to_paragraph_html(q.get("question", ""))
            marks_q = q.get("marks", 0)
            story.append(
                Paragraph(
                    f"Q{q_counter}. {qtext_html} "
                    f"<font color='#525252'>[{marks_q} marks]</font>",
                    q_style,
                )
            )

            # Diagram (if present) so a teacher can see the reference figure
            if q.get("diagram_path") and diagram_loader:
                try:
                    img_bytes = diagram_loader(q.get("id"), q["diagram_path"])
                    if img_bytes:
                        img = Image(
                            io.BytesIO(img_bytes), width=70 * mm, height=70 * mm
                        )
                        img.hAlign = "LEFT"
                        story.append(img)
                        story.append(Spacer(1, 2 * mm))
                except Exception:
                    pass

            answer = answers_by_qid.get(q.get("id")) or "(No answer written yet.)"
            ans_html = _math_to_paragraph_html(answer)
            story.append(Paragraph(f"<b>Ans:</b> {ans_html}", a_style))
            q_counter += 1

    doc.build(story)
    out = buf.getvalue()
    for path in list(_MATH_CACHE.values()):
        try:
            os.remove(path)
        except Exception:
            pass
    _MATH_CACHE.clear()
    return out
