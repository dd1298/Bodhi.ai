"""Prompt builders for topic extraction and question generation."""

TOPIC_SYSTEM = (
    "You are an expert academic content analyst. Given chapter text from a textbook, "
    "you extract a clean hierarchy of topics and subtopics that align strictly with the "
    "text. Do not invent topics not covered by the content."
)


def topic_extract_prompt(subject: str, klass: str, text_excerpt: str) -> str:
    return (
        f"Analyse the following textbook content for Class {klass} - {subject}. "
        "Identify the main topics and their subtopics. Return ONLY strict JSON of the form:\n"
        "{\n  \"topics\": [ { \"name\": \"Topic Name\", \"subtopics\": [\"Subtopic 1\", ...] } ]\n}\n\n"
        "Rules:\n"
        "- 4 to 10 top-level topics, each with 2-5 subtopics.\n"
        "- Names must be short (max 6 words), title case.\n"
        "- Cover ONLY what is present in the text.\n"
        "- No duplicates. No prose outside JSON.\n\n"
        f"=== TEXTBOOK CONTENT ===\n{text_excerpt}\n=== END ==="
    )


QGEN_SYSTEM = (
    "You are an expert teacher who designs original, high-quality exam questions. "
    "You NEVER copy textbook questions or content verbatim. You use the textbook only "
    "as a scope and style guide, never as a source to copy from. All questions must be "
    "originally phrased while staying strictly within the given topics."
)


QUESTION_TYPE_GUIDE = {
    "information": "Direct / information-based questions that recall facts, definitions, "
    "dates, formulas, or labelled concepts. Short, factual.",
    "concept": "Concept-based questions that test understanding of principles, "
    "relationships, reasoning and 'why/how' behind the topic.",
    "application": "Application-based questions that require applying concepts to "
    "scenarios, numerical problems, real-life cases or analysis.",
}


def qgen_prompt(
    subject: str,
    klass: str,
    topics: list[str],
    difficulty: str,
    distribution: dict,
    total_marks: int,
    duration: int,
    context_excerpt: str,
) -> str:
    # Compute counts from distribution (percentages)
    # Heuristic: target total questions based on marks (marks per question ~3 avg)
    target_q = max(5, min(25, total_marks // 3))
    info_n = round(target_q * distribution.get("information", 0) / 100)
    concept_n = round(target_q * distribution.get("concept", 0) / 100)
    app_n = max(1, target_q - info_n - concept_n) if target_q - info_n - concept_n > 0 else round(
        target_q * distribution.get("application", 0) / 100
    )

    guide = "\n".join(
        f"- {k}: {v}" for k, v in QUESTION_TYPE_GUIDE.items()
    )

    return (
        f"Generate an ORIGINAL question paper for Class {klass} - {subject}.\n"
        f"Topics to cover: {', '.join(topics)}\n"
        f"Overall difficulty: {difficulty}\n"
        f"Total marks: {total_marks}, Duration: {duration} minutes.\n"
        f"Target question counts: information={info_n}, concept={concept_n}, application={app_n}.\n\n"
        f"Question type definitions:\n{guide}\n\n"
        "Marks allocation: assign 1-2 marks for information, 3-4 for concept, 5-6 for application, "
        "ensuring the sum equals the total marks as closely as possible.\n\n"
        "Return ONLY strict JSON of the form:\n"
        "{\n"
        '  "instructions": "short instruction line",\n'
        '  "sections": [\n'
        '    { "title": "Section A - Information Based",\n'
        '      "questions": [ { "question": "...", "type": "information", "difficulty": "easy|medium|hard", "marks": 1 } ]\n'
        '    },\n'
        '    { "title": "Section B - Concept Based", "questions": [...] },\n'
        '    { "title": "Section C - Application Based", "questions": [...] }\n'
        "  ]\n"
        "}\n\n"
        "STRICT RULES:\n"
        "- Do NOT copy any sentence from the textbook content.\n"
        "- Every question must be originally phrased.\n"
        "- Stay strictly within the listed topics.\n"
        "- Ensure sum of marks of all questions equals the total marks.\n"
        "- No prose outside the JSON.\n\n"
        f"=== TEXTBOOK CONTEXT (style & scope only, DO NOT COPY) ===\n{context_excerpt}\n=== END ==="
    )
