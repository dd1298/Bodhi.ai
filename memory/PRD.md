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

## What's Implemented — 2026-05-06 (Markdown leak fix in PDFs)
- **Stripped LLM markdown from PDF output**: LLM was emitting `**Q1.**`, `**1.**`, `**(i)**` (markdown bold) which leaked into the PDF as literal asterisks. Added `_markdown_to_reportlab` preprocessor in `pdf_utils.py`:
  - `**bold**` → `<b>bold</b>` (renders bold instead of asterisks)
  - `*italic*` → `<i>italic</i>`
  - Backticks / `#` headings stripped
  - Leading `Q1.` / `**Q1.**` / `1.` prefixes stripped (renderer adds its own numbering, was producing duplicates like `Q1. Q1.`)
- **Updated `qgen_prompt`** with explicit "do NOT use markdown formatting" rule + "do NOT prefix questions with 'Q1.'" rule so future generations are clean at the source.
- **Verified** by re-rendering the user's reported "Physics ICSE class 10 paper" PDF: markdown asterisks gone, math (`5 N·m`, `45°`, `kg m s⁻¹`, `9.8 m/s²`) all render correctly via the existing matplotlib LaTeX→PNG pipeline. The "blank MCQ options" the AI image analyzer reported earlier were a false positive — those are inline math PNG images that `pdftotext` can't see, but they ARE present and rendering correctly.

## What's Implemented — 2026-05-06 (LLM resilience + Retry button)
- **Smart retry layer** in `llm_adapter.py`:
  - Disabled the OpenAI SDK's slow internal retries (which caused 60s+ stalls per attempt) by passing `num_retries=0` via LiteLLM and wrapping each call in `asyncio.wait_for(timeout=75s)` so transient 502s fail fast.
  - Added classified retries: 3 attempts per provider with 2s/4s/8s backoff, but ONLY on transient errors (502/503/504/timeout/rate-limit). Auth/budget/malformed errors fail fast and we move to the fallback Claude provider.
  - Result: a single failed call now resolves in ≤75s instead of stalling the worker for 12+ minutes.
- **Retry generation button** on the failed-paper page (`PaperView.jsx`):
  - New `POST /api/papers/{id}/regenerate` endpoint reuses the paper's stored topics, blueprint, format mix, and custom instructions; resets status to `pending` and re-kicks the background generation task.
  - UI detects transient-looking error messages (502/timeout/gateway/overloaded) and shows a friendly "upstream LLM gateway is having a hiccup" hint with the **Retry generation** button.
  - Verified: a paper that failed with a 502 was successfully regenerated in <30s after the retry layer was in place.

## What's Implemented — 2026-05-06 (Backend refactor + Blueprint regression)
- **Backend modularised**: `server.py` reduced from **1798 → 1229 lines** (32% smaller). New modules:
  - `/app/backend/deps.py` (39 lines) — shared `app`, `api_router`, `db`, `client`, `logger`, `utcnow_iso`, `require_admin`. Loads `.env` so JWT/LLM/storage keys are available before any other module imports.
  - `/app/backend/workers.py` (435 lines) — all background LLM jobs: `load_paper_feedback_hints`, `load_solution_feedback`, `generate_diagrams_for_paper`, `generate_diagrams_background`, `generate_paper_background`, `build_solution_for_paper`, `generate_solution_background`. (Previously `_`-prefixed locals in server.py.)
  - `/app/backend/admin_routes.py` (128 lines) — all 5 `/api/admin/*` endpoints, registered via side-effect import.
- `server.py` now imports `from deps` first (to load `.env`), then auth, then workers; admin routes are pulled in via `import admin_routes` at the bottom.
- **End-to-end verified post-refactor**: admin auth + all 5 admin endpoints (200 admin / 403 teacher), share toggle round-trip, ICSE blueprint generation produced exact 25-question Section A (40m) + 6-question Section B (10m each, "Attempt any FOUR of SIX") and a 850 KB PDF with **zero red pixels on every page**.

## What's Implemented — 2026-05-06 (Paper Blueprint + spell-check fix)
- **Paper Blueprint** (free-form textarea on New Paper page, optional). When set, the AI **overrides** the Bloom-based Section A/B/C split and reproduces the user's blueprint verbatim — section titles, marks per section, internal-choice rules ("attempt any 4 of 6"), per-question formats, sub-parts. Two preset buttons: **Use ICSE Class 10 (80m/2h)** and **Use CBSE Class 10 (80m/3h)**. Stored on paper doc as `section_blueprint` and threaded through `qgen_prompt` as a HIGHEST-PRIORITY block. Verified end-to-end: ICSE blueprint produced 25 questions in Section A (15 MCQ + 6 fill + 4 SA = 40m) and 6 alternatives × 10m in Section B with the exact title `"Section B (40 marks) — Attempt any FOUR of the following SIX questions"`.
- **Spell-check disabled** (`spellCheck={false}`) on all editable inputs across PaperView (title / instructions / question text) + SolutionView (answer textarea) + NewPaper (blueprint + custom instructions). Browser was drawing red squiggly underlines under physics terms (`kgf`, `mitochondrion`) and unit symbols, which the user mistook for stray red marks in the paper — actual PDF has zero red pixels (verified at pixel level).

## What's Implemented — 2026-05-06 (P1 Admin Dashboard)
- **Seeded admin** `admin@bodhi.ai` / `admin123` (idempotent on backend startup; documented in `/app/memory/test_credentials.md`).
- **Shared library**: `is_shared` flag on textbook docs; admin can toggle via `PATCH /api/admin/textbooks/{id}/share?is_shared=…`. Shared books appear in every teacher's `/api/textbooks` list with `is_owned=false`, are read-only on the Textbooks page, and can be used as sources in paper generation. Generate / get-textbook endpoints now allow access to shared books. Teachers cannot self-share at upload time (only admin role honors `?is_shared=true`).
- **Admin endpoints (all 403 for non-admin)**: `/api/admin/overview` (counts), `/api/admin/users` (with textbook+paper counts, no password_hash leak), `/api/admin/textbooks` (with owner_email + is_shared), `/api/admin/papers` (with owner_email), share toggle.
- **Admin Console (`/app/frontend/src/pages/Admin.jsx`)** at `/admin` (gated by new `AdminRoute`): 5 stat cards, 5 tabs — Shared Library / All Textbooks / All Papers / Teachers / Bulk Upload. Bulk Upload supports drag-multi-PDF, queue progress, and an "auto-add to shared library" checkbox.
- **Header**: `Admin` nav link only visible when `user.role === "admin"`.
- **Verified**: testing_agent_v3_fork iteration_4 — 18/18 backend tests + full frontend smoke green; zero issues.

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
