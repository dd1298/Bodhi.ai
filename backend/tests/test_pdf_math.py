"""Smoke test: render a PDF with inline + block math and verify the math
images embedded by ReportLab are now proportionally sized (not the old
fixed height=13pt that produced bumpy lines)."""
import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pdf_utils import (  # noqa: E402
    render_paper_pdf,
    _math_to_paragraph_html,
    _render_math_png,
    _math_img_tag,
)


def test_math_img_tag_proportional():
    """The new _math_img_tag should produce both width and height attributes,
    proportional to the rendered PNG's aspect ratio."""
    # Tall stacked expression (fraction)
    frac_png = _render_math_png(r"\frac{a^2 + b^2}{c}")
    assert frac_png and os.path.exists(frac_png)
    tag = _math_img_tag(frac_png)
    assert 'width="' in tag and 'height="' in tag, f"missing dimensions: {tag}"

    # Single-line expression (no stacking)
    inline_png = _render_math_png(r"F = ma")
    assert inline_png and os.path.exists(inline_png)
    tag2 = _math_img_tag(inline_png)
    assert 'width="' in tag2 and 'height="' in tag2

    # Pull out heights — fraction must be visibly taller than F=ma
    h1 = float(re.search(r'height="([\d.]+)"', tag).group(1))
    h2 = float(re.search(r'height="([\d.]+)"', tag2).group(1))
    assert h1 > h2, f"fraction height ({h1}) should exceed inline height ({h2})"
    # Cap at 18pt
    assert h1 <= 18.0001
    print(f"OK  inline_h={h2:.2f}pt  fraction_h={h1:.2f}pt")


def test_math_to_paragraph_html_uses_new_tag():
    """Verify _math_to_paragraph_html emits the dynamic <img> with width+height."""
    html = _math_to_paragraph_html("Force is $F=ma$ and $$E=mc^2$$ is famous.")
    imgs = re.findall(r"<img[^>]+>", html)
    assert len(imgs) == 2, f"expected 2 math images, got {len(imgs)}"
    for img in imgs:
        assert 'width="' in img and 'height="' in img, f"img missing dims: {img}"
    print("OK  math HTML uses proportional <img> tags")


def test_trivial_latex_numbers_render_as_plain_text():
    """Regression: LLM often emits `$4$`, `$1.0$ M`, `$300K$` in ISC/CBSE chem
    papers. These must NOT leak literal `$` symbols to the PDF (bug reported
    by user 2026-02). Trivial numeric content should short-circuit past the
    matplotlib PNG path and emit clean text."""
    cases = {
        "Cell has $4$ atoms.": "Cell has 4 atoms.",
        "Concentration $1.0$ M solution.": "Concentration 1.0 M solution.",
        "At $300K$ the rate doubles.": "At 300K the rate doubles.",
        "Volume $25$ ml added.": "Volume 25 ml added.",
    }
    for inp, expected in cases.items():
        out = _math_to_paragraph_html(inp)
        assert "$" not in out, f"literal $ leaked for input {inp!r}: {out!r}"
        assert expected in out, f"expected {expected!r} in {out!r}"
    print("OK  trivial LaTeX numbers render as clean text")


def test_real_latex_still_renders_as_image():
    """Regression companion: proper LaTeX math (backslash commands, subscripts,
    fractions) must still hit the matplotlib PNG path — we don't want to over-
    correct and lose real math rendering."""
    out = _math_to_paragraph_html("React $H_2SO_4$ with $\\frac{n}{V}$ molarity.")
    imgs = re.findall(r"<img[^>]+>", out)
    assert len(imgs) == 2, f"expected 2 math images, got {len(imgs)}: {out!r}"
    print("OK  real LaTeX still renders as PNG images")



def test_render_full_paper_pdf():
    """End-to-end: render a paper with inline + block math, ensure non-empty PDF."""
    paper = {
        "title": "Bodhi.ai Math Sizing Test",
        "subject": "Physics",
        "class_name": "Class 10",
        "total_marks": 20,
        "duration_minutes": 60,
        "instructions": "Solve all questions. Show working where applicable.",
        "sections": [
            {
                "title": "Section A — Short Answer",
                "questions": [
                    {
                        "id": "q1",
                        "question": "State Newton's second law: $F = ma$.",
                        "marks": 2,
                        "difficulty": "easy",
                        "type": "short_answer",
                    },
                    {
                        "id": "q2",
                        "question": "Evaluate the integral $\\int_0^1 x^2 \\, dx$.",
                        "marks": 3,
                        "difficulty": "medium",
                        "type": "short_answer",
                    },
                    {
                        "id": "q3",
                        "question": (
                            "Einstein's famous equation is $$E = mc^2$$ — explain "
                            "the meaning of each symbol."
                        ),
                        "marks": 5,
                        "difficulty": "medium",
                        "type": "long_answer",
                    },
                    {
                        "id": "q4",
                        "question": (
                            "Solve $\\frac{a^2 + b^2}{2ab}$ when $a=3, b=4$. "
                            "Also note $90^\\circ$ in your steps."
                        ),
                        "marks": 5,
                        "difficulty": "hard",
                        "type": "long_answer",
                    },
                ],
            }
        ],
    }
    pdf_bytes = render_paper_pdf(paper)
    assert pdf_bytes and pdf_bytes.startswith(b"%PDF"), "not a valid PDF"
    out_path = "/tmp/bodhi_math_sizing_test.pdf"
    with open(out_path, "wb") as f:
        f.write(pdf_bytes)
    size_kb = len(pdf_bytes) / 1024
    print(f"OK  rendered {size_kb:.1f} KB PDF -> {out_path}")


if __name__ == "__main__":
    test_math_img_tag_proportional()
    test_math_to_paragraph_html_uses_new_tag()
    test_render_full_paper_pdf()
    print("\nAll PDF math sizing tests passed.")
