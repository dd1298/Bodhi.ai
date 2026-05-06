# PRD — AI Question Paper Generator (QPGEN)

## Original Problem
Build an AI-Powered Question Paper Generator for schools and colleges. Teachers upload textbook PDFs, the system extracts topics/subtopics, and generates **original** question papers with controls for difficulty, duration, total marks and question-type distribution (Information / Concept / Application). Papers are exportable as PDFs. Uses multi-provider LLMs (OpenAI + Anthropic) with fallback.

## Tech Stack (POC)
- Backend: FastAPI + MongoDB (motor)
- Frontend: React + TailwindCSS + shadcn/ui + Phosphor icons
- LLM: OpenAI GPT-5.2 (primary) + Claude Sonnet 4.5 (fallback) via `emergentintegrations` (Emergent Universal Key)
- Storage: Emergent Object Storage (textbook PDFs)
- Auth: JWT custom (Teacher / Admin roles)
- PDF: pypdf (extract) + reportlab (render)

## User Personas
1. **Teacher** — primary user. Uploads PDFs, selects topics, tunes distribution, generates & downloads papers, manages question bank.
2. **Admin** — future expansion. Same abilities + cross-owner access.
3. **Student** — deferred (MVP-lite).

## Core Requirements (static)
- Original question generation (no copying textbook text)
- Topic / subtopic hierarchy auto-extracted from PDF
- Distribution sliders (Info / Concept / Application summing to 100%)
- Difficulty: easy / medium / hard
- Duration + total marks inputs
- Mark questions as important, save to question bank
- Provider fallback chain for LLMs
- PDF export of the generated paper

## What's Implemented — 2026-05-05 (502 timeout fix)
- `/api/papers/generate` now returns instantly (~0.2s) with `generation_status: "pending"` and runs the LLM call in a `_generate_paper_background` task. Frontend polls and shows a "Generating…" card while pending, a red "Generation failed" card if the LLM ultimately errors. PDF download endpoint returns 409 if status is pending/failed.

## What's Implemented — 2026-04-21 (Enhancements)
- **Editable papers + feedback loop**: PATCH `/papers/{id}` updates meta + sections; every question edit is logged to `paper_edits` and surfaced to the LLM as "teacher preferences" context in subsequent generations
- **Diagrams in questions**: LLM flags `needs_diagram`, backend generates PNGs via Gemini Nano Banana in parallel (max 5 per paper), stored in object storage; served via `/papers/{id}/diagrams/{qid}` and embedded in the PDF via reportlab
- **Upload existing question papers** (teacher + admin): `/qpapers/upload` — PDF parsed via LLM → saved into question bank with `source="uploaded"`; UI card on Question Bank page
- **Answer-key / Solution feature**: `POST /papers/{id}/solution/generate` (on-demand), `PATCH /papers/{id}/solution` (editable with its own `solution_edits` feedback loop), `GET /papers/{id}/solution/pdf` (separate PDF). Answers tuned per question type. Auto `is_stale` flag on paper edit. New `/papers/:id/solution` frontend page.
- **Bulk solution generation**: `POST /papers/solutions/bulk-generate?only_missing=true|only_stale=true` — processes all of a user's papers in one request. Dashboard CTA "Generate solutions for all papers without one".
- **Backend full-suite test pass**: testing_agent_v3 verified ALL endpoints @ 100% success rate (auth, textbooks, papers, solutions, qbank, qpapers, diagrams, PDF downloads, auth enforcement).

## What's Implemented — 2026-02-16
- JWT auth (register/login/me) with bcrypt
- Emergent object storage for PDFs + MongoDB metadata
- Textbook upload → pypdf text extraction → chunked storage
- AI topic extraction endpoint (structured JSON output)
- Paper generation endpoint (sections, type/difficulty/marks per question)
- Mark-important toggle, save to question bank, Q-bank search/filter
- Server-side PDF render via reportlab (download endpoint)
- Swiss / brutalist light-theme UI: Cabinet Grotesk + IBM Plex Sans + JetBrains Mono, blue #002FA7 accents, hard offset shadows
- Pages: Login, Register, Dashboard, Textbooks, New Paper, Paper View, Question Bank
- `data-testid` attributes across interactive elements
- Deployment health check: PASS

## Prioritized Backlog
### P0 (post-POC polish)
- Regenerate a single question (currently only via full paper)
- Validation that no generated question matches textbook content (similarity check)
- Admin dashboard & seed admin flow

## What's Implemented — 2026-05-06 (Bodhi.ai rebrand + custom prompt + format mix)
- **Rebrand QPGEN → Bodhi.ai** (display only — internal code/DB names unchanged): Header, Login, Register pages, browser tab title. Added `.brand-mark` CSS class with relaxed kerning so the lowercase "i.ai" doesn't render as "Lai" under the heavy Cabinet Grotesk display font; `.ai` is rendered in the brand blue.
- **Additional Instructions field** on New Paper: free-text multi-line area whose contents are appended to the LLM prompt as a "TEACHER'S ADDITIONAL INSTRUCTIONS" block (cannot override topic/marks/format constraints).
- **Question Format Mix card**: percentage sliders for MCQ / Short Answer / Long Answer / Fill-in-the-blanks / True-False that must sum to 100% (or set all to 0 to let AI decide). Teachers can add custom format chips like "Case Study" or "Assertion-Reason" via an inline input; chips are removable. Each generated question is now tagged with a `format` field, surfaced as a badge in PaperView and in the PDF tag line.
- Backend: `PaperRequest` extended with `custom_instructions` (str) and `format_distribution` (Dict[str,int]); both stored on the paper doc and woven into `qgen_prompt`. The prompt enforces format conventions (MCQ → 4 options + "Choose the correct option", True/False → end with "True or False?", Fill-in-the-blanks → use `_____`, etc.).

## What's Implemented — 2026-05-05 (502 timeout fix)
- **Unicode-capable PDF font**: registered DejaVuSans (Bold/Oblique) with ReportLab so characters like `·`, `°`, `⁻¹`, `²`, `π`, `θ`, `×`, `≈` render instead of being silently dropped.
- **Instructions line now passes through the LaTeX-to-image pipeline** — previously any `$...$` expression in paper instructions leaked as raw backslash syntax.
- **Diagrams preserve their natural aspect ratio** (via Pillow), bounded by max width/height, no longer squashed into a forced 80×80mm square.
- **Mathtext fallback** now strips backslash commands into readable plain text (e.g., `\vec{F}=m\vec{a}` → `F=ma`) instead of leaking raw LaTeX.
- **LLM prompts hardened**: question generation + solution prompts now explicitly forbid raw Unicode superscripts / degree symbols and require `$\mathrm{m\,s^{-1}}$`, `$60^\circ$`, `$N\cdot m$` style LaTeX. Diagram prompt instructs the model to never duplicate labels (fixes Q10 repeated-caption issue).

## Next Action Items
- Regenerate any previously-broken papers (user verification of the Physics Class 10 paper)
- Multi-textbook selection flow (code already shipped, still pending agent e2e test)
- Admin dashboard for bulk pre-indexed textbooks
- Optional: seed admin account, add "regenerate question" endpoint

### P1
- Pre-indexed school-wide textbook library
- Answer key generation
- Student practice mode (lite)
- Question validation scoring (bonus)

### P2
- Multi-school tenancy
- AI evaluation of student submissions
- Difficulty auto-calibration
- True vector DB (Pinecone/Weaviate) for larger corpora

## Next Action Items
- End-to-end testing
- Optional: seed admin account, add "regenerate question" endpoint, answer-key generation
