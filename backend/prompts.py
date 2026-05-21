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
    section_blueprint: str = "",
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

    has_blueprint = bool(section_blueprint and section_blueprint.strip())
    has_custom = bool(custom_instructions and custom_instructions.strip())
    # When EITHER a blueprint or free-form custom instructions are given,
    # the user-supplied prompt takes precedence over the slider-based
    # Question Distribution and Format Mix. The teacher is expected to
    # describe those inside their prompt/blueprint if they care about them.
    has_override = has_blueprint or has_custom

    # Optional question-format mix (MCQ / Short Answer / Long Answer / etc).
    format_block = ""
    if format_distribution and not has_override:
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
                "  - mcq: do NOT inline options inside the 'question' text. Instead "
                "emit a separate 'options' array of EXACTLY 4 plain-text choices and a "
                "0-indexed 'correct_option' integer pointing to the right one. Example: "
                '{"format":"mcq","question":"What is the SI unit of force?",'
                '"options":["Newton","Pascal","Joule","Watt"],"correct_option":0}.\n'
                "  - short_answer: 2-3 sentence answer expected.\n"
                "  - long_answer: detailed multi-paragraph answer expected.\n"
                "  - fill_blank: include one or more '_____' blanks in the question.\n"
                "  - true_false: end with 'True or False?'\n"
                "  - For any custom format label, follow the spirit of the label "
                "(e.g., 'case_study' → present a short scenario then ask).\n\n"
            )

    custom_block = ""
    if has_custom:
        custom_block = (
            "TEACHER'S ADDITIONAL INSTRUCTIONS (HIGHEST PRIORITY — these "
            "override the default question-type and format defaults. The "
            "teacher will usually describe their desired section / type / "
            "format mix inside this block; honour it strictly):\n"
            f"{custom_instructions.strip()}\n\n"
        )

    blueprint_block = ""
    if has_blueprint:
        blueprint_block = (
            "PAPER BLUEPRINT (HIGHEST PRIORITY — overrides any default section / type "
            "split). Reproduce sections, question counts, marks, internal-choice rules, "
            "and per-question formats EXACTLY as described below. Use the section "
            "TITLES verbatim as the LLM 'sections[].title' values. If the blueprint "
            "specifies internal choice (e.g. 'attempt any 4 of 6'), generate ALL the "
            "alternatives shown (e.g. 6 questions for a 4-of-6 section) and reflect the "
            "rule in the section's title (e.g. 'Section B (40 Marks) — Attempt any "
            "FOUR of the following SIX questions').\n\n"
            f"{section_blueprint.strip()}\n\n"
        )

    # Default Bloom-based section split — only used when neither blueprint nor
    # custom_instructions are given. The teacher's prompt is expected to
    # describe their preferred type/marks distribution.
    default_section_block = "" if has_override else (
        f"Target question counts: information={info_n}, concept={concept_n}, application={app_n}.\n\n"
        f"Question type definitions:\n{guide}\n\n"
    )
    marks_rule = (
        "" if has_override else
        "Marks allocation: assign 1-2 marks for information, 3-4 for concept, 5-6 for application, "
        "ensuring the sum equals the total marks as closely as possible.\n\n"
    )

    return (
        f"Generate an ORIGINAL question paper for Class {klass} - {subject}.\n"
        f"Topics to cover (with weightage — heavier topics get more questions):\n"
        f"{topics_block}\n\n"
        f"Overall difficulty: {difficulty}\n"
        f"Total marks: {total_marks}, Duration: {duration} minutes.\n\n"
        f"{blueprint_block}"
        f"{default_section_block}"
        f"{format_block}"
        f"{marks_rule}"
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
        '          "difficulty": "easy|medium|hard", "marks": 1, "needs_diagram": false,\n'
        '          "options": ["A","B","C","D"], "correct_option": 0 }\n'
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
        "- For format='mcq', 'options' MUST be an array of EXACTLY 4 plain strings, and 'correct_option' MUST be one of 0,1,2,3 pointing to the correct entry. Omit these fields for non-MCQ questions.\n"
        "- Ensure sum of marks of all questions equals the total marks.\n"
        "- At most 5 questions in the entire paper should have needs_diagram=true.\n"
        "- Do NOT use markdown formatting in any field. No '**bold**', no '*italic*', "
        "no '#' headings, no backticks, no bullet '-' or '*' markers at the start of "
        "lines. Use plain prose. Question numbering is added by the renderer; do NOT "
        "prefix questions with 'Q1.', '1.', '(i)' or similar yourself.\n"
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
        "The text was extracted from a PDF (often via OCR), so it may include "
        "noisy markers like 'Question Number : N', 'Question Id : XXX', "
        "'Question Type : MCQ', 'Options :' and option numeric IDs like '6911215.' "
        "— IGNORE these wrapper lines and only capture the actual question prose. "
        "OCR may also produce minor character glitches in math (e.g. 'a, B €' for "
        "'α, β ∈', '—' for '−'); reconstruct the cleanest plausible question text "
        "without inventing content.\n\n"
        "For each question, return its full text, your best guess of marks (integer, "
        "default 2), type (one of information|concept|application), difficulty "
        "(easy|medium|hard), and 'topic' (a short 2-5 word topic label inferred "
        "from the question content — e.g. 'Newton's Laws', 'Quadratic Equations').\n\n"
        "Return ONLY strict JSON:\n"
        "{\n"
        '  "subject": "best guess of subject or empty",\n'
        '  "class_name": "best guess of class or empty",\n'
        '  "questions": [ { "question": "...", "marks": 2, "type": "concept", '
        '"difficulty": "medium", "topic": "Topic name" } ]\n'
        "}\n\n"
        f"=== PAPER TEXT ===\n{text_excerpt}\n=== END ==="
    )


COMPETITIVE_QGEN_SYSTEM = (
    "You design ORIGINAL practice questions for competitive exams. You are given "
    "anchor samples retrieved from past papers of the SAME exam — use them ONLY "
    "to calibrate style, depth and difficulty (Easy/Medium/Hard). Never copy."
)


_EXAM_SYSTEM_OVERLAYS = {
    "JEE_MAINS": (
        "You are setting questions for JEE Main. Numerical answers must be exact "
        "(2 or 3 significant figures). Use SI units. Apply real JEE Main weightage: "
        "Physics — mechanics/electrodynamics/optics emphasis; Chemistry — physical, "
        "organic name-reactions, inorganic blocks; Mathematics — calculus, "
        "coordinate geometry, algebra. MCQ options must be plausible distractors "
        "based on common student errors (sign flips, factor of 2, unit-swap)."
    ),
    "JEE_ADV": (
        "You are setting questions for JEE Advanced. Demand multi-concept "
        "reasoning, integrated 2-3 step derivations, and unit/dimension awareness. "
        "Use the actual JEE Adv styles: 'single correct', 'one or more correct', "
        "and numerical-answer types when allowed. Avoid trivially memorisable "
        "items. Distractors must reflect plausible but wrong reasoning paths, "
        "not random wrong values."
    ),
    "UPSC": (
        "You are setting questions for the UPSC Civil Services examination. "
        "Use Indian-government and current-affairs context where appropriate. "
        "For GS/Essay prompts, demand structured, analytical, multi-perspective "
        "responses (historical, economic, social, ethical lenses). Avoid yes/no "
        "framing; favour 'critically examine', 'discuss', 'analyse' verbs."
    ),
    "CAT": (
        "You are setting questions for CAT (IIM admissions). For LRDI build a "
        "compact data set or scenario the student must reason over. For VARC "
        "favour passage-based inference and assumption-detection. For QA stay "
        "within high-school arithmetic/algebra/geometry but require multi-step "
        "manipulation. MCQs follow CAT's 4-option format with strong, close "
        "distractors."
    ),
    "NEET": (
        "You are setting questions for NEET (UG). Stay strictly within the "
        "NCERT Class 11-12 Biology / Physics / Chemistry syllabus. Use NCERT-style "
        "diction. For Biology, anchor on classification, physiology, genetics, "
        "ecology and human anatomy. MCQs use the standard 4-option format with "
        "one definitively correct answer."
    ),
}


def competitive_system_for_exam(exam_type: str | None) -> str:
    """Layer the exam-specific overlay onto the base competitive system."""
    base = COMPETITIVE_QGEN_SYSTEM
    overlay = _EXAM_SYSTEM_OVERLAYS.get((exam_type or "").upper())
    return f"{base}\n\n{overlay}" if overlay else base


def competitive_qgen_prompt(
    exam_name: str,
    topics: list[str],
    difficulty: str,
    question_count: int,
    duration: int,
    anchors: list[dict],
    rag_dist: dict,
    format_distribution: dict | None = None,
    custom_instructions: str = "",
    exam_type: str = "GENERIC",
) -> str:
    """RAG-calibrated competitive-exam paper prompt.

    `anchors` is a list of {text, difficulty, topic, marks, _score} retrieved
    from past_questions. `rag_dist` is the easy/medium/hard distribution
    actually observed across the anchors — the prompt hands this to the LLM
    as a calibration anchor for what *real* Easy/Medium/Hard looks like for
    this exam, rather than a generic notion of difficulty."""
    anchor_lines = []
    for i, a in enumerate(anchors[:8]):
        diff = (a.get("difficulty") or "medium").lower()
        tpc = a.get("topic") or ""
        marks = a.get("marks") or ""
        text = (a.get("text") or "").strip().replace("\n", " ")[:280]
        anchor_lines.append(
            f"[{i+1}] difficulty={diff} topic={tpc} marks={marks}\n    {text}"
        )
    anchors_block = "\n".join(anchor_lines) or "(none — no past papers indexed yet)"

    rag_summary = (
        f"Past-paper sample distribution for these topics: "
        f"easy={rag_dist.get('easy',0)}, medium={rag_dist.get('medium',0)}, "
        f"hard={rag_dist.get('hard',0)}.\n"
    )

    format_block = ""
    is_pure_mcq = (
        format_distribution
        and len(format_distribution) == 1
        and (format_distribution.get("mcq") or 0) >= 100
    )
    if format_distribution:
        fmt_lines = []
        for fmt, pct in format_distribution.items():
            if pct <= 0:
                continue
            n = max(1, round(question_count * pct / 100))
            fmt_lines.append(f"- {fmt}: ~{n} ({pct}%)")
        if fmt_lines:
            format_block = (
                "QUESTION FORMAT MIX (mandatory, set 'format' on each question):\n"
                + "\n".join(fmt_lines)
                + "\nFor 'mcq', emit options:[4 strings] and correct_option:0-3 "
                "as SEPARATE JSON fields (NOT inlined into the question text).\n\n"
            )
    if is_pure_mcq:
        format_block += (
            "ABSOLUTE RULE: Every single question MUST be format='mcq' with "
            "EXACTLY 4 options and a correct_option in [0,3]. Do NOT emit any "
            "numerical-answer, short-answer, fill-in-the-blank or true/false "
            "questions. For items that would normally be numerical (e.g. 'find "
            "the value of x'), wrap the numerical answer as one of 4 plausible "
            "MCQ options — the correct value plus 3 distractors derived from "
            "common student errors (off-by-one, sign flip, unit swap, dropped "
            "factor of 2, etc.). Any question lacking 4 options is INVALID.\n\n"
        )

    custom_block = ""
    if custom_instructions.strip():
        custom_block = (
            "TEACHER'S ADDITIONAL INSTRUCTIONS (HIGHEST PRIORITY — override "
            "defaults where they conflict):\n"
            f"{custom_instructions.strip()}\n\n"
        )

    topics_block = "\n".join(f"- {t}" for t in topics)
    return (
        f"Generate an ORIGINAL practice paper for the {exam_name} competitive exam "
        f"(exam_type={exam_type}).\n"
        f"Target difficulty: {difficulty}. Target question count: {question_count}. "
        f"Duration: {duration} minutes.\n\n"
        f"Topics to cover:\n{topics_block}\n\n"
        "DIFFICULTY CALIBRATION (mandatory):\n"
        f"{rag_summary}"
        "Use the anchor samples below as your concrete reference for what "
        "Easy/Medium/Hard looks like FOR THIS EXAM — they came from real past "
        "papers retrieved by topic similarity. Match their depth and style. "
        "If the target difficulty is 'medium', anchor primarily on items "
        "labelled medium; for 'hard' anchor on hard, etc. NEVER copy any "
        "anchor verbatim — produce ORIGINAL questions only.\n\n"
        f"=== RAG ANCHORS ({len(anchor_lines)} items) ===\n{anchors_block}\n=== END ===\n\n"
        f"{format_block}"
        f"{custom_block}"
        "MATH FORMATTING (STRICT): wrap every math expression in '$...$' "
        "(inline) or '$$...$$' (block). Use KaTeX/matplotlib-mathtext "
        "compatible LaTeX. No raw Unicode superscripts, subscripts or '°'.\n\n"
        "Return ONLY strict JSON of the form:\n"
        "{\n"
        '  "instructions": "short instruction line",\n'
        '  "sections": [\n'
        '    { "title": "Section A",\n'
        '      "questions": [\n'
        '        { "question": "...", "topic": "Topic name",\n'
        '          "type": "information|concept|application",\n'
        '          "format": "mcq|short_answer|long_answer|fill_blank|true_false|\\"\\"",\n'
        '          "difficulty": "easy|medium|hard", "marks": 1,\n'
        '          "needs_diagram": false,\n'
        '          "options": ["A","B","C","D"], "correct_option": 0 }\n'
        '      ]\n'
        '    }, ...\n'
        "  ]\n"
        "}\n\n"
        "STRICT RULES:\n"
        "- Originally phrased, never copy anchor wording.\n"
        "- Stay on the listed topics.\n"
        "- For format='mcq', options MUST be 4 plain strings and correct_option in [0,3].\n"
        "- Sum of marks should approximate question_count * average mark-per-question of anchors (default 1 mark each if unsure).\n"
        "- No markdown formatting in any field. No prose outside JSON.\n"
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
