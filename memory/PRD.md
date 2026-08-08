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

## What's Implemented — 2026-08-08 (CamScanner watermark + zero-topics silent failure)
- **Root cause:** User's `sl-arora-class-11-complete.pdf` was a scanned PDF whose text layer contained only `"Scanned by CamScanner"` watermarks repeated across 22 KB. Because that exceeded the 500-char OCR trigger threshold, OCR never fired, the LLM saw only watermark noise, returned zero topics — and the endpoint STILL flipped status to `topics_ready` with an empty array. The user saw "success" but no topics.
- **Fix 1 — expanded watermark strip.** `_strip_boilerplate` now recognises `"Scanned by CamScanner"`, `"Scanned with CamScanner"`, `"CamScanner"`, `"Tap here to remove ads"`, `"cam scanner"` — in addition to the existing `"Downloaded from…"`. Verified: 1154 chars of watermarks collapse to 0 → OCR trigger fires → real content extracted.
- **Fix 2 — extract-topics no longer lies.** When the LLM returns zero topics we now raise **HTTP 422** with detail "The AI couldn't identify any topics…" instead of silently flipping to `topics_ready` with `topics: []`. Status stays as `indexed` so the user can retry.
- **Fix 3 — reindex is now async.** `/api/textbooks/{id}/reindex` returns immediately with `status: ingesting` and runs OCR + chunking in a background task, matching the upload flow. Prevents Cloudflare 502 on large scanned re-ingests. Chunks cap bumped 50 → 120 to keep more spread for topic-extract sampling.
- **Fix 4 — HTTPException passthrough.** Testing agent caught a related bug during verification: the bare `except Exception as e` in `extract_topics` was catching the intentional 422 and re-raising it as 502. Added `except HTTPException: raise` before the generic handler.
- **Verified via `testing_agent` → iteration_10.json**: backend **100%** + frontend **100%**. Live proof: user's `sl-arora-class-11-complete.pdf` re-ingested from 9 watermark chunks → 48 real physics chunks → 8 real topics (Mathematical Tools, Units & Measurements, Kinematic Equations, Vectors, Motion In A Plane, etc.).

## What's Implemented — 2026-08-08 (Extract Topics silent-failure fix)
- **Root cause:** User uploaded a textbook and clicked "Extract Topics" but nothing happened. Three compounding bugs: (1) `poppler-utils` + `tesseract-ocr` binaries were missing on the pod (evicted on re-provisioning; 4th time this session), so scanned PDFs OCR'd to empty text; (2) after the recent async-ingest change, clicking Extract Topics while `status: ingesting` returned a generic 400 with an unhelpful message; (3) frontend didn't distinguish `ingesting` from `indexed` so the button was always active.
- **Fix 1 — OCR binary self-heal.** `server.py` `@app.on_event('startup')` now detects missing `pdftoppm`/`tesseract` and installs them via `apt-get`. Backend logs `OCR binaries installed successfully` on first boot of a fresh pod. This ends the recurring "OCR silently failing" pattern once and for all.
- **Fix 2 — clear errors on extract-topics.** Endpoint now returns **409** with "Textbook is still being processed (OCR + chunking)..." when status is `ingesting`, and **400** with "No indexed text available..." when status is `extraction_failed` or chunks are empty. Both messages tell the user exactly what to do next.
- **Fix 3 — orphan recovery for textbooks.** Startup handler now resets any textbook stuck in `ingesting` from a previous crash to `extraction_failed` with a "restart interrupted" message — matches the existing recovery for orphaned pending papers and solutions.
- **Fix 4 — frontend polls + disables.** `Textbooks.jsx` now polls the list every 5s while any textbook is `ingesting`. The Extract Topics button is disabled during ingest with label "Processing PDF..." and a tooltip explaining why.
- **Verified via `testing_agent` → iteration_9.json**: backend **14/14** pytest passed, frontend **100%** — small PDF upload → status=ingesting → polling flips to indexed → extract-topics returns topics. `extraction_failed` textbook returns clean 400. All other flows (papers, mock tests, competitive) unchanged.

## What's Implemented — 2026-06-27 (Textbook topic-extraction fix for scanned PDFs)
- **Root cause:** User's ICSE Class-10 Chemistry textbook (237-page, 61 MB scanned PDF) was returning only ~1KB of real text from pypdf (the rest was "Downloaded from studiestoday.com" watermarks) and OCR wasn't kicking in. Even when OCR did fire, only the **first 8 chunks** of text were fed to the topic-extract LLM call, missing chapters 4-13. The topic cap of 12 also clipped real chapters off the result.
- **Fix 1 — OCR page sampling.** `pdf_utils._ocr_pdf` now samples evenly across the whole book when total pages > max: head pages (ToC), evenly-spaced middle pages (chapter intros), tail pages (glossary). Capped at 40 pages so latency stays bounded (~60-110s for a 237-page book). Confirmed 12/12 ICSE chapter titles now appear in the OCR'd text.
- **Fix 2 — async textbook ingestion.** `POST /api/textbooks` now inserts the textbook row in `status: ingesting` and runs `extract_text` inside `asyncio.create_task` + `asyncio.to_thread`. UI returns instantly, status flows `ingesting → indexed` automatically (frontend already polls). Previously the 60-120s OCR call blocked the uvicorn worker and tripped the Cloudflare proxy 502.
- **Fix 3 — broad chunk sampling for topic extract.** `POST /api/textbooks/{id}/extract-topics` now samples chunks evenly across the textbook (head + N evenly-spaced) instead of only `chunks[:8]`. Excerpt budget bumped 12k → 14k chars. Chunks-on-disk cap raised 50 → 120 to keep enough spread for sampling.
- **Fix 4 — bigger topic ceiling.** Topic-extract prompt now asks for "8 to 18 top-level topics" (was 4-10) and code cap raised 12 → 20. Prompt explicitly tells the LLM to use ToC chapter lists as the authoritative topic source when present.
- **Verified end-to-end** on the user's actual chemistry PDF: **17 topics extracted** (every chapter from Periodic Table → Organic Chemistry plus extras like Practical Work, Glossary, Test Papers, Model Papers), each with 1-6 subtopics. Previously the same PDF returned <5 topics. Regression test in `tests/test_ocr_sampling.py` (3/3 pass) locks the OCR page planner.

## What's Implemented — 2026-05-21 (LLM timeout resilience + parallel batches)
- **Root cause:** Users hit "All LLM providers failed: Request timed out" on large competitive papers. The LiteLLM internal timeout was 60s but real JEE/NEET batches with full math + 4 distractors per Q + RAG anchors regularly took 90-130s. Every attempt hit the 60s wall, every retry the same, fallback provider too — so 6+ minutes per batch of pure timeout chains, with the final paper marked `failed`.
- **Fix 1 — bigger LLM timeouts.** `llm_adapter.chat_complete` now passes `timeout=150 / request_timeout=150` to `LlmChat.with_params(...)` (was 60s) and the outer asyncio wrapper is 165s (was 75s). Aligned so the wrapper kicks in after LiteLLM had its chance, not before.
- **Fix 2 — smaller batch sizes.** `exam_formats.py` batch_size dropped across the board: JEE Mains 30→20, JEE Adv 27→18, CAT 33→22, UPSC 34→20, NEET 30→20. Each LLM call now has less to produce so it fits comfortably under the new timeout.
- **Fix 3 — parallel batches.** `_generate_competitive_paper` now runs batches concurrently with `asyncio.gather` + a 3-way semaphore. JEE Mains 75q dropped from ~95s sequential to ~44s parallel; NEET 180q should drop from ~10min to ~3-4min worst case.
- **Fix 4 — clearer error.** When every batch times out, the persisted `generation_error` now reads: "All LLM providers timed out — the upstream gateway is slow right now. Click 'Retry generation' below; usually clears within a few minutes."
- **Verified live:** JEE Mains 75q completed in 44s, 100% of questions with 4 options, no truncation, no failed batches.

## What's Implemented — 2026-05-21 (PaperView MCQ-options rendering)
- **Root cause:** Although the underlying JEE Mains data correctly had 4 options + correct_option on every question, `PaperView.jsx` only rendered the question text + marks; the options array was never displayed. The PDF download already rendered options (added earlier this session), but on-screen the paper looked option-less.
- **Fix:** Added MCQ option rendering to `PaperView.jsx` in both view and edit modes. In view mode, options appear under the question on indented `(a)/(b)/(c)/(d)` lines with KaTeX math, the correct option highlighted in green with a screen-only "Correct" badge (`no-print` class so it's stripped from print/PDF). In edit mode, each option becomes an editable text input with a clickable `(a/b/c/d)` button that toggles which option is the correct answer; the change persists through the existing `update_paper` endpoint (since `SectionUpdate.questions: List[dict]` already accepts arbitrary keys).
- **Verified:** Live screenshot of the JEE Mains 100% MCQ paper shows Q1 with options 1.0s / 2.0s / 1.5s / 2.5s and 2.0s flagged "Correct". PDF text extraction confirms each downloaded question carries its 4 options without the "Correct" badge — exactly the NTA paper format.

## What's Implemented — 2026-05-21 (All competitive papers now 4-option MCQ)
- **Root cause:** User reported "JEE Mains pattern should have 4 options for each question" — but the locked JEE Mains format was 80% MCQ + 20% numerical (matching NTA's real exam), so 20% of generated questions intentionally had no options. Same issue applied to JEE Adv (30% numerical) and CAT (25% TITA).
- **Fix:** Locked formats for `JEE_MAINS`, `JEE_ADV`, and `CAT` switched to `{mcq: 100}` in `exam_formats.py`. Practice papers in Bodhi.ai now use 100% 4-option MCQ across every preset (UPSC and NEET were already 100% MCQ). Numerical-style problems are wrapped as MCQs with 4 plausible distractors (correct value + 3 common-error variants).
- **Prompt hardening:** `competitive_qgen_prompt` detects 100%-MCQ format distribution and appends an "ABSOLUTE RULE" block instructing the LLM to never emit numerical/short-answer/fill-blank/true-false, and to wrap numerical answers as 4 plausible MCQ options.
- **Defensive normalisation:** New `strict_mcq=True` mode in `_normalise_questions` (used whenever the locked format is 100% MCQ) drops any item that escapes the prompt without 4 valid options + valid `correct_option`. Batching produces enough surplus questions to absorb the occasional reject.
- **Verified end-to-end:** Fresh JEE Mains generation produced **75/75 MCQs, all 4 options, all valid correct_option** in ~70s. Visual confirmation: numerical answers ("$1.0\\,s$", "$2.0\\,s$", …) wrapped as MCQ options.
- **Tests:** `tests/test_strict_mcq.py` 2/2 pass — strict mode drops numerical/short/3-option/out-of-range items, lenient mode (GENERIC exams) keeps them.

## What's Implemented — 2026-05-21 (NTA past-paper OCR fix)
- **Root cause:** NTA's JEE Mains 2026 result PDFs (and similar exams) render each question stem as a page image while leaving only metadata wrappers in the text layer ("Question Number :", "Question Id :", "Options :", numeric option IDs like 6911215.). pypdf's `extract_text` returned ~22KB of *metadata* — comfortably over the old 500-char threshold for triggering OCR — so OCR never ran and the LLM extraction received only header noise and produced 0 questions.
- **Fix 1 — smarter OCR trigger.** New `_looks_like_metadata_only()` heuristic in `pdf_utils.py`: counts `Question Number :` markers and measures the average *real prose* (after stripping known NTA header fields and numeric option IDs) between consecutive markers. <80 chars/question on average → text layer is metadata only → force OCR fallback. Threshold tuned and locked behind 3 regression tests in `tests/test_ocr_heuristic.py` (NTA pattern → True; real prose → False; <5 markers → False).
- **Fix 2 — install OCR dependencies.** Verified `poppler-utils` + `tesseract-ocr` are present on the runtime image; they were missing on this pod and `pdf2image.convert_from_bytes` was silently returning `[]`. (If the pod is reprovisioned again, `apt-get install -y poppler-utils tesseract-ocr` restores it.)
- **Fix 3 — OCR-aware LLM prompt.** `qpaper_extract_prompt()` now tells the LLM to ignore NTA metadata wrapper lines and reconstruct math from OCR glitches (e.g. `a, B €` → `α, β ∈`) without inventing content.
- **Verified end-to-end** on the actual user PDF: 67 of 75 NTA questions extracted in ~70s, properly tagged with topics (Quadratic Equation Roots, Complex Numbers, Differential Equations…) and difficulty (42 medium / 23 hard / 2 easy — matches JEE Mains profile). LaTeX math reconstructed cleanly (`\(\alpha,\beta\in\mathbb{R}\)`).

## What's Implemented — 2026-05-21 (Locked official competitive-exam formats + batching)
- **Locked official formats** (`exam_formats.EXAM_FORMATS`): JEE_MAINS 75q/180min/300m (80% MCQ + 20% numerical), JEE_ADV 54q/180min/180m (70% MCQ + 30% numerical), CAT 66q/120min/198m (75% MCQ + 25% short), UPSC 100q/120min/200m (100% MCQ), NEET 180q/200min/720m (100% MCQ). Backend overrides any client-sent `question_count`/`duration_minutes`/`format_distribution`/`total_marks` when `exam_type` is a preset; GENERIC still respects client values.
- **Batched generation**: for papers larger than `batch_size` (30 for JEE_MAINS, 27 for JEE_ADV, 33 for CAT, 34 for UPSC, 30 for NEET), `_generate_competitive_paper` issues sequential LLM calls per batch and merges into a single section. Per-batch failures are tolerated (other batches still count); only an empty all-batches-zero outcome marks the paper failed. Verified live: JEE_MAINS produced 75 questions across 3 batches in ~95s.
- **New endpoint** `GET /api/competitive-exams/formats` returns the locked-format catalogue (auth-required) so the UI can drive both the locked-info card and the validation.
- **Frontend** — `/competitive-exams/:id` for a preset exam shows a new "Official format (locked)" card with question_count/duration/marks tiles + the NTA/UPSC/IIM notes, and HIDES the question-count + duration inputs. Difficulty + custom-instructions inputs remain. Toast on generate notes the expected time (1-2 min for batched runs). GENERIC exams keep the editable inputs as before.
- **Verified via testing_agent_v3_fork → iteration_8.json**: backend 4/5 functional (only failure was the unauth /formats endpoint, now fixed), frontend 100% — locked-card renders on preset, inputs hidden, GENERIC still shows inputs.

## What's Implemented — 2026-05-21 (Truncation fix: max_tokens + JSON salvage)
- **Root cause**: LLM hit default ~4k output token budget mid-stream on long MCQ papers with LaTeX math; response was cut off and `parse_json_response` failed with the user-visible "Could not parse JSON from: { …Section A - Information Bas". Both teacher AND competitive paper generation were affected.
- **Fix 1 — bigger output budget**: `chat_complete()` now passes `max_tokens=16384` via `LlmChat.with_params(...)` for every provider/attempt. Modern OpenAI/Claude/Gemini models can emit far more than 4k tokens; raising the cap is safe (no extra cost when the model returns less).
- **Fix 2 — graceful salvage**: `parse_json_response()` now extracts a top-level `"instructions"` plus walks every `"questions": [` block in the response (using a brace-depth state machine that respects strings/escapes) and returns whatever complete question objects survived. Sets `_recovered_from_truncation=True` which workers persist to the paper. UI shows a yellow "Partial recovery" banner on the paper page with a hint to use "Retry generation" for a full re-run.
- **Verified**: 5/5 pytest in `tests/test_json_salvage.py` (well-formed, mid-array truncation, no-salvageable-content failure, solution `answers` salvage). Live regression: 20-MCQ JEE Mains paper generated to completion in ~35s with `recovered=False` — confirms the 16k cap prevents truncation entirely on real workloads.

## What's Implemented — 2026-05-20 (Phase 2.5: Per-exam model routing + presets)
- **5 quick-start presets** on `/competitive-exams` — JEE Mains, JEE Advanced, CAT, UPSC, NEET. One click creates an exam library pre-tuned to that exam's stack: appropriate exam-type code stored, exam-specific system-prompt overlay used, and a dedicated model chain used at generation time.
- **Per-exam model routing** (`llm_adapter.EXAM_PROVIDER_CHAINS` + `chain_for_exam()` + `chat_complete(provider_chain=...)` override): JEE_MAINS → `openai/gpt-5.1` → fallback gpt-5.2 → claude-sonnet-4-5; JEE_ADV → `openai/o3-pro` → gpt-5.1 → claude-opus-4-6; UPSC → `anthropic/claude-opus-4-6` → claude-sonnet-4-5 → gpt-5.2; CAT → `gemini/gemini-3.1-pro-preview` → gpt-5.2 → claude-sonnet-4-5; NEET → `anthropic/claude-sonnet-4-5` → gemini-2.5-pro → gpt-5.2. Verified live on JEE_MAINS run via backend logs (`LLM success with openai/gpt-5.1`). Note: DeepSeek R1 and Aryabhata 1.0 are NOT available via the Emergent universal key — flagged for future when user provides separate keys.
- **Exam-specific system overlays** (`prompts._EXAM_SYSTEM_OVERLAYS` + `competitive_system_for_exam()`) layer concrete style guidance on top of the base competitive system prompt: JEE distractor patterns, UPSC "discuss/critically examine" verbs, CAT LRDI/VARC framing, NEET NCERT-only anchor.
- **Backend tolerance** — `competitive_exams` docs missing `exam_type` are read back as `GENERIC` (covers pre-migration rows).
- **UI** — type badge on exam list cards + detail page (testids `exam-type-{CODE}` / `detail-exam-type-{CODE}`). New Exam form has a 6-option `exam_type` select.
- **Verified via testing_agent_v3_fork → iteration_7.json**: backend 13/14 pre-fix → 14/14 after the legacy-default patch, frontend 100% E2E (all 5 preset testids, select options, library/detail badges). JEE_MAINS end-to-end on real LLM confirmed.

## What's Implemented — 2026-05-17 (Phase 2: Competitive Exams + RAG, Phase 3: 600-dpi math)
- **Competitive Exam library** (separate from textbook-bound papers). New collections `competitive_exams`, `past_papers`, `past_questions`. Teachers/admins create an exam (e.g. "JEE Main 2026"), upload past-paper PDFs that get ingested in the background (LLM extracts each question with `topic`+`difficulty` tags, persisted to `past_questions`). Teachers can delete past papers, which also wipes the indexed questions and decrements counters.
- **RAG retrieval (`/app/backend/rag.py`)** — sklearn TF-IDF (with bigrams + english stopwords) over `topic + " . " + text` corpus, cosine similarity, top-K with `_score` rounded to 3 dp. Falls back to lexical-overlap on tiny corpora. No model download, no torch — pure Python + sklearn. Architecture is swap-ready for FAISS + real embeddings (sentence-transformers / OpenAI) when scale demands.
- **RAG-calibrated paper generation** — new `competitive_qgen_prompt()` packs the retrieved anchors (text + difficulty + topic + marks) into the prompt as a concrete reference for what *that specific exam's* Easy/Medium/Hard really looks like, plus an aggregate distribution summary. Generated papers carry `is_competitive: true`, `competitive_exam_id`, `rag_anchors_used`, `rag_difficulty_distribution`.
- **Frontend** — new `Competitive` nav item, `/competitive-exams` library page with inline "New Exam" form, `/competitive-exams/:id` detail page with upload form, indexed-paper list (with status pills + delete), topic pill picker showing question counts, difficulty/count/duration controls, custom-prompt textarea, "Preview RAG anchors" CTA (renders an inline card with retrieved anchors and difficulty distribution), and Generate that kicks off the LLM and navigates to the standard `/papers/:id` view.
- **Phase 3 — PDF math sharpness**: bumped matplotlib mathtext PNG rendering from 220 dpi → 600 dpi in `pdf_utils._render_math_png`. Visual verification via `analyze_file_tool` returned 5/5 sharpness across inline (F=ma), integrals, E=mc², fractions, and 90°. New `_render_math_svg()` helper added as a future hook for true vector block-math (ReportLab inline `<img>` only accepts raster, so inline stays PNG).
- **Verified via testing_agent_v3_fork → iteration_6.json**: backend 15/15 + teacher regression green, frontend full E2E green (nav, list/create exam, upload UI, topic pills, RAG preview, Generate → /papers/:id). All comments were MINOR; cleaned up the 3x RAG-call perf nit and rounded `_score`.

## What's Implemented — 2026-05-17 (Phase 1 Student MVP)
- **Student persona end-to-end.** Register flow now offers `teacher | student | admin`. Backend allows `role=student` on `/api/auth/register`. Frontend Header is role-aware; `/` redirects students to `/student` via `TeacherOrRedirect`; `/student/*` is gated by `StudentRoute`.
- **Mock-test backend** (`/app/backend/student_routes.py`): 7 endpoints under `/api/student/*` for the full lifecycle — list shared textbooks, create mock test (kicks off existing paper-generation worker with `format_distribution={mcq:100}`), fetch test (hides `correct_option` until submitted), start (sets `ends_at`), autosave answers, submit + auto-grade, fetch result. New `mock_tests` collection. Correct-option leakage is prevented in the in-progress state (defense-in-depth — also strips `diagram_description`).
- **Structured MCQs.** `prompts.py` + `workers.py` updated so MCQs emit `options:[4 strings]` and `correct_option:0-3` as separate JSON fields (not inlined). `pdf_utils.render_paper_pdf` now renders MCQ options on indented `(a)/(b)/(c)/(d)` lines for teacher PDFs.
- **MCQ auto-grader** in `student_routes._grade_test`: marks awarded only for matching `selected_option`, with topic-wise breakdown (`obtained/total/correct/count` per topic) and overall percent. Non-MCQ items are counted toward `total` but never awarded — fine because mock tests are 100% MCQ.
- **Exam UI** (`/app/frontend/src/pages/student/MockTestExam.jsx`): server-time-driven countdown (no clock drift), batched autosave every 3s of dirty answers, automatic submit at 0s, question navigator sidebar, KaTeX in question/option rendering. Mobile-responsive grid.
- **Result UI** with overall percent, topic breakdown bars, weak-topic detection (<50%) + one-click practice-drill generation, per-question review with green/red highlighting on correct/picked options.
- **Orphan recovery on startup** (added earlier today) still in place so interrupted mock-test generations also auto-recover.
- Verified via `testing_agent_v3_fork` → iteration_5.json: backend 13/13 pass + teacher regression green (PDF download, admin overview), frontend full E2E green (register/login/redirect/route-guards/new-mock-test/exam/submit/result/practice-drill).

## What's Implemented — 2026-02-15 (PDF math sizing fix)
- `pdf_utils._math_to_paragraph_html` now routes inline + block math through the new `_math_img_tag()` helper that opens each rendered LaTeX PNG with PIL, computes its natural width/height at 220 dpi, caps height at 18pt for stacked expressions, and emits a proportional `<img width=... height=... valign="-1">` tag. Eliminates the "bumpy line / oversized equation" issue users reported in downloaded PDFs. Verified via `/app/backend/tests/test_pdf_math.py` (inline F=ma renders at ~12pt, fraction caps at 18pt, full paper PDF renders without errors, visual analysis confirmed proportional sizing).

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

## What's Implemented — 2026-05-12 (Prompt takes precedence over sliders)
- When the teacher fills **Additional Instructions** OR **Paper Blueprint**, the **Question Distribution** and **Question Format Mix** slider cards are now visually disabled (opacity-50, `pointer-events: none`) and show a yellow **"OVERRIDDEN BY PROMPT"** badge.
- Backend `qgen_prompt` now skips the default Bloom-distribution block, the marks-allocation rule, and the format-mix block when EITHER `custom_instructions` or `section_blueprint` is non-empty. The teacher's prompt block is promoted to **HIGHEST PRIORITY**, so the AI follows their description of types/marks/formats verbatim.
- Frontend validation no longer enforces the 100% slider sums when a prompt is active; the `format_distribution` payload is sent empty in that case so it doesn't compete with the prompt.

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
