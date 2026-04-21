"""Prompt builders for topic extraction, question generation and solutions."""

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
    feedback_hints: str = "",
) -> str:
    target_q = max(5, min(25, total_marks // 3))
    info_n = round(target_q * distribution.get("information", 0) / 100)
    concept_n = round(target_q * distribution.get("concept", 0) / 100)
    app_n = max(1, target_q - info_n - concept_n) if target_q - info_n - concept_n > 0 else round(
        target_q * distribution.get("application", 0) / 100
    )

    guide = "\n".join(f"- {k}: {v}" for k, v in QUESTION_TYPE_GUIDE.items())
    feedback_block = ""
    if feedback_hints:
        feedback_block = (
            "\n=== TEACHER PREFERENCES (learned from past edits) ===\n"
            f"{feedback_hints}\n=== END ===\n\n"
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
        f"{feedback_block}"
        "DIAGRAM SUPPORT:\n"
        "Some questions benefit from a figure (Physics circuits, Biology labeled diagrams, "
        "Geography maps, Geometry shapes, Chemistry structures, Economics graphs, History timelines). "
        "For each such question, set 'needs_diagram': true and provide a concise 'diagram_description' "
        "(20-40 words). Otherwise set 'needs_diagram': false and omit diagram_description.\n\n"
        "Return ONLY strict JSON of the form:\n"
        "{\n"
        '  "instructions": "short instruction line",\n'
        '  "sections": [\n'
        '    { "title": "Section A - Information Based",\n'
        '      "questions": [\n'
        '        { "question": "...", "type": "information", "difficulty": "easy|medium|hard", "marks": 1,\n'
        '          "needs_diagram": false }\n'
        '      ]\n'
        '    }, ...\n'
        "  ]\n"
        "}\n\n"
        "STRICT RULES:\n"
        "- Do NOT copy any sentence from the textbook content.\n"
        "- Every question must be originally phrased.\n"
        "- Stay strictly within the listed topics.\n"
        "- Ensure sum of marks of all questions equals the total marks.\n"
        "- At most 5 questions in the entire paper should have needs_diagram=true.\n"
        "- No prose outside the JSON.\n\n"
        f"=== TEXTBOOK CONTEXT (style & scope only, DO NOT COPY) ===\n{context_excerpt}\n=== END ==="
    )


QPAPER_EXTRACT_SYSTEM = (
    "You extract structured questions from existing question paper PDFs. "
    "You output strict JSON only. You never invent questions not in the source."
)


def qpaper_extract_prompt(text_excerpt: str) -> str:
    return (
        "Extract every question you can find in the following question-paper text. "
        "For each question, return its full text, your best guess of marks (integer, "
        "default 2), type (one of information|concept|application), and difficulty "
        "(easy|medium|hard).\n\n"
        "Return ONLY strict JSON:\n"
        "{\n"
        '  "subject": "best guess of subject or empty",\n'
        '  "class_name": "best guess of class or empty",\n'
        '  "questions": [ { "question": "...", "marks": 2, "type": "concept", "difficulty": "medium" } ]\n'
        "}\n\n"
        f"=== PAPER TEXT ===\n{text_excerpt}\n=== END ==="
    )


SOLUTION_SYSTEM = (
    "You are an expert teacher writing the answer key for an exam paper. "
    "Your answers are accurate, academically rigorous, and written in the "
    "style a teacher would use to verify a student's response. You follow "
    "strict differentiation by question type:\n"
    "- information: a concise final answer only (1 sentence, or a key term / "
    "definition / value).\n"
    "- concept: a short explanation (2-4 sentences) covering the key reasoning.\n"
    "- application: a complete step-by-step worked solution, including the "
    "method, intermediate steps, formulas used, and the final boxed answer."
)


def solution_prompt(
    subject: str,
    klass: str,
    context_excerpt: str,
    questions_payload: list,
    feedback_hints: str = "",
) -> str:
    """Build a prompt that asks the LLM to produce a mirrored answer array.

    questions_payload is a list of dicts like:
       { "id": "...", "question": "...", "type": "concept", "marks": 3 }
    """
    feedback_block = ""
    if feedback_hints:
        feedback_block = (
            "\n=== TEACHER PREFERENCES FOR SOLUTIONS (learned from past edits) ===\n"
            f"{feedback_hints}\n=== END ===\n\n"
        )
    return (
        f"Write the answer key for an exam paper for Class {klass} - {subject}.\n\n"
        "DEPTH PER TYPE (mandatory):\n"
        "- information: one concise sentence (final answer / key fact).\n"
        "- concept: 2-4 sentence explanation.\n"
        "- application: step-by-step worked solution, formulas, final answer.\n\n"
        "FORMAT:\n"
        "- For step-by-step answers, use plain text with numbered steps (1., 2., 3.).\n"
        "- Use 'Final Answer:' prefix before the concluding value for application questions.\n"
        "- No markdown headings or bold, but you may use bullet points ('- ') inside steps.\n"
        "- Each answer must directly address the specific question.\n\n"
        f"{feedback_block}"
        "Return ONLY strict JSON of the form:\n"
        "{\n"
        '  "answers": [ { "question_id": "...", "answer": "..." } ]\n'
        "}\n\n"
        "The answers array MUST contain exactly one entry per question in the input, "
        "matched by question_id. Do not invent question_ids not in the input.\n\n"
        f"=== TEXTBOOK CONTEXT (style & scope reference) ===\n{context_excerpt[:6000]}\n=== END ===\n\n"
        f"=== QUESTIONS (answer each) ===\n{_render_questions(questions_payload)}\n=== END ==="
    )


def _render_questions(questions: list) -> str:
    lines = []
    for q in questions:
        lines.append(
            f"[{q['id']}] type={q.get('type','concept')} marks={q.get('marks',2)}\n"
            f"{q.get('question','')}"
        )
    return "\n\n".join(lines)
