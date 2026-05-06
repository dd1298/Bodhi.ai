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
    topics_weighted: list,  # list of {"name": str, "weight": int}
    difficulty: str,
    distribution: dict,
    total_marks: int,
    duration: int,
    context_excerpt: str,
    feedback_hints: str = "",
    format_distribution: dict | None = None,
    custom_instructions: str = "",
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

    # Compute proportional question counts per topic so the LLM has a hard target.
    total_w = sum(max(1, int(t.get("weight", 5))) for t in topics_weighted) or 1
    topic_lines = []
    for t in topics_weighted:
        w = max(1, int(t.get("weight", 5)))
        share = round(target_q * w / total_w)
        topic_lines.append(
            f"- {t['name']}  (weight {w}, target ~{share} question{'s' if share != 1 else ''})"
        )
    topics_block = "\n".join(topic_lines)

    # Optional question-format mix (MCQ / Short Answer / Long Answer / etc).
    format_block = ""
    if format_distribution:
        fmt_lines = []
        for fmt, pct in format_distribution.items():
            if pct <= 0:
                continue
            n = max(1, round(target_q * pct / 100))
            fmt_lines.append(f"- {fmt}: ~{n} question{'s' if n != 1 else ''} ({pct}%)")
        if fmt_lines:
            format_block = (
                "QUESTION FORMAT MIX (mandatory — set each question's 'format' field):\n"
                + "\n".join(fmt_lines)
                + "\nFormat conventions:\n"
                "  - mcq: include 4 options labelled (a)-(d) within the question text "
                "and end with 'Choose the correct option.'\n"
                "  - short_answer: 2-3 sentence answer expected.\n"
                "  - long_answer: detailed multi-paragraph answer expected.\n"
                "  - fill_blank: include one or more '_____' blanks in the question.\n"
                "  - true_false: end with 'True or False?'\n"
                "  - For any custom format label, follow the spirit of the label "
                "(e.g., 'case_study' → present a short scenario then ask).\n\n"
            )

    custom_block = ""
    if custom_instructions:
        custom_block = (
            "TEACHER'S ADDITIONAL INSTRUCTIONS (honour these strictly, "
            "but do NOT let them override the topic/marks/format constraints above):\n"
            f"{custom_instructions.strip()}\n\n"
        )

    return (
        f"Generate an ORIGINAL question paper for Class {klass} - {subject}.\n"
        f"Topics to cover (with weightage — heavier topics get more questions):\n"
        f"{topics_block}\n\n"
        f"Overall difficulty: {difficulty}\n"
        f"Total marks: {total_marks}, Duration: {duration} minutes.\n"
        f"Target question counts: information={info_n}, concept={concept_n}, application={app_n}.\n\n"
        f"Question type definitions:\n{guide}\n\n"
        f"{format_block}"
        "Marks allocation: assign 1-2 marks for information, 3-4 for concept, 5-6 for application, "
        "ensuring the sum equals the total marks as closely as possible.\n\n"
        "TOPIC COVERAGE RULE (mandatory):\n"
        "- Distribute questions across ALL listed topics in proportion to their weights.\n"
        "- No single topic should exceed its target by more than 1 question.\n"
        "- If a topic has weight > 0 it MUST receive at least one question.\n\n"
        f"{custom_block}"
        f"{feedback_block}"
        "MATH FORMATTING (STRICT — critical for PDF rendering):\n"
        "Wrap EVERY mathematical or scientific expression in LaTeX delimiters — "
        "'$...$' for inline, '$$...$$' for block. This includes:\n"
        "  - Units with exponents: write '$\\mathrm{m\\,s^{-1}}$' not 'm s⁻¹'.\n"
        "  - Units with a middle dot: write '$\\mathrm{N\\cdot m}$' not 'N·m' or 'Nm'.\n"
        "  - Any power / subscript: '$v^2$', '$x_1$' (never Unicode ², ₁).\n"
        "  - Degrees: '$60^\\circ$' not '60°'.\n"
        "  - Vectors and fractions: '$\\vec{F}=m\\vec{a}$', '$\\frac{1}{2}mv^2$'.\n"
        "  - Greek letters: '$\\theta$', '$\\omega$'.\n"
        "Use only KaTeX + matplotlib-mathtext compatible commands. "
        "Prefer '\\mathrm{...}' over '\\text{...}'. Do NOT output Unicode "
        "superscripts, subscripts, or the degree symbol directly — always use "
        "LaTeX. For non-math subjects, ignore this.\n\n"
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
        '        { "question": "...", "topic": "Topic name", "type": "information",\n'
        '          "format": "mcq|short_answer|long_answer|fill_blank|true_false|custom_label|\\"\\"",\n'
        '          "difficulty": "easy|medium|hard", "marks": 1, "needs_diagram": false }\n'
        '      ]\n'
        '    }, ...\n'
        "  ]\n"
        "}\n\n"
        "STRICT RULES:\n"
        "- Do NOT copy any sentence from the textbook content.\n"
        "- Every question must be originally phrased.\n"
        "- Stay strictly within the listed topics.\n"
        "- Set 'topic' field on every question to the matching topic name from the list above.\n"
        "- Set 'format' field on every question (use one of the provided format labels, or empty string if none specified).\n"
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
        "- Each answer must directly address the specific question.\n"
        "- Wrap any mathematical expression (integral, vector, fraction, derivative, sum, "
        "Greek letter, matrix, square root, units with exponent, degrees) in LaTeX "
        "delimiters: '$...$' inline or '$$...$$' for display. Use only KaTeX / "
        "matplotlib-mathtext compatible commands. Prefer '\\mathrm{...}' over '\\text{...}'. "
        "Do NOT output raw Unicode superscripts/subscripts or '°' — always use LaTeX "
        "('$9.8\\,\\mathrm{m\\,s^{-2}}$', '$60^\\circ$', '$\\vec{F}=m\\vec{a}$', "
        "'$\\int_0^1 x^2\\, dx = \\tfrac{1}{3}$').\n\n"
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
