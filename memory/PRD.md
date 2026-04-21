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
