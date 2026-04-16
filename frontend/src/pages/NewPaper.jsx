import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import Header from "@/components/Header";
import { toast } from "sonner";
import { Sparkle, ArrowRight, CheckSquare, Square } from "@phosphor-icons/react";

const DIFFICULTIES = ["easy", "medium", "hard"];

export default function NewPaper() {
  const navigate = useNavigate();
  const [textbooks, setTextbooks] = useState([]);
  const [selectedTbId, setSelectedTbId] = useState("");
  const [tbDetail, setTbDetail] = useState(null);
  const [title, setTitle] = useState("");
  const [difficulty, setDifficulty] = useState("medium");
  const [duration, setDuration] = useState(60);
  const [totalMarks, setTotalMarks] = useState(50);
  const [info, setInfo] = useState(40);
  const [concept, setConcept] = useState(40);
  const [selectedTopics, setSelectedTopics] = useState([]);
  const [generating, setGenerating] = useState(false);
  const [extracting, setExtracting] = useState(false);

  const application = useMemo(
    () => Math.max(0, 100 - info - concept),
    [info, concept]
  );

  useEffect(() => {
    api.get("/textbooks").then((r) => setTextbooks(r.data));
  }, []);

  useEffect(() => {
    if (!selectedTbId) {
      setTbDetail(null);
      setSelectedTopics([]);
      return;
    }
    api.get(`/textbooks/${selectedTbId}`).then((r) => {
      setTbDetail(r.data);
      setSelectedTopics([]);
    });
  }, [selectedTbId]);

  const toggleTopic = (name) => {
    setSelectedTopics((curr) =>
      curr.includes(name) ? curr.filter((t) => t !== name) : [...curr, name]
    );
  };

  const extractIfNeeded = async () => {
    if (!selectedTbId) return;
    setExtracting(true);
    try {
      const { data } = await api.post(
        `/textbooks/${selectedTbId}/extract-topics`
      );
      setTbDetail({ ...tbDetail, topics: data.topics });
      toast.success("Topics extracted");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed");
    } finally {
      setExtracting(false);
    }
  };

  const onGenerate = async (e) => {
    e.preventDefault();
    if (!selectedTbId) return toast.error("Select a textbook");
    if (!title) return toast.error("Title required");
    if (selectedTopics.length === 0)
      return toast.error("Select at least one topic");
    if (info + concept + application !== 100)
      return toast.error("Distribution must sum to 100%");

    setGenerating(true);
    try {
      const { data } = await api.post("/papers/generate", {
        title,
        subject: tbDetail?.subject || "",
        class_name: tbDetail?.class_name || "",
        textbook_id: selectedTbId,
        topics: selectedTopics,
        difficulty,
        duration_minutes: Number(duration),
        total_marks: Number(totalMarks),
        distribution: { information: info, concept, application },
      });
      toast.success("Paper generated");
      navigate(`/papers/${data.id}`);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Generation failed");
    } finally {
      setGenerating(false);
    }
  };

  const hasTopics = (tbDetail?.topics || []).length > 0;

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
                <label className="qp-label">Textbook</label>
                <select
                  value={selectedTbId}
                  onChange={(e) => setSelectedTbId(e.target.value)}
                  className="qp-input"
                  required
                  data-testid="paper-textbook-select"
                >
                  <option value="">Select textbook</option>
                  {textbooks.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.original_filename} — {t.subject} / Class {t.class_name}
                    </option>
                  ))}
                </select>
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
          </div>

          {/* Right: Topics + submit */}
          <div className="lg:col-span-2 space-y-6">
            <div className="qp-card">
              <div className="flex items-center justify-between mb-4">
                <div className="overline">// TOPICS</div>
                {tbDetail && (
                  <button
                    type="button"
                    onClick={extractIfNeeded}
                    disabled={extracting}
                    className="qp-btn-ghost text-xs uppercase tracking-wider"
                    data-testid="extract-topics-button"
                  >
                    {extracting ? "..." : hasTopics ? "Re-extract" : "Extract"}
                  </button>
                )}
              </div>

              {!tbDetail && (
                <div className="text-sm text-neutral-500">
                  Select a textbook to load topics.
                </div>
              )}

              {tbDetail && !hasTopics && (
                <div className="text-sm text-neutral-600">
                  No topics extracted yet.
                  <button
                    type="button"
                    onClick={extractIfNeeded}
                    disabled={extracting}
                    className="qp-btn qp-btn-primary w-full mt-3"
                    data-testid="extract-now-button"
                  >
                    <Sparkle size={14} weight="bold" />
                    {extracting ? "Extracting..." : "Extract topics now"}
                  </button>
                </div>
              )}

              {hasTopics && (
                <div className="space-y-2 max-h-[400px] overflow-auto pr-1">
                  {tbDetail.topics.map((t, i) => {
                    const checked = selectedTopics.includes(t.name);
                    return (
                      <button
                        type="button"
                        key={i}
                        onClick={() => toggleTopic(t.name)}
                        data-testid={`topic-select-${i}`}
                        className={`w-full text-left border-2 p-3 flex items-start gap-3 transition-colors ${
                          checked
                            ? "border-[#002FA7] bg-[#002FA7]/5"
                            : "border-black bg-white hover:bg-neutral-50"
                        }`}
                      >
                        {checked ? (
                          <CheckSquare
                            size={18}
                            weight="fill"
                            color="#002FA7"
                            className="shrink-0 mt-0.5"
                          />
                        ) : (
                          <Square
                            size={18}
                            weight="bold"
                            className="shrink-0 mt-0.5"
                          />
                        )}
                        <div className="min-w-0">
                          <div className="font-bold">{t.name}</div>
                          {t.subtopics?.length > 0 && (
                            <div className="text-xs text-neutral-500 font-mono mt-0.5 truncate">
                              {t.subtopics.join(" · ")}
                            </div>
                          )}
                        </div>
                      </button>
                    );
                  })}
                </div>
              )}
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
