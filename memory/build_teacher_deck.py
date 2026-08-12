"""Bodhi.ai — Teacher-facing product walkthrough deck.

Runs a Swiss/brutalist light theme matching the web app:
  Off-white bg  •  Klein Blue #002FA7 primary  •  Yellow #FFC300 accent
  Black hard borders, mono captions, generous whitespace.

Output: /app/memory/Bodhi_Teacher_Walkthrough.pptx
"""
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

# ---------- Theme ----------
INK        = RGBColor(0x0A, 0x0A, 0x0A)
INK_SOFT   = RGBColor(0x52, 0x52, 0x52)
INK_MUTED  = RGBColor(0x8A, 0x8A, 0x8A)
BG         = RGBColor(0xFA, 0xFA, 0xF7)
SURFACE    = RGBColor(0xFF, 0xFF, 0xFF)
BLUE       = RGBColor(0x00, 0x2F, 0xA7)   # Klein blue
YELLOW     = RGBColor(0xFF, 0xC3, 0x00)
GREEN      = RGBColor(0x10, 0xB9, 0x81)
RED        = RGBColor(0xE6, 0x39, 0x46)
GREY_LINE  = RGBColor(0xE0, 0xE0, 0xE0)

FONT_H = "Calibri"
FONT_B = "Calibri"
FONT_M = "Consolas"

SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)


# ---------- Helpers ----------
def add_bg(slide, color=BG):
    r = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, SLIDE_W, SLIDE_H)
    r.fill.solid(); r.fill.fore_color.rgb = color
    r.line.fill.background()
    r.shadow.inherit = False
    return r


def add_text(slide, x, y, w, h, text, *, size=18, bold=False, color=INK,
             font=FONT_B, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, italic=False):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = 0
    tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    lines = text.split("\n") if isinstance(text, str) else text
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        run = p.add_run()
        run.text = line
        run.font.name = font
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.italic = italic
        run.font.color.rgb = color
    return tb


def add_rect(slide, x, y, w, h, fill=SURFACE, line=INK, line_w=1.25):
    r = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, w, h)
    r.fill.solid(); r.fill.fore_color.rgb = fill
    if line is None:
        r.line.fill.background()
    else:
        r.line.color.rgb = line
        r.line.width = Pt(line_w)
    r.shadow.inherit = False
    return r


def add_line(slide, x1, y1, x2, y2, color=INK, width=1.25):
    ln = slide.shapes.add_connector(1, x1, y1, x2, y2)
    ln.line.color.rgb = color
    ln.line.width = Pt(width)
    return ln


def add_pill(slide, x, y, text, *, fill=YELLOW, color=INK, w=Inches(2.2), h=Inches(0.36)):
    r = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, w, h)
    r.fill.solid(); r.fill.fore_color.rgb = fill
    r.line.fill.background()
    r.shadow.inherit = False
    tf = r.text_frame
    tf.margin_left = tf.margin_right = Inches(0.12)
    tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]; p.alignment = PP_ALIGN.LEFT
    run = p.add_run(); run.text = text
    run.font.name = FONT_M; run.font.size = Pt(10); run.font.bold = True
    run.font.color.rgb = color
    return r


def header(slide, chapter, kicker, title):
    """Consistent top-of-slide header: kicker line + chapter number + title."""
    add_text(slide, Inches(0.6), Inches(0.35), Inches(6), Inches(0.3),
             kicker, size=10, bold=True, color=BLUE, font=FONT_M)
    add_text(slide, Inches(11.3), Inches(0.35), Inches(1.5), Inches(0.3),
             chapter, size=10, bold=True, color=INK_MUTED, font=FONT_M,
             align=PP_ALIGN.RIGHT)
    add_text(slide, Inches(0.6), Inches(0.65), Inches(12.2), Inches(1.1),
             title, size=36, bold=True, color=INK, font=FONT_H)
    add_line(slide, Inches(0.6), Inches(1.55), Inches(12.7), Inches(1.55),
             color=INK, width=1.5)


def footer(slide, page_no, total):
    add_text(slide, Inches(0.6), Inches(7.05), Inches(6), Inches(0.3),
             "BODHI.AI — QUESTION PAPER STUDIO", size=9,
             color=INK_MUTED, font=FONT_M, bold=True)
    add_text(slide, Inches(11.3), Inches(7.05), Inches(1.5), Inches(0.3),
             f"{page_no:02d} / {total:02d}", size=9, color=INK_MUTED,
             font=FONT_M, bold=True, align=PP_ALIGN.RIGHT)


# ---------- Slide builders ----------
def slide_cover(prs, total):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    add_bg(s)

    # Klein blue block on the left
    add_rect(s, 0, 0, Inches(5.6), SLIDE_H, fill=BLUE, line=None)

    # Yellow tick block bottom-left for character
    add_rect(s, Inches(0), Inches(6.8), Inches(0.7), Inches(0.7),
             fill=YELLOW, line=None)

    # Left panel content
    add_text(s, Inches(0.6), Inches(0.6), Inches(4.5), Inches(0.35),
             "// PRODUCT WALKTHROUGH", size=11, bold=True,
             color=YELLOW, font=FONT_M)
    add_text(s, Inches(0.6), Inches(1.15), Inches(4.7), Inches(0.5),
             "Bodhi.ai", size=52, bold=True, color=RGBColor(0xFF, 0xFF, 0xFF),
             font=FONT_H)
    add_text(s, Inches(0.6), Inches(2.2), Inches(4.7), Inches(0.4),
             "QUESTION PAPER STUDIO", size=13, bold=True,
             color=YELLOW, font=FONT_M)

    # Divider
    add_line(s, Inches(0.6), Inches(2.9), Inches(4.9), Inches(2.9),
             color=RGBColor(0xFF, 0xFF, 0xFF), width=1.25)

    add_text(s, Inches(0.6), Inches(3.1), Inches(4.7), Inches(2),
             "Design exams\nalgorithmically.", size=30, bold=True,
             color=RGBColor(0xFF, 0xFF, 0xFF), font=FONT_H)

    add_text(s, Inches(0.6), Inches(5.05), Inches(4.7), Inches(1.5),
             ("A complete AI paper-generation and mock-test platform for "
              "teachers of ICSE / CBSE / ISC boards and JEE / NEET / CAT / "
              "UPSC coaching."),
             size=13, color=RGBColor(0xE8, 0xE8, 0xE8), font=FONT_B)

    add_text(s, Inches(0.6), Inches(6.85), Inches(4), Inches(0.3),
             "PREPARED FOR THE TEACHING TEAM", size=9,
             color=YELLOW, font=FONT_M, bold=True)

    # Right side — big index card
    add_rect(s, Inches(6.3), Inches(1.15), Inches(6.5), Inches(5.7),
             fill=SURFACE, line=INK, line_w=1.5)

    add_text(s, Inches(6.6), Inches(1.35), Inches(6), Inches(0.3),
             "// INSIDE THIS DECK", size=10, bold=True,
             color=BLUE, font=FONT_M)

    toc = [
        ("01", "The problem with manual paper setting"),
        ("02", "What Bodhi.ai does — feature map"),
        ("03", "Teacher workflow — 8 steps end-to-end"),
        ("04", "Board blueprints  ·  ICSE / CBSE / ISC"),
        ("05", "Competitive presets  ·  JEE / NEET / CAT / UPSC"),
        ("06", "Student side  ·  mock tests + analytics"),
        ("07", "AI, OCR, RAG — how it works"),
        ("08", "What teachers get out of it"),
    ]
    y = Inches(1.85)
    for num, text in toc:
        add_text(s, Inches(6.6), y, Inches(0.6), Inches(0.35),
                 num, size=13, bold=True, color=BLUE, font=FONT_M)
        add_text(s, Inches(7.35), y, Inches(5.2), Inches(0.35),
                 text, size=14, color=INK, font=FONT_B)
        y += Inches(0.58)

    add_text(s, Inches(6.6), Inches(6.55), Inches(6), Inches(0.3),
             "10-minute read  ·  live demo follows", size=10,
             italic=True, color=INK_MUTED, font=FONT_B)


def slide_problem(prs, page, total):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    add_bg(s)
    header(s, f"CHAPTER 01 / {total-2:02d}",
           "// WHY WE BUILT THIS",
           "Setting a good paper still costs a full weekend.")

    # Left column — pain points
    add_text(s, Inches(0.6), Inches(1.85), Inches(6.2), Inches(0.35),
             "// THE OLD WORKFLOW", size=10, bold=True,
             color=INK_MUTED, font=FONT_M)

    pains = [
        ("~4 hrs", "Re-typing questions from previous year papers and reference guides."),
        ("~2 hrs", "Balancing sections, marks, difficulty and topic coverage by hand."),
        ("~1 hr",  "Typing formulas, equations and chemistry in a word processor."),
        ("~1 hr",  "Creating a matching answer key and marking scheme."),
        ("0",      "Zero data on which topics students actually get wrong."),
    ]
    y = Inches(2.3)
    for tag, text in pains:
        add_rect(s, Inches(0.6), y, Inches(1.05), Inches(0.55),
                 fill=INK, line=None)
        add_text(s, Inches(0.6), y, Inches(1.05), Inches(0.55),
                 tag, size=13, bold=True, color=YELLOW, font=FONT_M,
                 align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
        add_text(s, Inches(1.85), y + Inches(0.04), Inches(4.9), Inches(0.55),
                 text, size=13, color=INK, font=FONT_B)
        y += Inches(0.68)

    # Right column — cost
    add_rect(s, Inches(7.4), Inches(1.85), Inches(5.4), Inches(4.7),
             fill=BLUE, line=None)
    add_text(s, Inches(7.7), Inches(2.05), Inches(5), Inches(0.35),
             "// THE HIDDEN COST", size=10, bold=True,
             color=YELLOW, font=FONT_M)
    add_text(s, Inches(7.7), Inches(2.55), Inches(5), Inches(2),
             "8+ hours", size=64, bold=True,
             color=RGBColor(0xFF, 0xFF, 0xFF), font=FONT_H)
    add_text(s, Inches(7.7), Inches(3.75), Inches(5), Inches(0.5),
             "per paper, per teacher", size=14, color=YELLOW, font=FONT_M,
             bold=True)
    add_line(s, Inches(7.7), Inches(4.35), Inches(12.5), Inches(4.35),
             color=YELLOW, width=1)
    add_text(s, Inches(7.7), Inches(4.55), Inches(5), Inches(2),
             ("For a school with 30 subject teachers and 4 assessments a "
              "year, that is roughly 960 teaching hours lost every "
              "academic year — before a single answer script is marked."),
             size=13, color=RGBColor(0xF0, 0xF0, 0xF0), font=FONT_B)

    footer(s, page, total)


def slide_solution(prs, page, total):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    add_bg(s)
    header(s, f"CHAPTER 02 / {total-2:02d}",
           "// THE SOLUTION",
           "One tool. Textbook in, exam-ready paper out.")

    # 4 pillars
    pillars = [
        ("01", "INGEST",
         "Upload any PDF — printed, scanned, or watermarked. "
         "OCR + AI extract the chapters and topics automatically."),
        ("02", "GENERATE",
         "Choose topics, difficulty, sections and format mix. "
         "AI drafts an original, calibrated paper in under 2 minutes."),
        ("03", "REFINE",
         "Edit any question inline. Regenerate a single item. "
         "One-click answer key with step-wise solutions."),
        ("04", "ASSESS",
         "Assign as a timed mock test to students. Auto-grade MCQs. "
         "See topic-wise weakness heatmaps."),
    ]
    x = Inches(0.6)
    for i, (num, tag, body) in enumerate(pillars):
        add_rect(s, x, Inches(2.0), Inches(3.0), Inches(4.5),
                 fill=SURFACE, line=INK, line_w=1.5)
        # top bar
        add_rect(s, x, Inches(2.0), Inches(3.0), Inches(0.55),
                 fill=INK, line=None)
        add_text(s, x + Inches(0.2), Inches(2.05), Inches(0.6), Inches(0.45),
                 num, size=13, bold=True, color=YELLOW, font=FONT_M,
                 anchor=MSO_ANCHOR.MIDDLE)
        add_text(s, x + Inches(1.0), Inches(2.05), Inches(2.0), Inches(0.45),
                 tag, size=15, bold=True, color=RGBColor(0xFF, 0xFF, 0xFF),
                 font=FONT_H, anchor=MSO_ANCHOR.MIDDLE)
        # body
        add_text(s, x + Inches(0.25), Inches(2.85), Inches(2.55), Inches(3.4),
                 body, size=12, color=INK, font=FONT_B)
        # yellow accent
        add_rect(s, x + Inches(0.25), Inches(6.1), Inches(0.6), Inches(0.15),
                 fill=YELLOW, line=None)
        x += Inches(3.1)

    footer(s, page, total)


def slide_workflow_overview(prs, page, total):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    add_bg(s)
    header(s, f"CHAPTER 03 / {total-2:02d}",
           "// TEACHER JOURNEY",
           "The 8-step workflow, at a glance.")

    steps = [
        ("01", "Upload PDF",       "Textbooks tab"),
        ("02", "OCR + Topics",     "Auto, ~30s"),
        ("03", "Configure paper",  "Topics · marks · mix"),
        ("04", "Pick blueprint",   "ICSE / CBSE / ISC"),
        ("05", "AI generates",     "Parallel LLM batches"),
        ("06", "Edit inline",      "Any question"),
        ("07", "Answer key",       "Step-by-step"),
        ("08", "Download PDF",     "Print-ready"),
    ]
    # 4x2 grid
    x0 = Inches(0.6); y0 = Inches(2.0)
    cw = Inches(3.05); ch = Inches(2.15); gap_x = Inches(0.05); gap_y = Inches(0.15)
    for i, (num, name, sub) in enumerate(steps):
        col = i % 4; row = i // 4
        x = x0 + (cw + gap_x) * col
        y = y0 + (ch + gap_y) * row
        add_rect(s, x, y, cw, ch, fill=SURFACE, line=INK, line_w=1.25)
        # step badge
        add_rect(s, x, y, Inches(0.9), Inches(0.55), fill=BLUE, line=None)
        add_text(s, x, y, Inches(0.9), Inches(0.55),
                 num, size=15, bold=True, color=YELLOW, font=FONT_M,
                 align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
        add_text(s, x + Inches(0.25), y + Inches(0.75), cw - Inches(0.5),
                 Inches(0.7), name, size=20, bold=True, color=INK,
                 font=FONT_H)
        add_text(s, x + Inches(0.25), y + Inches(1.5), cw - Inches(0.5),
                 Inches(0.4), sub, size=11, color=INK_MUTED, font=FONT_M)
        # arrow to next
        if col < 3:
            ax1 = x + cw + Emu(1)
            ax2 = x + cw + gap_x - Emu(1)
            ay = y + ch/2
            add_line(s, ax1, ay, ax2, ay, color=INK_MUTED, width=1)

    add_text(s, Inches(0.6), Inches(6.55), Inches(12), Inches(0.4),
             "Every step in detail on the next pages →", size=12,
             italic=True, color=INK_MUTED, font=FONT_B)

    footer(s, page, total)


def _step_slide(prs, page, total, num, title, description,
                what_you_see, why_it_matters, tag):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    add_bg(s)
    header(s, f"STEP {num} / 08", f"// {tag}", title)

    # Left — description card
    add_rect(s, Inches(0.6), Inches(1.85), Inches(6.3), Inches(5.0),
             fill=SURFACE, line=INK, line_w=1.5)
    add_text(s, Inches(0.85), Inches(2.05), Inches(5.8), Inches(0.35),
             "// WHAT HAPPENS", size=10, bold=True,
             color=BLUE, font=FONT_M)
    add_text(s, Inches(0.85), Inches(2.45), Inches(5.8), Inches(4.2),
             description, size=14, color=INK, font=FONT_B)

    # Right — what you see + why it matters
    add_rect(s, Inches(7.15), Inches(1.85), Inches(5.65), Inches(2.4),
             fill=BLUE, line=None)
    add_text(s, Inches(7.4), Inches(2.05), Inches(5.2), Inches(0.35),
             "// WHAT YOU SEE ON SCREEN", size=10, bold=True,
             color=YELLOW, font=FONT_M)
    add_text(s, Inches(7.4), Inches(2.45), Inches(5.2), Inches(1.7),
             what_you_see, size=13, color=RGBColor(0xF3, 0xF3, 0xF3),
             font=FONT_B)

    add_rect(s, Inches(7.15), Inches(4.35), Inches(5.65), Inches(2.5),
             fill=SURFACE, line=INK, line_w=1.5)
    # yellow left band
    add_rect(s, Inches(7.15), Inches(4.35), Inches(0.15), Inches(2.5),
             fill=YELLOW, line=None)
    add_text(s, Inches(7.5), Inches(4.55), Inches(5.2), Inches(0.35),
             "// WHY IT MATTERS", size=10, bold=True,
             color=INK, font=FONT_M)
    add_text(s, Inches(7.5), Inches(4.95), Inches(5.2), Inches(1.8),
             why_it_matters, size=13, color=INK, font=FONT_B)

    footer(s, page, total)


def slide_boards(prs, page, total):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    add_bg(s)
    header(s, f"CHAPTER 04 / {total-2:02d}",
           "// BOARD BLUEPRINTS",
           "Four one-click templates. Verified against 2026 specimens.")

    boards = [
        ("ICSE", "Class 10",
         "80 marks · 2 hrs\n+ 15 min reading",
         ["Sec A (40m) — 15 MCQs + fills + short-answer",
          "Sec B (40m) — Attempt any 4 of 6 · 10m each",
          "Sub-parts (a) 3m + (b) 3m + (c) 4m"]),
        ("CBSE", "Class 10",
         "80 marks · 3 hrs",
         ["Sec A — 16 MCQs · 1 mark",
          "Sec B–D — VSA · SA · LA (2/3/5 mark)",
          "Sec E — 3 case-study questions · 4m each"]),
        ("ISC",  "Class 12",
         "70 marks theory · 3 hrs\n+ 15 min reading",
         ["Sec A — 14 objective/MCQ · 1 mark",
          "Sec B — 10 short-answer · 2 marks",
          "Sec C — 7 short-answer · 3 marks",
          "Sec D — 3 long-answer · 5 marks"]),
        ("CBSE", "Class 12",
         "80 marks · 3 hrs",
         ["Sec A — 20 MCQ + assertion-reason",
          "Sec B–D — VSA · SA · LA with internal choice",
          "Sec E — 3 case-study · 4m each",
          "~50% competency-based content"]),
    ]

    x = Inches(0.6)
    for i, (board, klass, meta, bullets) in enumerate(boards):
        # card
        add_rect(s, x, Inches(2.0), Inches(3.0), Inches(4.75),
                 fill=SURFACE, line=INK, line_w=1.5)
        # top tag
        add_rect(s, x, Inches(2.0), Inches(3.0), Inches(0.65),
                 fill=YELLOW if i % 2 == 0 else INK, line=None)
        add_text(s, x + Inches(0.2), Inches(2.05), Inches(2.6), Inches(0.55),
                 f"{board} · {klass}", size=16, bold=True,
                 color=INK if i % 2 == 0 else YELLOW, font=FONT_H,
                 anchor=MSO_ANCHOR.MIDDLE)
        # meta
        add_text(s, x + Inches(0.2), Inches(2.85), Inches(2.6), Inches(0.85),
                 meta, size=12, bold=True, color=BLUE, font=FONT_M)
        # divider
        add_line(s, x + Inches(0.2), Inches(3.85), x + Inches(2.8),
                 Inches(3.85), color=GREY_LINE, width=1)
        # bullets
        text = "\n".join(f"— {b}" for b in bullets)
        add_text(s, x + Inches(0.2), Inches(3.95), Inches(2.7), Inches(2.7),
                 text, size=11, color=INK, font=FONT_B)
        x += Inches(3.1)

    add_text(s, Inches(0.6), Inches(6.9), Inches(12), Inches(0.35),
             ("Each preset auto-fills the section layout. Teachers can "
              "still tweak marks, difficulty and topics before generating."),
             size=11, italic=True, color=INK_MUTED, font=FONT_B)

    footer(s, page, total)


def slide_competitive(prs, page, total):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    add_bg(s)
    header(s, f"CHAPTER 05 / {total-2:02d}",
           "// COMPETITIVE PRESETS",
           "Locked NTA / IIM / UPSC formats for coaching institutes.")

    exams = [
        ("JEE Main",   "75 q · 180 min",  "PCM · 25 each · +4 / -1",   BLUE),
        ("JEE Advanced","54 q · 180 min", "PCM · 18 each · single-paper", INK),
        ("NEET UG",    "180 q · 200 min", "P·C·B (Botany + Zoology)",  RED),
        ("CAT",        "66 q · 120 min",  "VARC · DILR · QA · 40m each", BLUE),
        ("UPSC Prelims","100 q · 120 min","GS Paper I · -0.66 negative", INK),
    ]

    # Left column — cards
    y = Inches(1.9)
    for name, spec, subs, color in exams:
        add_rect(s, Inches(0.6), y, Inches(6.6), Inches(0.9),
                 fill=SURFACE, line=INK, line_w=1.25)
        add_rect(s, Inches(0.6), y, Inches(0.25), Inches(0.9),
                 fill=color, line=None)
        add_text(s, Inches(1.0), y + Inches(0.08), Inches(3), Inches(0.4),
                 name, size=17, bold=True, color=INK, font=FONT_H)
        add_text(s, Inches(1.0), y + Inches(0.5), Inches(3), Inches(0.35),
                 spec, size=11, color=BLUE, bold=True, font=FONT_M)
        add_text(s, Inches(4.1), y + Inches(0.15), Inches(3.0),
                 Inches(0.7), subs, size=11, color=INK_SOFT,
                 font=FONT_B, anchor=MSO_ANCHOR.MIDDLE)
        y += Inches(0.98)

    # Right — RAG calibration explainer
    add_rect(s, Inches(7.5), Inches(1.9), Inches(5.3), Inches(4.9),
             fill=INK, line=None)
    add_text(s, Inches(7.75), Inches(2.1), Inches(5), Inches(0.35),
             "// UNDER THE HOOD", size=10, bold=True,
             color=YELLOW, font=FONT_M)
    add_text(s, Inches(7.75), Inches(2.5), Inches(5), Inches(0.9),
             "RAG-calibrated difficulty",
             size=24, bold=True, color=RGBColor(0xFF, 0xFF, 0xFF),
             font=FONT_H)
    add_line(s, Inches(7.75), Inches(3.55), Inches(12.5), Inches(3.55),
             color=YELLOW, width=1)
    add_text(s, Inches(7.75), Inches(3.7), Inches(5), Inches(3),
             ("For every competitive exam we ship a corpus of past-year "
              "questions tagged by topic and difficulty.\n\n"
              "When you generate, Bodhi.ai retrieves the closest matches "
              "(TF-IDF similarity) and calibrates the LLM prompt so the "
              "output feels like a real NTA / IIM paper — not a generic "
              "textbook question."),
             size=12, color=RGBColor(0xE8, 0xE8, 0xE8), font=FONT_B)

    footer(s, page, total)


def slide_student(prs, page, total):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    add_bg(s)
    header(s, f"CHAPTER 06 / {total-2:02d}",
           "// STUDENT SIDE",
           "Every paper you make can become a mock test.")

    # Left — mock exam UI mock
    add_rect(s, Inches(0.6), Inches(1.9), Inches(6.2), Inches(4.9),
             fill=SURFACE, line=INK, line_w=1.5)
    # Header bar
    add_rect(s, Inches(0.6), Inches(1.9), Inches(6.2), Inches(0.55),
             fill=INK, line=None)
    add_text(s, Inches(0.8), Inches(1.9), Inches(3), Inches(0.55),
             "Mock Test · Chemistry ISC 12", size=13, bold=True,
             color=RGBColor(0xFF, 0xFF, 0xFF), font=FONT_H,
             anchor=MSO_ANCHOR.MIDDLE)
    add_rect(s, Inches(5.65), Inches(2.0), Inches(1.05), Inches(0.35),
             fill=YELLOW, line=None)
    add_text(s, Inches(5.65), Inches(2.0), Inches(1.05), Inches(0.35),
             "58:24", size=12, bold=True, color=INK, font=FONT_M,
             align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)

    # Question
    add_text(s, Inches(0.85), Inches(2.7), Inches(5.7), Inches(0.35),
             "Q07 · Section B · 2 marks", size=10, bold=True,
             color=BLUE, font=FONT_M)
    add_text(s, Inches(0.85), Inches(3.05), Inches(5.7), Inches(1),
             "The coordination number of Na⁺ in NaCl is:",
             size=14, bold=True, color=INK, font=FONT_H)

    for i, (opt, val, sel) in enumerate([
        ("A", "4", False), ("B", "6", True),
        ("C", "8", False), ("D", "12", False)]):
        y = Inches(4.05) + Inches(0.55) * i
        add_rect(s, Inches(0.85), y, Inches(5.7), Inches(0.45),
                 fill=BLUE if sel else SURFACE, line=INK, line_w=0.75)
        add_text(s, Inches(1.05), y, Inches(5.5), Inches(0.45),
                 f"({opt})   {val}",
                 size=12, bold=sel,
                 color=RGBColor(0xFF, 0xFF, 0xFF) if sel else INK,
                 font=FONT_B, anchor=MSO_ANCHOR.MIDDLE)

    # Right — feature bullets
    add_text(s, Inches(7.2), Inches(1.95), Inches(5.6), Inches(0.35),
             "// WHAT STUDENTS GET", size=10, bold=True,
             color=BLUE, font=FONT_M)

    feats = [
        ("Timed mode",     "Real countdown with auto-submit on expiry."),
        ("Autosave",       "Answers persist per question — no lost work if browser closes."),
        ("MCQ auto-grade", "Instant score + section-wise breakdown."),
        ("Topic heatmap",  "See which topics the student is weakest on."),
        ("Question review","Correct answer + explanation revealed after submit."),
        ("Retake",         "Regenerate a fresh variant on the same topics."),
    ]
    y = Inches(2.4)
    for name, desc in feats:
        # bullet dot
        add_rect(s, Inches(7.2), y + Inches(0.16), Inches(0.15), Inches(0.15),
                 fill=YELLOW, line=None)
        add_text(s, Inches(7.5), y, Inches(5.3), Inches(0.35),
                 name, size=14, bold=True, color=INK, font=FONT_H)
        add_text(s, Inches(7.5), y + Inches(0.35), Inches(5.3), Inches(0.35),
                 desc, size=11, color=INK_SOFT, font=FONT_B)
        y += Inches(0.72)

    footer(s, page, total)


def slide_tech(prs, page, total):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    add_bg(s)
    header(s, f"CHAPTER 07 / {total-2:02d}",
           "// HOW IT WORKS",
           "Six moving parts. Zero teacher configuration.")

    parts = [
        ("Multi-model AI",
         "OpenAI GPT-5.2 · Claude Sonnet 4.5 · Gemini 3.1 Pro. "
         "Bodhi.ai auto-picks the right model per exam type — with "
         "retry-and-fallback between providers."),
        ("OCR for scans",
         "Tesseract + Poppler process image-heavy or watermarked PDFs "
         "(SL Arora, CamScanner scans, textbook photocopies). No manual "
         "cleanup needed."),
        ("RAG difficulty tuning",
         "TF-IDF retrieval of past-year questions calibrates each prompt "
         "so JEE feels like JEE, not like a Class 10 worksheet."),
        ("Parallel batching",
         "Long papers (100+ questions) run in parallel LLM batches to "
         "cut wall-clock time from 6 min → under 90 sec."),
        ("LaTeX + chem PNGs",
         "Inline math and chemistry formulas rendered at 600 DPI. "
         "Prints razor-sharp on any classroom printer."),
        ("Salvage + recovery",
         "Truncated LLM responses are salvaged automatically. Papers "
         "orphaned by a server restart resume on their own."),
    ]

    x0, y0 = Inches(0.6), Inches(2.0)
    cw, ch = Inches(4.05), Inches(2.35)
    for i, (name, desc) in enumerate(parts):
        col = i % 3; row = i // 3
        x = x0 + (cw + Inches(0.05)) * col
        y = y0 + (ch + Inches(0.15)) * row
        add_rect(s, x, y, cw, ch, fill=SURFACE, line=INK, line_w=1.25)
        add_rect(s, x, y, Inches(0.15), ch, fill=BLUE, line=None)
        add_text(s, x + Inches(0.35), y + Inches(0.2), cw - Inches(0.5),
                 Inches(0.5), name, size=15, bold=True, color=INK,
                 font=FONT_H)
        add_text(s, x + Inches(0.35), y + Inches(0.75), cw - Inches(0.5),
                 ch - Inches(0.85), desc, size=11, color=INK_SOFT,
                 font=FONT_B)

    footer(s, page, total)


def slide_benefits(prs, page, total):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    add_bg(s)
    header(s, f"CHAPTER 08 / {total-2:02d}",
           "// FOR THE TEACHER",
           "What you get back — in numbers and in headspace.")

    metrics = [
        ("8 hrs → 15 min",  "per paper cycle",           BLUE),
        ("4 boards",        "ICSE · CBSE · ISC · IB",    INK),
        ("5 exams",         "JEE · NEET · CAT · UPSC",   YELLOW),
        ("100%",             "original content",         GREEN),
    ]
    x = Inches(0.6)
    for value, label, color in metrics:
        add_rect(s, x, Inches(1.95), Inches(3.05), Inches(2.0),
                 fill=color if color != YELLOW else YELLOW,
                 line=INK, line_w=1.5)
        add_text(s, x + Inches(0.25), Inches(2.15), Inches(2.8), Inches(1.0),
                 value, size=24 if len(value) > 8 else 32, bold=True,
                 color=INK if color in (YELLOW,) else RGBColor(0xFF, 0xFF, 0xFF),
                 font=FONT_H)
        add_text(s, x + Inches(0.25), Inches(3.3), Inches(2.8), Inches(0.5),
                 label, size=12, bold=True,
                 color=INK if color in (YELLOW,) else YELLOW,
                 font=FONT_M)
        x += Inches(3.11)

    # Bottom — quotes / talking points
    add_rect(s, Inches(0.6), Inches(4.25), Inches(12.15), Inches(2.55),
             fill=SURFACE, line=INK, line_w=1.5)
    add_text(s, Inches(0.85), Inches(4.4), Inches(11), Inches(0.35),
             "// WHY TEACHERS ADOPT IT", size=10, bold=True,
             color=BLUE, font=FONT_M)

    points = [
        ("Weekends back.",
         "The mechanical part of paper-setting is off your plate. You "
         "spend the time on lesson design and 1-on-1 doubt clearing."),
        ("Consistency across a department.",
         "Every teacher in the same subject can generate papers with "
         "identical marks distribution and difficulty."),
        ("Data on where students struggle.",
         "The topic heatmap turns each mock into actionable feedback for "
         "the next lesson."),
    ]
    y = Inches(4.85)
    for head, body in points:
        add_rect(s, Inches(0.85), y + Inches(0.15), Inches(0.15),
                 Inches(0.15), fill=YELLOW, line=None)
        add_text(s, Inches(1.15), y, Inches(11.5), Inches(0.35),
                 head, size=13, bold=True, color=INK, font=FONT_H)
        add_text(s, Inches(1.15), y + Inches(0.35), Inches(11.5),
                 Inches(0.35), body, size=11, color=INK_SOFT, font=FONT_B)
        y += Inches(0.62)

    footer(s, page, total)


def slide_demo_cta(prs, page, total):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    add_bg(s, color=INK)
    # yellow slash
    add_rect(s, 0, 0, Inches(0.4), SLIDE_H, fill=YELLOW, line=None)

    add_text(s, Inches(0.9), Inches(0.7), Inches(12), Inches(0.35),
             "// LIVE DEMO", size=11, bold=True,
             color=YELLOW, font=FONT_M)

    add_text(s, Inches(0.9), Inches(1.3), Inches(12), Inches(1.5),
             "Let's build a paper together.", size=54, bold=True,
             color=RGBColor(0xFF, 0xFF, 0xFF), font=FONT_H)

    add_line(s, Inches(0.9), Inches(3.15), Inches(12.4), Inches(3.15),
             color=YELLOW, width=1.5)

    add_text(s, Inches(0.9), Inches(3.35), Inches(12), Inches(0.5),
             ("Pick any chapter from a class textbook. In the next "
              "10 minutes we will:"),
             size=16, color=RGBColor(0xE8, 0xE8, 0xE8), font=FONT_B)

    steps = [
        "Upload the chapter as a PDF",
        "Watch topics get extracted live",
        "Configure a 40-mark paper with an ICSE Class-10 blueprint",
        "Generate, edit one question, and download the print-ready PDF",
    ]
    y = Inches(4.15)
    for i, step in enumerate(steps, start=1):
        add_text(s, Inches(0.9), y, Inches(0.6), Inches(0.4),
                 f"{i:02d}", size=18, bold=True, color=YELLOW, font=FONT_M)
        add_text(s, Inches(1.6), y, Inches(11), Inches(0.4),
                 step, size=16, color=RGBColor(0xF0, 0xF0, 0xF0),
                 font=FONT_B)
        y += Inches(0.55)

    add_text(s, Inches(0.9), Inches(6.75), Inches(12), Inches(0.35),
             "Ready when you are.  →", size=13, bold=True,
             color=YELLOW, font=FONT_M)

    footer(s, page, total)


# ---------- Build ----------
def build():
    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H

    total = 15   # cover + 8 chapters + 5 workflow step slides + demo + closer
    slide_cover(prs, total)
    slide_problem(prs, 2, total)
    slide_solution(prs, 3, total)
    slide_workflow_overview(prs, 4, total)

    # Detailed step slides — 5 chosen because they carry the story
    _step_slide(
        prs, 5, total, "01",
        "Upload the textbook.",
        ("Drag any PDF onto the Textbooks page — scanned, printed, "
         "photocopied, watermarked. Bodhi.ai supports files up to "
         "80 MB and auto-runs OCR on image-heavy PDFs (like SL Arora "
         "or CamScanner scans).\n\n"
         "You can also tag a book as school-wide so every teacher "
         "in the department can generate off the same source."),
        ("A tile appears in the Textbooks grid with a live status "
         "chip: ingesting → indexed → topics ready."),
        ("You never re-type a single question. Your school's own "
         "reference material becomes the AI's context — so questions "
         "match what students were actually taught."),
        "STEP 01 · INGEST",
    )
    _step_slide(
        prs, 6, total, "02",
        "Extract topics automatically.",
        ("Behind the scenes, the PDF is chunked, OCR-cleaned and "
         "fed into an LLM that produces a hierarchical topic tree — "
         "chapters → sections → subtopics.\n\n"
         "For a Class-10 Physics textbook this typically gives you "
         "12–20 top-level topics ready to pick from, without any "
         "manual tagging."),
        ("Click 'Extract Topics'. In ~30 seconds a checkbox list of "
         "topics appears, each with an editable weight slider."),
        ("You control exactly which topics appear on the paper and "
         "in what proportion — without ever writing a syllabus mapping "
         "by hand."),
        "STEP 02 · EXTRACT",
    )
    _step_slide(
        prs, 7, total, "03",
        "Configure the paper.",
        ("Choose topics, difficulty (easy · medium · hard · mixed), "
         "duration, total marks, cognitive mix (information / concept "
         "/ application) and question-format mix (MCQ · short-answer "
         "· long-answer · numerical · match-the-following · custom).\n\n"
         "Or override everything with a section blueprint text-box that "
         "the AI follows verbatim."),
        ("A structured form with sliders and pill-shaped format "
         "chips. Every change is reflected live in a running preview."),
        ("Papers stay aligned with the pedagogy of the board or "
         "coaching program — no surprise question types show up on "
         "the day of the test."),
        "STEP 03 · CONFIGURE",
    )
    _step_slide(
        prs, 8, total, "05",
        "AI drafts the paper.",
        ("Bodhi.ai splits the workload across parallel LLM batches: "
         "20-question chunks for board papers, larger batches for "
         "competitive exams. Each batch is routed to the best-suited "
         "model (GPT for numericals, Claude for reasoning, Gemini for "
         "biology diagrams).\n\n"
         "If any batch times out or truncates, the response is "
         "salvaged automatically — you never see a 500 error."),
        ("A live progress bar shows sections filling in as they are "
         "generated. Typical 80-mark board paper: ~90 seconds."),
        ("You go from a blank Google Doc to a printable exam faster "
         "than it takes to fill a coffee cup."),
        "STEP 05 · GENERATE",
    )
    _step_slide(
        prs, 9, total, "07",
        "Answer key with step-wise solutions.",
        ("From the Paper view, one click generates a full solution "
         "PDF — answers plus step-by-step working for every "
         "numerical, mechanism or derivation. Chemistry equations "
         "render with proper subscripts and arrows; math with LaTeX "
         "rendered at 600 DPI.\n\n"
         "Solutions can be bulk-regenerated if you edit a question."),
        ("A 'Generate Solutions' button. A minute later, a second "
         "PDF appears in Downloads titled '<paper> — Answer Key'."),
        ("Marking scripts becomes a matter of comparison, not "
         "recalculation. And peer teachers can grade any paper "
         "without needing your notes."),
        "STEP 07 · ANSWER KEY",
    )

    slide_boards(prs, 10, total)
    slide_competitive(prs, 11, total)
    slide_student(prs, 12, total)
    slide_tech(prs, 13, total)
    slide_benefits(prs, 14, total)
    slide_demo_cta(prs, 15, total)

    out = "/app/memory/Bodhi_Teacher_Walkthrough.pptx"
    prs.save(out)
    print(f"Saved: {out}")


if __name__ == "__main__":
    build()
