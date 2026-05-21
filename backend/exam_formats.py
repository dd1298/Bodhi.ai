"""Official paper formats for competitive exams.

Centralised so the backend can lock the prescribed format (question count,
duration, marks, format mix) when generating a paper, and the frontend can
display the same canonical info to the user.

Counts and durations reflect the public conducting-body specs (NTA for
JEE/NEET, UPSC, IIM for CAT) as of 2026. We accept that an LLM may chunk
the output across batches for very long papers — the `batch_size` field
controls that.
"""
from __future__ import annotations


EXAM_FORMATS: dict[str, dict] = {
    "JEE_MAINS": {
        "label": "JEE Main 2026 — NTA pattern",
        "question_count": 75,
        "duration_minutes": 180,
        "total_marks": 300,
        # Practice papers in Bodhi.ai use 100% 4-option MCQ for every question
        # (including items that would be numerical-answer in the real NTA exam)
        # so students see consistent 4-option choices and we can auto-grade.
        "format_distribution": {"mcq": 100},
        "batch_size": 30,
        "subjects": ["Physics", "Chemistry", "Mathematics"],
        "notes": (
            "Three subjects × 25 questions each (4-option MCQ practice format). "
            "+4 / -1 marking. Three hours."
        ),
    },
    "JEE_ADV": {
        "label": "JEE Advanced 2026 — IIT pattern (single paper)",
        "question_count": 54,
        "duration_minutes": 180,
        "total_marks": 180,
        "format_distribution": {"mcq": 100},
        "batch_size": 27,
        "subjects": ["Physics", "Chemistry", "Mathematics"],
        "notes": (
            "One paper, three subjects × 18 questions each (4-option MCQ practice "
            "format with single correct answer). Three hours."
        ),
    },
    "CAT": {
        "label": "CAT — IIM pattern",
        "question_count": 66,
        "duration_minutes": 120,
        "total_marks": 198,
        "format_distribution": {"mcq": 100},
        "batch_size": 33,
        "subjects": ["VARC", "DILR", "QA"],
        "notes": (
            "Three sections × 22 questions: VARC, DILR, QA. 4-option MCQ "
            "practice format throughout. 40 min per section."
        ),
    },
    "UPSC": {
        "label": "UPSC CSE Prelims — GS Paper I",
        "question_count": 100,
        "duration_minutes": 120,
        "total_marks": 200,
        "format_distribution": {"mcq": 100},
        "batch_size": 34,
        "subjects": ["General Studies"],
        "notes": (
            "100 MCQs, 2 marks each, -0.66 negative marking. 'Critically examine / "
            "analyse / discuss' framing favoured for analytical depth."
        ),
    },
    "NEET": {
        "label": "NEET UG — PCB pattern",
        "question_count": 180,
        "duration_minutes": 200,
        "total_marks": 720,
        "format_distribution": {"mcq": 100},
        "batch_size": 30,
        "subjects": ["Physics", "Chemistry", "Botany", "Zoology"],
        "notes": (
            "Physics 45 + Chemistry 45 + Biology 90 (45 Botany + 45 Zoology) = 180 "
            "questions to attempt. +4 / -1 marking. NCERT-anchored."
        ),
    },
}


def get_format(exam_type: str | None) -> dict | None:
    """Return the locked format spec, or None for GENERIC / unknown types."""
    if not exam_type:
        return None
    return EXAM_FORMATS.get(exam_type.upper())
