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
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


# Register a Unicode-capable font once so characters like °, ·, ⁻¹, ², ∞, ×
# render correctly in the PDF. ReportLab's built-in Helvetica is Latin-1 only
# and silently drops many Unicode glyphs we actually use in physics/math.
_MPL_FONTS = os.path.join(
    os.path.dirname(matplotlib.__file__), "mpl-data", "fonts", "ttf"
)
BODY_FONT = "Helvetica"
BODY_FONT_BOLD = "Helvetica-Bold"
BODY_FONT_ITALIC = "Helvetica-Oblique"
try:
    pdfmetrics.registerFont(TTFont("DejaVuSans", os.path.join(_MPL_FONTS, "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", os.path.join(_MPL_FONTS, "DejaVuSans-Bold.ttf")))
    pdfmetrics.registerFont(TTFont("DejaVuSans-Oblique", os.path.join(_MPL_FONTS, "DejaVuSans-Oblique.ttf")))
    from reportlab.pdfbase.pdfmetrics import registerFontFamily
    registerFontFamily(
        "DejaVuSans",
        normal="DejaVuSans",
        bold="DejaVuSans-Bold",
        italic="DejaVuSans-Oblique",
        boldItalic="DejaVuSans-Bold",
    )
    BODY_FONT = "DejaVuSans"
    BODY_FONT_BOLD = "DejaVuSans-Bold"
    BODY_FONT_ITALIC = "DejaVuSans-Oblique"
except Exception:
    # Fall back silently to Helvetica if the DejaVu files aren't available.
    pass


# Cache rendered math equations across a single PDF render so repeated
# expressions don't get rasterised twice.
_MATH_CACHE: dict = {}


def _normalise_latex(latex: str) -> str:
    """Normalise a LaTeX snippet so matplotlib's mathtext can render it.
    Matplotlib mathtext accepts `\\text{...}` in recent versions but we
    replace it with `\\mathrm{...}` for maximum compatibility, and drop
    a few commands that mathtext does not support at all."""
    if not latex:
        return latex
    s = latex
    # Replace \text{...} and \textrm{...} with \mathrm{...}
    s = re.sub(r"\\text(?:rm|bf|it|sf|tt)?\{([^{}]*)\}", r"\\mathrm{\1}", s)
    # \operatorname{...} -> \mathrm{...}
    s = re.sub(r"\\operatorname\*?\{([^{}]*)\}", r"\\mathrm{\1}", s)
    # Unsupported commands -> drop them (keep the argument if braced)
    s = re.sub(r"\\boxed\{([^{}]*)\}", r"\1", s)
    # Normalise \degree to ^\circ
    s = s.replace(r"\degree", r"^\circ")
    return s


def _strip_latex_for_fallback(latex: str) -> str:
    """Last-resort textual fallback when mathtext rendering fails. Produce a
    readable plain-text version of the LaTeX snippet rather than leaking raw
    backslash commands into the PDF."""
    if not latex:
        return ""
    s = latex
    # keep contents of common wrappers
    for cmd in ("mathrm", "text", "textrm", "textbf", "textit", "mathbf", "mathit", "boxed", "vec"):
        s = re.sub(r"\\" + cmd + r"\{([^{}]*)\}", r"\1", s)
    # Frac
    s = re.sub(r"\\d?frac\{([^{}]*)\}\{([^{}]*)\}", r"(\1)/(\2)", s)
    # Sqrt
    s = re.sub(r"\\sqrt\{([^{}]*)\}", r"√(\1)", s)
    # Degree
    s = re.sub(r"\^\\?circ", "°", s)
    # Common symbols
    replacements = {
        r"\cdot": "·",
        r"\times": "×",
        r"\pm": "±",
        r"\approx": "≈",
        r"\neq": "≠",
        r"\leq": "≤",
        r"\geq": "≥",
        r"\to": "→",
        r"\infty": "∞",
        r"\pi": "π",
        r"\theta": "θ",
        r"\alpha": "α",
        r"\beta": "β",
        r"\gamma": "γ",
        r"\mu": "μ",
        r"\omega": "ω",
        r"\,": " ",
        r"\;": " ",
        r"\:": " ",
        r"\!": "",
        r"\ ": " ",
    }
    for k, v in replacements.items():
        s = s.replace(k, v)
    # strip remaining backslashes from any simple commands
    s = re.sub(r"\\([a-zA-Z]+)", r"\1", s)
    # strip braces
    s = s.replace("{", "").replace("}", "")
    return s


def _render_math_png(latex: str, fontsize: int = 11) -> str | None:
    """Render a LaTeX expression to a high-DPI transparent PNG using
    matplotlib mathtext. We render at 600 dpi (up from 220) so the image
    stays razor-sharp when zoomed or printed — at the cost of a slightly
    larger PDF. ReportLab compresses PNG streams inside the PDF anyway."""
    latex = _normalise_latex(latex)
    key = (latex, fontsize)
    if key in _MATH_CACHE:
        return _MATH_CACHE[key]
    try:
        fig = plt.figure(figsize=(0.01, 0.01))
        # Render slightly smaller than the body font so inline math doesn't
        # tower over surrounding text. fontsize=10 pairs well with 11pt body.
        fig.text(0, 0, f"${latex}$", fontsize=10)
        out = os.path.join(
            tempfile.gettempdir(), f"qpgen_math_{uuid.uuid4().hex}.png"
        )
        fig.savefig(
            out,
            dpi=600,
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


def _render_math_svg(latex: str) -> str | None:
    """Render a LaTeX expression to a vector SVG. Available for future use
    when a block-math flowable wants true-vector rendering (the inline
    `<img>` tags inside ReportLab Paragraphs only accept raster images, so
    inline math still uses `_render_math_png`)."""
    latex = _normalise_latex(latex)
    try:
        fig = plt.figure(figsize=(0.01, 0.01))
        fig.text(0, 0, f"${latex}$", fontsize=11)
        out = os.path.join(
            tempfile.gettempdir(), f"qpgen_math_{uuid.uuid4().hex}.svg"
        )
        fig.savefig(out, bbox_inches="tight", pad_inches=0.02, transparent=True)
        plt.close(fig)
        return out
    except Exception:
        try:
            plt.close("all")
        except Exception:
            pass
        return None


def _math_img_tag(png_path: str) -> str:
    """Build an `<img>` tag for a ReportLab Paragraph that displays the math
    PNG at a sensible inline size — matching the body text height when the
    expression is single-line, and slightly taller for stacked expressions
    (fractions, sums). Aspect ratio is preserved.
    """
    try:
        from PIL import Image as PILImage  # noqa: PLC0415
        with PILImage.open(png_path) as pim:
            pw, ph = pim.size
        # PNG is at 600 dpi from matplotlib (1 pt = 600/72 px).
        natural_h_pt = (ph / 600.0) * 72.0
        natural_w_pt = (pw / 600.0) * 72.0
        # Cap height at 18pt so giant fractions don't blow up the line spacing.
        max_h = 18.0
        if natural_h_pt > max_h:
            scale = max_h / natural_h_pt
            natural_h_pt = max_h
            natural_w_pt *= scale
        return (
            f'<img src="{png_path}" valign="-1" '
            f'width="{natural_w_pt:.2f}" height="{natural_h_pt:.2f}"/>'
        )
    except Exception:
        # Fallback: previous fixed-height behaviour
        return f'<img src="{png_path}" valign="middle" height="11"/>'


def _make_diagram_image(img_bytes: bytes, max_width_mm: float = 100, max_height_mm: float = 90):
    """Build a ReportLab Image that fits within max_width_mm × max_height_mm
    while preserving the source image's aspect ratio."""
    try:
        from PIL import Image as PILImage
        bio = io.BytesIO(img_bytes)
        with PILImage.open(bio) as pim:
            iw, ih = pim.size
        if iw <= 0 or ih <= 0:
            return None
        max_w_pt = max_width_mm * mm
        max_h_pt = max_height_mm * mm
        scale = min(max_w_pt / iw, max_h_pt / ih)
        w = iw * scale
        h = ih * scale
        return Image(io.BytesIO(img_bytes), width=w, height=h)
    except Exception:
        # Fallback: honour max width, keep a 4:3-ish ratio
        return Image(io.BytesIO(img_bytes), width=max_width_mm * mm, height=max_height_mm * mm * 0.75)


def _markdown_to_reportlab(text: str) -> str:
    """Strip / convert common markdown formatting that LLMs sometimes emit
    so it doesn't leak into the rendered PDF as raw asterisks/backticks.

    Runs BEFORE math segmentation so the math segments themselves are not
    affected (they're between $...$ delimiters anyway).
    """
    if not text:
        return text
    # Strip a leading "Q1." / "Q1)" / "**Q1.**" / "1." / "1)" from the LLM
    # output FIRST (before sentinelizing) — the renderer always adds its
    # own "Qx." prefix so this would otherwise double up.
    text = re.sub(
        r"^\s*\*{0,2}\s*Q\s*\d+\s*[.)]\s*\*{0,2}\s*",
        "",
        text,
        count=1,
        flags=re.IGNORECASE,
    )
    # **bold**  -> sentinels (placeholder strings to survive escaping)
    # We can't insert ReportLab <b>...</b> tags directly here because the
    # downstream code escapes "<" / ">". Instead, we use a unique sentinel
    # that the post-escape stage swaps in for real tags.
    text = re.sub(r"\*\*(.+?)\*\*", "\x01B_OPEN\x01\\1\x01B_CLOSE\x01", text, flags=re.DOTALL)
    # *italic* -> <i>italic</i>  (must NOT eat the leading * of a bullet line)
    text = re.sub(
        r"(?<![*\w])\*(?!\s)([^\*\n]+?)(?<!\s)\*(?![*\w])",
        "\x01I_OPEN\x01\\1\x01I_CLOSE\x01",
        text,
    )
    # `inline code` -> drop backticks (we'd render in mono but ReportLab Paragraph
    # doesn't have a mono tag by default; just strip the markers).
    text = re.sub(r"`([^`\n]+)`", r"\1", text)
    # Stray heading markers at line starts (#, ##, ###) -> drop the marker
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s+", "", text)
    return text


def _apply_format_sentinels(escaped_html: str) -> str:
    """Swap markdown sentinels for real ReportLab tags AFTER escape pass."""
    return (
        escaped_html.replace("\x01B_OPEN\x01", "<b>")
        .replace("\x01B_CLOSE\x01", "</b>")
        .replace("\x01I_OPEN\x01", "<i>")
        .replace("\x01I_CLOSE\x01", "</i>")
    )


def _math_to_paragraph_html(text: str) -> str:
    """Convert a string with LaTeX delimiters ($...$ and $$...$$) into a
    ReportLab Paragraph-compatible HTML string with inline math images."""
    if not text:
        return ""
    # Convert markdown emphasis to sentinels BEFORE math segmentation, so
    # the math content itself (which is rendered as PNG and never goes
    # through escape) is not affected.
    text = _markdown_to_reportlab(text)
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
            inner = text[i + 1 : end]
            # If content is trivially plain (numbers, units, ASCII words), skip
            # the matplotlib PNG round-trip and just emit the inner text — this
            # keeps `$4$` from rendering as literal `$4$` when mathtext bounces,
            # and speeds up rendering for the very common "number in a sentence"
            # case (e.g. `$1.0$ M`, `$300$ K`, `$25$ ml`). Anything with LaTeX
            # markers (\, ^, _, {, }, /) still goes down the math path.
            if inner and not re.search(r"[\\\^_{}/]", inner) and re.fullmatch(
                r"[A-Za-z0-9,\.\-+×·%°'\" ]+", inner
            ):
                segments.append(("text", inner))
                i = end + 1
                continue
            segments.append(("math", inner))
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
                out_parts.append(_math_img_tag(png))
            else:
                # Friendly textual fallback — no raw backslash commands.
                friendly = _strip_latex_for_fallback(val)
                out_parts.append(
                    friendly.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                )
    return _apply_format_sentinels("".join(out_parts))


def _strip_boilerplate(text: str) -> str:
    """Remove common PDF watermark / header noise without touching real content.
    Specifically targets:
      - 'Downloaded from …' watermarks
      - Standalone URL-only lines
      - Bare page numbers on their own line
      - 3+ consecutive blank lines
    We intentionally do NOT do generic repetition-based stripping because
    legitimate textbook phrases (chapter titles, section headers, common
    question stems like 'Give the name of …') repeat often enough to trigger
    false positives."""
    if not text:
        return text

    import re as _re

    url_re = _re.compile(
        r"^(https?://|www\.)\S+$|^\S+\.(com|in|org|net|edu|co\.[a-z]+)(/\S*)?$",
        _re.IGNORECASE,
    )
    lines = text.split("\n")
    cleaned: list[str] = []
    for ln in lines:
        s = ln.strip()
        if not s:
            cleaned.append("")
            continue
        low = s.lower()
        # Watermark patterns — expanded to catch common scanner-app stamps
        # that would otherwise inflate the char count and mask an empty
        # text layer (i.e. a scanned PDF that needs OCR).
        if "downloaded from" in low:
            continue
        if "scanned by camscanner" in low or low == "camscanner":
            continue
        if "scanned with camscanner" in low:
            continue
        if "tap here to remove ads" in low or "cam scanner" in low:
            continue
        if url_re.match(s):
            continue
        # Bare page numbers
        if s.isdigit() and len(s) <= 4:
            continue
        cleaned.append(ln)

    # Collapse 3+ consecutive blank lines to at most 2
    out: list[str] = []
    blank = 0
    for ln in cleaned:
        if ln.strip():
            out.append(ln)
            blank = 0
        else:
            blank += 1
            if blank <= 2:
                out.append(ln)
    return "\n".join(out)


def _ocr_pdf(pdf_bytes: bytes, max_pages: int = 40, dpi: int = 150) -> str:
    """Run Tesseract OCR on a scanned / image-based PDF.

    Strategy: when the PDF is short, OCR every page up to `max_pages`. For
    longer books (> max_pages), sample evenly across the whole document so
    we capture the ToC at the front, chapter intros in the middle and the
    glossary/summary at the end — critical for topic extraction.
    """
    try:
        from pdf2image import convert_from_bytes
        from pdf2image.exceptions import PDFPageCountError
        import pytesseract
        import pypdf as _pypdf
        import io as _io
    except ImportError:
        return ""

    try:
        total_pages = len(_pypdf.PdfReader(_io.BytesIO(pdf_bytes)).pages)
    except Exception:
        total_pages = max_pages

    if total_pages <= max_pages:
        page_numbers = list(range(1, total_pages + 1))
    else:
        # Always OCR the first 4 pages (ToC) + the last 2 (glossary/answers)
        # and sample the rest evenly.
        head = list(range(1, min(5, total_pages + 1)))
        tail = list(range(max(total_pages - 1, 1), total_pages + 1))
        remaining = max_pages - len(head) - len(tail)
        if remaining > 0:
            # Pick `remaining` pages spaced evenly in [head_end+1 .. tail_start-1]
            start = head[-1] + 1
            end = tail[0] - 1
            if end > start and remaining > 0:
                step = max(1, (end - start) // remaining)
                middle = list(range(start, end + 1, step))[:remaining]
            else:
                middle = []
        else:
            middle = []
        page_numbers = sorted(set(head + middle + tail))

    pieces: list = []
    for pn in page_numbers:
        try:
            imgs = convert_from_bytes(
                pdf_bytes, dpi=dpi, first_page=pn, last_page=pn
            )
        except (PDFPageCountError, Exception):
            continue
        for img in imgs:
            try:
                pieces.append(pytesseract.image_to_string(img) or "")
            except Exception:
                continue
    return "\n\n".join(p for p in pieces if p.strip())


def _looks_like_metadata_only(text: str) -> bool:
    """Detect NTA-style PDFs where pypdf only pulls metadata (Question Number,
    Question Id, Question Type, Options: labels) while the actual question
    stems and option choices are rendered as page images. Heuristic: many
    'Question Number' markers but after stripping known NTA metadata fields
    the gap between consecutive question markers averages <80 chars (no real
    question prose between them)."""
    import re as _re
    matches = list(_re.finditer(r"Question Number\s*:\s*\d+", text))
    if len(matches) < 5:
        return False
    # Patterns we strip before measuring real-prose density. Each represents
    # one NTA "header" line that wraps the actual (image-only) question body.
    metadata_re = _re.compile(
        r"Question (?:Id|Type|Number) :\s*\S+|"
        r"Option (?:Shuffling|Orientation) :\s*\S+|"
        r"Display Question Number :\s*\S+|"
        r"IsQuestion Mandatory :\s*\S+|"
        r"Single Line Question Option :\s*\S+|"
        r"Options? :|"
        r"^\s*\d{4,}\.\s*$|"  # option numeric IDs on their own line
        r"Correct Answer.*?$|"
        r"Selected Option :.*?$|"
        r"Time Taken.*?$|"
        r"Status :.*?$",
        _re.MULTILINE,
    )
    leftover_total = 0
    for i in range(len(matches) - 1):
        gap = text[matches[i].end() : matches[i + 1].start()]
        stripped = metadata_re.sub("", gap).strip()
        # Collapse whitespace so blank-line spam doesn't inflate the count.
        leftover_total += len(_re.sub(r"\s+", " ", stripped))
    avg_leftover = leftover_total / max(1, len(matches) - 1)
    return avg_leftover < 80


def extract_text(pdf_bytes: bytes, allow_ocr: bool = True) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    pieces: List[str] = []
    for page in reader.pages:
        try:
            t = page.extract_text() or ""
        except Exception:
            t = ""
        if t.strip():
            pieces.append(t)
    raw = "\n\n".join(pieces)
    cleaned = _strip_boilerplate(raw)

    # OCR fallback in two cases:
    #   1. Almost nothing was extracted (truly scanned/image PDF).
    #   2. Text contains lots of "Question Number :" markers but no real prose
    #      between them — i.e. an NTA PDF where questions are page images.
    needs_ocr = (
        allow_ocr
        and (len(cleaned.strip()) < 500 or _looks_like_metadata_only(cleaned))
    )
    if needs_ocr:
        ocr_text = _ocr_pdf(pdf_bytes, max_pages=40)
        if ocr_text.strip():
            return _strip_boilerplate(ocr_text)
    return cleaned


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
        fontName=BODY_FONT_BOLD,
        fontSize=20,
        leading=24,
        alignment=1,
        spaceAfter=4,
    )
    meta = ParagraphStyle(
        "meta",
        parent=styles["Normal"],
        fontName=BODY_FONT,
        fontSize=10,
        leading=14,
        alignment=1,
        textColor=colors.HexColor("#525252"),
    )
    section_h = ParagraphStyle(
        "section",
        parent=styles["Heading2"],
        fontName=BODY_FONT_BOLD,
        fontSize=12,
        leading=16,
        spaceBefore=10,
        spaceAfter=6,
        textColor=colors.HexColor("#002FA7"),
    )
    q_style = ParagraphStyle(
        "q",
        parent=styles["Normal"],
        fontName=BODY_FONT,
        fontSize=11,
        leading=15,
        spaceAfter=6,
    )
    tag_style = ParagraphStyle(
        "tag",
        parent=styles["Normal"],
        fontName=BODY_FONT_ITALIC,
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
                f"<b>Instructions:</b> {_math_to_paragraph_html(instructions)}",
                q_style,
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
            # MCQ options — render as (a)/(b)/(c)/(d) on indented lines so the
            # paper looks like a real MCQ paper instead of having options
            # squashed inline with the stem.
            if (q.get("format") or "").lower() == "mcq" and q.get("options"):
                labels = ["(a)", "(b)", "(c)", "(d)"]
                for idx, opt in enumerate(q["options"][:4]):
                    label = labels[idx] if idx < len(labels) else f"({idx + 1})"
                    opt_html = _math_to_paragraph_html(str(opt))
                    story.append(
                        Paragraph(
                            f"&nbsp;&nbsp;&nbsp;&nbsp;<b>{label}</b> {opt_html}",
                            q_style,
                        )
                    )
            tags = [t for t in [qtype, q.get("format", ""), difficulty] if t]
            if tags:
                # Make format display human-friendly (snake_case -> spaces)
                tags = [str(t).replace("_", " ") for t in tags]
                story.append(Paragraph(" · ".join(tags), tag_style))

            # Embed diagram if present
            if q.get("diagram_path") and diagram_loader:
                try:
                    img_bytes = diagram_loader(q.get("id"), q["diagram_path"])
                    if img_bytes:
                        img = _make_diagram_image(img_bytes, max_width_mm=100, max_height_mm=90)
                        if img is not None:
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
        fontName=BODY_FONT_BOLD,
        fontSize=20,
        leading=24,
        alignment=1,
        spaceAfter=4,
    )
    meta = ParagraphStyle(
        "meta",
        parent=styles["Normal"],
        fontName=BODY_FONT,
        fontSize=10,
        leading=14,
        alignment=1,
        textColor=colors.HexColor("#525252"),
    )
    section_h = ParagraphStyle(
        "section",
        parent=styles["Heading2"],
        fontName=BODY_FONT_BOLD,
        fontSize=12,
        leading=16,
        spaceBefore=10,
        spaceAfter=6,
        textColor=colors.HexColor("#002FA7"),
    )
    q_style = ParagraphStyle(
        "q",
        parent=styles["Normal"],
        fontName=BODY_FONT_BOLD,
        fontSize=11,
        leading=15,
        spaceAfter=3,
    )
    a_style = ParagraphStyle(
        "a",
        parent=styles["Normal"],
        fontName=BODY_FONT,
        fontSize=11,
        leading=15,
        spaceAfter=8,
        leftIndent=12,
        textColor=colors.HexColor("#0A0A0A"),
    )
    tag_style = ParagraphStyle(
        "tag",
        parent=styles["Normal"],
        fontName=BODY_FONT_ITALIC,
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
                        img = _make_diagram_image(img_bytes, max_width_mm=90, max_height_mm=80)
                        if img is not None:
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
