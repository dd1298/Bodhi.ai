"""Verify metadata-only NTA PDFs are detected so OCR fallback fires.

Real-world failure mode: NTA's JEE Mains result PDFs render each question
stem as a page image (LaTeX/diagrams) and leave only metadata wrappers in
the text layer ("Question Number :", "Question Id :", "Options :",
"6911215.", etc.). pypdf's text extraction succeeds (high char count) but
produces no actual question prose — so the LLM extraction call returns 0
questions. The heuristic below catches this and forces OCR.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pdf_utils import _looks_like_metadata_only  # noqa: E402


def test_nta_metadata_block_triggers_ocr():
    """Synthesise the exact text pattern pypdf returns for an NTA JEE PDF."""
    block = ""
    for i in range(1, 21):
        block += (
            f"Question Number : {i} Question Id : 691121{i:02d} Question Type : MCQ "
            "Option Shuffling : Yes Display Question Number : Yes IsQuestion Mandatory : No "
            "Single Line Question Option : No Option Orientation : Vertical\n"
            "Options :\n"
            f"691121{i:02d}1.\n"
            f"691121{i:02d}2.\n"
            f"691121{i:02d}3.\n"
            f"691121{i:02d}4.\n\n"
        )
    assert _looks_like_metadata_only(block) is True


def test_normal_question_paper_does_not_trigger_ocr():
    """A paper with real question prose between markers must NOT trigger OCR."""
    block = ""
    for i in range(1, 11):
        block += (
            f"Question Number : {i}\n"
            f"Q{i}. Solve the quadratic equation x^2 - 5x + 6 = 0 and find the "
            "sum of its roots. Then verify your answer by substituting back into "
            "the original equation. Show all working steps clearly. The expected "
            "answer is 5 (sum of roots equals -b/a in standard form ax^2 + bx + c).\n\n"
            "(a) 5\n(b) 6\n(c) -5\n(d) -6\n\n"
        )
    assert _looks_like_metadata_only(block) is False


def test_short_text_does_not_false_positive():
    """Fewer than 5 'Question Number' markers shouldn't trigger OCR."""
    assert _looks_like_metadata_only("Question Number : 1\nReal question text\n" * 3) is False


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
