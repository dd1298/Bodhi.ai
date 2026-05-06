import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import Header from "@/components/Header";
import { toast } from "sonner";
import {
  Sparkle,
  ArrowRight,
  CheckSquare,
  Square,
  X as XIcon,
  Plus,
} from "@phosphor-icons/react";

const DIFFICULTIES = ["easy", "medium", "hard"];
const DEFAULT_FORMATS = [
  { key: "mcq", label: "MCQ", default: 0 },
  { key: "short_answer", label: "Short Answer", default: 40 },
  { key: "long_answer", label: "Long Answer", default: 40 },
  { key: "fill_blank", label: "Fill in the Blanks", default: 10 },
  { key: "true_false", label: "True / False", default: 10 },
];

export default function NewPaper() {
  const navigate = useNavigate();
  const [textbooks, setTextbooks] = useState([]);
  const [selectedTbIds, setSelectedTbIds] = useState([]); // list of ids
  const [tbDetails, setTbDetails] = useState({}); // { id: { topics, subject, class_name } }
  const [title, setTitle] = useState("");
  const [difficulty, setDifficulty] = useState("medium");
  const [duration, setDuration] = useState(60);
  const [totalMarks, setTotalMarks] = useState(50);
  const [info, setInfo] = useState(40);
  const [concept, setConcept] = useState(40);
  const [selectedTopics, setSelectedTopics] = useState([]); // [{name, weight}]
  const [generating, setGenerating] = useState(false);
  const [extractingId, setExtractingId] = useState(null);
  const [customInstructions, setCustomInstructions] = useState("");
  // Format mix: array of { key, label, value, custom }
  const [formats, setFormats] = useState(
    DEFAULT_FORMATS.map((f) => ({ ...f, value: f.default, custom: false }))
  );
  const [newFormatLabel, setNewFormatLabel] = useState("");

  const application = useMemo(
    () => Math.max(0, 100 - info - concept),
    [info, concept]
  );

  const formatTotal = useMemo(
    () => formats.reduce((sum, f) => sum + Number(f.value || 0), 0),
    [formats]
  );
  const formatActive = useMemo(
    () => formats.some((f) => Number(f.value || 0) > 0),
    [formats]
  );

  useEffect(() => {
    api.get("/textbooks").then((r) => setTextbooks(r.data));
  }, []);

  // Load detail (topics) for every selected textbook not yet in cache.
  useEffect(() => {
    const missing = selectedTbIds.filter((id) => !tbDetails[id]);
    if (missing.length === 0) return;
    Promise.all(
      missing.map((id) => api.get(`/textbooks/${id}`).then((r) => [id, r.data]))
    ).then((pairs) => {
      setTbDetails((curr) => {
        const next = { ...curr };
        for (const [id, detail] of pairs) next[id] = detail;
        return next;
      });
    });
  }, [selectedTbIds]); // eslint-disable-line

  const addTextbook = (id) => {
    if (!id) return;
    if (selectedTbIds.includes(id)) return;
    setSelectedTbIds((curr) => [...curr, id]);
  };

  const removeTextbook = (id) => {
    setSelectedTbIds((curr) => curr.filter((x) => x !== id));
    // Prune topics tied only to this book
    const others = selectedTbIds.filter((x) => x !== id);
    const allowed = new Set();
    for (const other of others) {
      const d = tbDetails[other];
      if (!d) continue;
      (d.topics || []).forEach((t) => {
        allowed.add(t.name);
        (t.subtopics || []).forEach((s) => allowed.add(s));
      });
    }
    setSelectedTopics((curr) => curr.filter((t) => allowed.has(t.name)));
  };

  const toggleTopic = (name) => {
    setSelectedTopics((curr) =>
      curr.find((t) => t.name === name)
        ? curr.filter((t) => t.name !== name)
        : [...curr, { name, weight: 5 }]
    );
  };

  const setTopicWeight = (name, weight) => {
    setSelectedTopics((curr) =>
      curr.map((t) =>
        t.name === name ? { ...t, weight: Math.max(1, Math.min(10, weight)) } : t
      )
    );
  };

  const extractTopicsFor = async (id) => {
    setExtractingId(id);
    try {
      const { data } = await api.post(`/textbooks/${id}/extract-topics`);
      setTbDetails((curr) => ({
        ...curr,
        [id]: { ...(curr[id] || {}), topics: data.topics },
      }));
      toast.success("Topics extracted");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed");
    } finally {
      setExtractingId(null);
    }
  };

  const setFormatValue = (key, v) => {
    setFormats((curr) =>
      curr.map((f) =>
        f.key === key ? { ...f, value: clamp(v, 0, 100) } : f
      )
    );
  };

  const addCustomFormat = () => {
    const label = newFormatLabel.trim();
    if (!label) return;
    const key = label.toLowerCase().replace(/[^a-z0-9]+/g, "_");
    if (formats.some((f) => f.key === key)) {
      toast.error("That format is already in the list");
      return;
    }
    setFormats((curr) => [...curr, { key, label, value: 0, custom: true }]);
    setNewFormatLabel("");
  };

  const removeFormat = (key) => {
    setFormats((curr) => curr.filter((f) => f.key !== key));
  };

  const onGenerate = async (e) => {
    e.preventDefault();
    if (selectedTbIds.length === 0)
      return toast.error("Select at least one textbook");
    if (!title) return toast.error("Title required");
    if (selectedTopics.length === 0)
      return toast.error("Select at least one topic");
    if (info + concept + application !== 100)
      return toast.error("Distribution must sum to 100%");
    if (formatActive && formatTotal !== 100)
      return toast.error(
        "Format mix must sum to 100% (or set all to 0 to let AI decide)"
      );

    // Build format_distribution payload (only non-zero)
    const fmtPayload = {};
    for (const f of formats) {
      const v = Number(f.value || 0);
      if (v > 0) fmtPayload[f.key] = v;
    }

    // Derive subject / class from the first selected book
    const first = tbDetails[selectedTbIds[0]] || {};
    setGenerating(true);
    try {
      const { data } = await api.post("/papers/generate", {
        title,
        subject: first.subject || "",
        class_name: first.class_name || "",
        textbook_ids: selectedTbIds,
        topics: selectedTopics,
        difficulty,
        duration_minutes: Number(duration),
        total_marks: Number(totalMarks),
        distribution: { information: info, concept, application },
        format_distribution: fmtPayload,
        custom_instructions: customInstructions.trim() || null,
      });
      toast.success("Generation started — opening paper…");
      navigate(`/papers/${data.id}`);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Generation failed");
    } finally {
      setGenerating(false);
    }
  };

  const anyTopics = selectedTbIds.some(
    (id) => (tbDetails[id]?.topics || []).length > 0
  );

  return (
    <div className="min-h-screen bg-[#FAFAFA]">
      <Header />
      <main className="max-w-7xl mx-auto p-6 md:p-12" data-testid="new-paper-page">
        <div className="overline text-neutral-500 mb-3">// NEW PAPER</div>
        <h1 className="font-display text-5xl md:text-6xl mb-10">
          Tune the
          <br />
          <span className="text-[#002FA7]">generator.</span>
        </h1>

        <form onSubmit={onGenerate} className="grid grid-cols-1 lg:grid-cols-5 gap-6 md:gap-8">
          {/* Left: Metadata + distribution */}
          <div className="lg:col-span-3 space-y-6">
            <div className="qp-card">
              <div className="overline mb-4">// METADATA</div>
              <div className="mb-4">
                <label className="qp-label">Paper title</label>
                <input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  className="qp-input"
                  placeholder="e.g., Mid-Term Physics Paper"
                  required
                  data-testid="paper-title-input"
                />
              </div>

              <div className="mb-4">
                <label className="qp-label">Textbooks</label>
                <select
                  value=""
                  onChange={(e) => {
                    addTextbook(e.target.value);
                    e.target.value = "";
                  }}
                  className="qp-input"
                  data-testid="paper-textbook-select"
                >
                  <option value="">
                    {selectedTbIds.length > 0
                      ? "+ Add another textbook"
                      : "Select textbook"}
                  </option>
                  {textbooks
                    .filter((t) => !selectedTbIds.includes(t.id))
                    .map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.original_filename} — {t.subject} / Class{" "}
                        {t.class_name}
                      </option>
                    ))}
                </select>
                {selectedTbIds.length > 0 && (
                  <div
                    className="mt-3 flex flex-wrap gap-2"
                    data-testid="selected-textbooks-chips"
                  >
                    {selectedTbIds.map((id) => {
                      const tb = textbooks.find((t) => t.id === id);
                      const label = tb
                        ? `${tb.original_filename.slice(0, 28)}${
                            tb.original_filename.length > 28 ? "…" : ""
                          }`
                        : id.slice(0, 8);
                      return (
                        <span
                          key={id}
                          className="inline-flex items-center gap-1 border-2 border-black bg-white px-2 py-1 text-xs font-mono"
                          data-testid={`textbook-chip-${id}`}
                        >
                          {label}
                          <button
                            type="button"
                            onClick={() => removeTextbook(id)}
                            aria-label="Remove"
                            className="hover:text-[#E63946]"
                            data-testid={`textbook-chip-remove-${id}`}
                          >
                            <XIcon size={12} weight="bold" />
                          </button>
                        </span>
                      );
                    })}
                  </div>
                )}
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="qp-label">Duration (min)</label>
                  <input
                    type="number"
                    min={10}
                    max={300}
                    value={duration}
                    onChange={(e) => setDuration(e.target.value)}
                    className="qp-input"
                    data-testid="paper-duration-input"
                  />
                </div>
                <div>
                  <label className="qp-label">Total marks</label>
                  <input
                    type="number"
                    min={10}
                    max={200}
                    value={totalMarks}
                    onChange={(e) => setTotalMarks(e.target.value)}
                    className="qp-input"
                    data-testid="paper-marks-input"
                  />
                </div>
              </div>

              <div className="mt-4">
                <label className="qp-label">Difficulty</label>
                <div className="grid grid-cols-3 border-2 border-black">
                  {DIFFICULTIES.map((d, i) => (
                    <button
                      key={d}
                      type="button"
                      onClick={() => setDifficulty(d)}
                      data-testid={`difficulty-${d}-button`}
                      className={`py-3 font-bold uppercase tracking-wider text-sm transition-colors ${
                        difficulty === d
                          ? "bg-black text-white"
                          : "bg-white hover:bg-neutral-100"
                      } ${i !== 2 ? "border-r-2 border-black" : ""}`}
                    >
                      {d}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div className="qp-card">
              <div className="flex items-center justify-between mb-4">
                <div className="overline">// QUESTION DISTRIBUTION</div>
                <span
                  className={`qp-badge ${
                    info + concept + application === 100
                      ? "qp-badge-success"
                      : "qp-badge-red"
                  }`}
                  data-testid="distribution-total"
                >
                  {info + concept + application}%
                </span>
              </div>

              <SliderRow
                label="Information / Direct"
                value={info}
                onChange={(v) => setInfo(clamp(v, 0, 100 - concept))}
                color="#002FA7"
                testid="dist-info"
              />
              <SliderRow
                label="Concept"
                value={concept}
                onChange={(v) => setConcept(clamp(v, 0, 100 - info))}
                color="#FFC300"
                testid="dist-concept"
              />
              <SliderRow
                label="Application"
                value={application}
                readOnly
                color="#E63946"
                testid="dist-app"
              />
              <p className="text-xs text-neutral-500 font-mono mt-3">
                Application is auto-adjusted so total stays at 100%.
              </p>
            </div>

            <div className="qp-card" data-testid="format-mix-card">
              <div className="flex items-center justify-between mb-2">
                <div className="overline">// QUESTION FORMAT MIX</div>
                <span
                  className={`qp-badge ${
                    !formatActive
                      ? "qp-badge-success"
                      : formatTotal === 100
                      ? "qp-badge-success"
                      : "qp-badge-red"
                  }`}
                  data-testid="format-total"
                >
                  {formatActive ? `${formatTotal}%` : "AUTO"}
                </span>
              </div>
              <p className="text-xs text-neutral-500 font-mono mb-4">
                MCQ, Short / Long Answer, Fill-in-the-blanks, True / False, or
                add your own. Set all to 0 to let the AI decide.
              </p>

              {formats.map((f) => (
                <div
                  key={f.key}
                  className="mb-3 last:mb-0"
                  data-testid={`format-${f.key}`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <div className="font-bold text-sm uppercase tracking-wider flex items-center gap-2">
                      {f.label}
                      {f.custom && (
                        <button
                          type="button"
                          onClick={() => removeFormat(f.key)}
                          className="text-neutral-400 hover:text-[#E63946]"
                          aria-label="Remove custom format"
                          data-testid={`format-remove-${f.key}`}
                        >
                          <XIcon size={12} weight="bold" />
                        </button>
                      )}
                    </div>
                    <div className="font-mono text-sm font-bold">
                      {f.value}%
                    </div>
                  </div>
                  <div className="relative h-2 bg-neutral-200">
                    <div
                      className="absolute top-0 left-0 h-full bg-black"
                      style={{ width: `${f.value}%` }}
                    />
                  </div>
                  <input
                    type="range"
                    min={0}
                    max={100}
                    value={f.value}
                    onChange={(e) =>
                      setFormatValue(f.key, Number(e.target.value))
                    }
                    className="w-full mt-1"
                    data-testid={`format-${f.key}-slider`}
                  />
                </div>
              ))}

              <div className="mt-4 flex items-center gap-2 border-t-2 border-black pt-3">
                <input
                  type="text"
                  value={newFormatLabel}
                  onChange={(e) => setNewFormatLabel(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      addCustomFormat();
                    }
                  }}
                  placeholder="Custom format (e.g., Case Study)"
                  className="qp-input flex-1"
                  data-testid="custom-format-input"
                />
                <button
                  type="button"
                  onClick={addCustomFormat}
                  className="qp-btn qp-btn-secondary text-xs"
                  data-testid="custom-format-add"
                >
                  <Plus size={14} weight="bold" /> Add
                </button>
              </div>
            </div>

            <div className="qp-card" data-testid="custom-instructions-card">
              <div className="overline mb-2">
                // ADDITIONAL INSTRUCTIONS FOR THE AI
              </div>
              <p className="text-xs text-neutral-500 font-mono mb-3">
                Optional. The AI will honour these on top of topics, marks and
                format above. e.g.&nbsp;
                <span className="text-neutral-700">
                  &ldquo;Make all numerical values whole numbers&rdquo;,
                  &ldquo;Avoid Newton&rsquo;s laws&rdquo;, &ldquo;One question
                  must be assertion-reason&rdquo;.
                </span>
              </p>
              <textarea
                value={customInstructions}
                onChange={(e) => setCustomInstructions(e.target.value)}
                rows={4}
                className="qp-input font-mono text-sm"
                placeholder="Type extra instructions for the question paper engine here..."
                data-testid="custom-instructions-input"
              />
            </div>
          </div>

          {/* Right: Topics + submit */}
          <div className="lg:col-span-2 space-y-6">
            <div className="qp-card">
              <div className="overline mb-4">// TOPICS &amp; WEIGHTS</div>

              {selectedTbIds.length === 0 && (
                <div className="text-sm text-neutral-500">
                  Select one or more textbooks to load topics.
                </div>
              )}

              {selectedTbIds.length > 0 && anyTopics && (
                <p className="text-xs text-neutral-500 font-mono mb-3">
                  Pick topics or subtopics from any book. Heavier weights →
                  more questions from that item.
                </p>
              )}

              <div className="space-y-5 max-h-[520px] overflow-auto pr-1">
                {selectedTbIds.map((bookId) => {
                  const detail = tbDetails[bookId];
                  const tb = textbooks.find((t) => t.id === bookId);
                  const topics = detail?.topics || [];
                  return (
                    <div key={bookId} data-testid={`book-topics-${bookId}`}>
                      <div className="flex items-center justify-between mb-2">
                        <div className="overline text-neutral-500 truncate">
                          {(tb?.original_filename || bookId).slice(0, 40)}
                        </div>
                        <button
                          type="button"
                          onClick={() => extractTopicsFor(bookId)}
                          disabled={extractingId === bookId}
                          className="qp-btn-ghost text-xs uppercase tracking-wider"
                          data-testid={`extract-topics-${bookId}`}
                        >
                          {extractingId === bookId
                            ? "..."
                            : topics.length
                            ? "Re-extract"
                            : "Extract"}
                        </button>
                      </div>

                      {!detail && (
                        <div className="text-xs text-neutral-400">Loading...</div>
                      )}

                      {detail && topics.length === 0 && (
                        <button
                          type="button"
                          onClick={() => extractTopicsFor(bookId)}
                          disabled={extractingId === bookId}
                          className="qp-btn qp-btn-primary w-full text-xs"
                          data-testid={`extract-now-${bookId}`}
                        >
                          <Sparkle size={12} weight="bold" />
                          {extractingId === bookId
                            ? "Extracting..."
                            : "Extract topics"}
                        </button>
                      )}

                      {topics.length > 0 && (
                        <div className="space-y-2">
                          {topics.map((t, i) => {
                            const items = [
                              { name: t.name, isTopic: true },
                              ...((t.subtopics || []).map((s) => ({
                                name: s,
                                isTopic: false,
                              }))),
                            ];
                            return (
                              <div
                                key={i}
                                className="border-2 border-black bg-white"
                                data-testid={`topic-block-${bookId}-${i}`}
                              >
                                {items.map((it, j) => {
                                  const sel = selectedTopics.find(
                                    (s) => s.name === it.name
                                  );
                                  const checked = !!sel;
                                  return (
                                    <div
                                      key={j}
                                      className={`flex items-center gap-2 p-2 ${
                                        j !== items.length - 1
                                          ? "border-b border-neutral-200"
                                          : ""
                                      } ${it.isTopic ? "bg-neutral-50" : "pl-8"}`}
                                      data-testid={`topic-row-${bookId}-${i}-${j}`}
                                    >
                                      <button
                                        type="button"
                                        onClick={() => toggleTopic(it.name)}
                                        className="flex items-center gap-2 flex-1 text-left"
                                        data-testid={`topic-toggle-${bookId}-${i}-${j}`}
                                      >
                                        {checked ? (
                                          <CheckSquare
                                            size={18}
                                            weight="fill"
                                            color="#002FA7"
                                          />
                                        ) : (
                                          <Square size={18} weight="bold" />
                                        )}
                                        <span
                                          className={`text-sm ${
                                            it.isTopic ? "font-bold" : ""
                                          }`}
                                        >
                                          {it.name}
                                        </span>
                                      </button>
                                      {checked && (
                                        <div
                                          className="flex items-center gap-2 shrink-0"
                                          data-testid={`weight-row-${bookId}-${i}-${j}`}
                                        >
                                          <input
                                            type="range"
                                            min={1}
                                            max={10}
                                            value={sel.weight}
                                            onChange={(e) =>
                                              setTopicWeight(
                                                it.name,
                                                Number(e.target.value)
                                              )
                                            }
                                            className="w-20"
                                            data-testid={`weight-slider-${bookId}-${i}-${j}`}
                                          />
                                          <span className="font-mono text-xs w-6 text-right font-bold">
                                            {sel.weight}
                                          </span>
                                        </div>
                                      )}
                                    </div>
                                  );
                                })}
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>

            <button
              type="submit"
              disabled={generating}
              className="qp-btn qp-btn-primary w-full text-base py-4"
              data-testid="generate-paper-button"
            >
              <Sparkle size={18} weight="bold" />
              {generating ? "Generating..." : "Generate Question Paper"}
              <ArrowRight size={16} weight="bold" />
            </button>
          </div>
        </form>
      </main>
    </div>
  );
}

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, Number(v)));

const SliderRow = ({ label, value, onChange, readOnly, color, testid }) => (
  <div className="mb-4 last:mb-0" data-testid={testid}>
    <div className="flex items-center justify-between mb-2">
      <div className="font-bold text-sm uppercase tracking-wider">{label}</div>
      <div className="font-mono text-sm font-bold">{value}%</div>
    </div>
    <div className="relative h-2 bg-neutral-200">
      <div
        className="absolute top-0 left-0 h-full"
        style={{ width: `${value}%`, background: color }}
      />
    </div>
    {!readOnly && (
      <input
        type="range"
        min={0}
        max={100}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full mt-1"
        data-testid={`${testid}-slider`}
      />
    )}
  </div>
);
