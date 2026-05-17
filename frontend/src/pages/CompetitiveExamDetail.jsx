import React, { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "@/lib/api";
import Header from "@/components/Header";
import { toast } from "sonner";
import {
  ArrowLeft,
  UploadSimple,
  FileText,
  Sparkle,
  CheckCircle,
  Hourglass,
  Trash,
  Brain,
} from "@phosphor-icons/react";

const STATUS_PILL = {
  ingesting: { label: "Indexing…", cls: "bg-blue-100 text-blue-900" },
  ready: { label: "Indexed", cls: "bg-green-100 text-green-900" },
  failed: { label: "Failed", cls: "bg-red-100 text-red-900" },
  extraction_empty: { label: "Empty", cls: "bg-yellow-100 text-yellow-900" },
};

export default function CompetitiveExamDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [exam, setExam] = useState(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [genBusy, setGenBusy] = useState(false);
  const [selectedTopics, setSelectedTopics] = useState(new Set());
  const [difficulty, setDifficulty] = useState("medium");
  const [questionCount, setQuestionCount] = useState(10);
  const [duration, setDuration] = useState(30);
  const [customPrompt, setCustomPrompt] = useState("");
  const [ragPreview, setRagPreview] = useState(null);
  const fileRef = useRef(null);

  const load = async () => {
    try {
      const { data } = await api.get(`/competitive-exams/${id}`);
      setExam(data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    const iv = setInterval(load, 6000);
    return () => clearInterval(iv);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const topics = useMemo(() => Object.keys(exam?.topic_counts || {}), [exam]);

  // Default-select top 4 topics on first load.
  useEffect(() => {
    if (topics.length && selectedTopics.size === 0) {
      setSelectedTopics(new Set(topics.slice(0, 4)));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topics.length]);

  const onUpload = async (e) => {
    e.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!file) return toast.error("Select a PDF");
    if (!file.name.toLowerCase().endsWith(".pdf")) return toast.error("PDF only");
    const fd = new FormData();
    fd.append("file", file);
    setUploading(true);
    try {
      await api.post(`/competitive-exams/${id}/papers/upload`, fd, {
        headers: { "Content-Type": "multipart/form-data" },
        timeout: 5 * 60 * 1000,
      });
      toast.success("Uploaded — indexing in the background");
      if (fileRef.current) fileRef.current.value = "";
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const deletePastPaper = async (paperId) => {
    if (!window.confirm("Remove this past paper and its indexed questions?")) return;
    try {
      await api.delete(`/competitive-exams/${id}/papers/${paperId}`);
      toast.success("Removed");
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not delete");
    }
  };

  const togglePill = (name) => {
    setSelectedTopics((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  const previewRag = async () => {
    if (selectedTopics.size === 0) return toast.error("Pick at least one topic");
    const first = Array.from(selectedTopics)[0];
    try {
      const { data } = await api.get(
        `/competitive-exams/${id}/rag-preview?topic=${encodeURIComponent(first)}&k=5`
      );
      setRagPreview({ topic: first, ...data });
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Preview failed");
    }
  };

  const generate = async () => {
    if (selectedTopics.size === 0) return toast.error("Pick at least one topic");
    setGenBusy(true);
    try {
      const { data } = await api.post(
        `/competitive-exams/${id}/generate-paper`,
        {
          exam_id: id,
          title: `${exam?.name || "Competitive"} practice`,
          topics: Array.from(selectedTopics),
          difficulty,
          question_count: questionCount,
          duration_minutes: duration,
          format_distribution: { mcq: 100 },
          custom_instructions: customPrompt,
        }
      );
      toast.success("Generating — this may take ~20-40s");
      navigate(`/papers/${data.id}`);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Generation failed");
    } finally {
      setGenBusy(false);
    }
  };

  if (loading || !exam) {
    return (
      <div className="min-h-screen bg-[#FAFAFA]">
        <Header />
        <main className="max-w-3xl mx-auto p-12 text-neutral-500">Loading…</main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#FAFAFA]">
      <Header />
      <main
        className="max-w-6xl mx-auto p-6 md:p-12"
        data-testid="competitive-exam-detail"
      >
        <Link
          to="/competitive-exams"
          className="qp-btn-ghost inline-flex items-center gap-2 mb-6"
          data-testid="back-to-exams"
        >
          <ArrowLeft size={16} weight="bold" /> All exams
        </Link>

        <div className="flex items-end justify-between flex-wrap gap-4 mb-8">
          <div>
            <div className="overline text-neutral-500 mb-2">// EXAM LIBRARY</div>
            <h1 className="font-display text-5xl">{exam.name}</h1>
            {exam.description && (
              <p className="text-neutral-600 mt-2">{exam.description}</p>
            )}
            <div className="text-xs text-neutral-500 mt-2">
              {exam.papers?.length || 0} past papers · {exam.questions_count || 0}{" "}
              questions indexed · difficulty distribution: easy{" "}
              {exam.difficulty_counts?.easy || 0} · medium{" "}
              {exam.difficulty_counts?.medium || 0} · hard{" "}
              {exam.difficulty_counts?.hard || 0}
            </div>
          </div>
        </div>

        <div className="grid lg:grid-cols-[1fr_1fr] gap-6">
          {/* Upload + past papers */}
          <div>
            <div className="overline text-neutral-500 mb-3">// PAST PAPERS</div>
            <form
              onSubmit={onUpload}
              className="qp-card hard-shadow-static mb-5"
              data-testid="upload-past-paper-form"
            >
              <label className="qp-label">Upload past-paper PDF</label>
              <input
                ref={fileRef}
                type="file"
                accept="application/pdf"
                className="block w-full text-sm mb-3"
                data-testid="past-paper-file-input"
              />
              <button
                type="submit"
                disabled={uploading}
                className="qp-btn qp-btn-primary w-full"
                data-testid="past-paper-upload-submit"
              >
                <UploadSimple size={16} weight="bold" />
                {uploading ? "Uploading…" : "Upload + index"}
              </button>
              <p className="text-xs text-neutral-500 mt-2">
                Indexing extracts questions, tags difficulty (easy/medium/hard) and
                topic, then makes them available to RAG calibration.
              </p>
            </form>

            <div className="space-y-2" data-testid="past-papers-list">
              {(exam.papers || []).length === 0 ? (
                <div className="text-sm text-neutral-500">
                  No past papers uploaded yet.
                </div>
              ) : (
                exam.papers.map((p) => {
                  const pill = STATUS_PILL[p.status] || {
                    label: p.status,
                    cls: "bg-neutral-100",
                  };
                  return (
                    <div
                      key={p.id}
                      className="border-2 border-black bg-white p-3 flex items-center gap-3 hard-shadow-static"
                      data-testid={`past-paper-${p.id}`}
                    >
                      <FileText size={20} weight="fill" className="text-neutral-700" />
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-bold truncate">
                          {p.original_filename}
                        </div>
                        <div className="text-xs text-neutral-500">
                          {p.questions_count || 0} questions
                          {p.error ? ` · ${p.error}` : ""}
                        </div>
                      </div>
                      <span
                        className={`px-2 py-0.5 text-[10px] font-bold uppercase ${pill.cls}`}
                      >
                        {pill.label}
                      </span>
                      <button
                        onClick={() => deletePastPaper(p.id)}
                        className="text-neutral-500 hover:text-red-600"
                        data-testid={`past-paper-delete-${p.id}`}
                      >
                        <Trash size={16} />
                      </button>
                    </div>
                  );
                })
              )}
            </div>
          </div>

          {/* Generate new paper */}
          <div>
            <div className="overline text-neutral-500 mb-3">// NEW PRACTICE PAPER</div>
            <div className="qp-card hard-shadow-static space-y-4">
              <div>
                <label className="qp-label">
                  Topics ({selectedTopics.size}/{topics.length} selected)
                </label>
                {topics.length === 0 ? (
                  <p className="text-sm text-neutral-500">
                    No topics yet — upload at least one past paper first.
                  </p>
                ) : (
                  <div className="flex flex-wrap gap-2" data-testid="topic-pill-list">
                    {topics.map((t) => {
                      const active = selectedTopics.has(t);
                      return (
                        <button
                          key={t}
                          onClick={() => togglePill(t)}
                          data-testid={`topic-pill-${t}`}
                          className={`px-3 py-1 text-xs font-bold border-2 transition-colors ${
                            active
                              ? "border-[#002FA7] bg-[#002FA7] text-white"
                              : "border-black bg-white"
                          }`}
                        >
                          {t} ({exam.topic_counts[t]})
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="qp-label">Difficulty</label>
                  <div className="flex border-2 border-black">
                    {["easy", "medium", "hard"].map((d, i, arr) => (
                      <button
                        type="button"
                        key={d}
                        onClick={() => setDifficulty(d)}
                        data-testid={`comp-diff-${d}`}
                        className={`flex-1 py-2 text-xs font-bold uppercase ${
                          difficulty === d
                            ? "bg-black text-white"
                            : "bg-white text-black"
                        } ${i < arr.length - 1 ? "border-r-2 border-black" : ""}`}
                      >
                        {d}
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <label className="qp-label">Questions</label>
                  <input
                    type="number"
                    min={3}
                    max={60}
                    value={questionCount}
                    onChange={(e) =>
                      setQuestionCount(parseInt(e.target.value, 10) || 0)
                    }
                    className="qp-input"
                    data-testid="comp-question-count"
                  />
                </div>
                <div>
                  <label className="qp-label">Duration (min)</label>
                  <input
                    type="number"
                    min={5}
                    max={300}
                    value={duration}
                    onChange={(e) => setDuration(parseInt(e.target.value, 10) || 0)}
                    className="qp-input"
                    data-testid="comp-duration"
                  />
                </div>
              </div>

              <div>
                <label className="qp-label">Custom instructions (optional)</label>
                <textarea
                  value={customPrompt}
                  onChange={(e) => setCustomPrompt(e.target.value)}
                  className="qp-input"
                  rows={2}
                  spellCheck={false}
                  placeholder="e.g. Mix numerical and conceptual; include 2 PYQ-style questions"
                  data-testid="comp-custom-prompt"
                />
              </div>

              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={previewRag}
                  className="qp-btn qp-btn-secondary"
                  data-testid="comp-rag-preview-btn"
                >
                  <Brain size={16} weight="bold" /> Preview RAG anchors
                </button>
                <button
                  type="button"
                  onClick={generate}
                  disabled={genBusy || selectedTopics.size === 0}
                  className="qp-btn qp-btn-primary flex-1"
                  data-testid="comp-generate-btn"
                >
                  <Sparkle size={16} weight="bold" />
                  {genBusy ? "Generating…" : "Generate practice paper"}
                </button>
              </div>

              {ragPreview && (
                <div
                  className="border-2 border-[#002FA7] bg-[#EEF2FF] p-3 text-xs"
                  data-testid="rag-preview-card"
                >
                  <div className="font-bold mb-1">
                    Anchors for "{ragPreview.topic}" — easy{" "}
                    {ragPreview.distribution.easy} · medium{" "}
                    {ragPreview.distribution.medium} · hard{" "}
                    {ragPreview.distribution.hard}
                  </div>
                  {ragPreview.anchors.length === 0 ? (
                    <div className="text-neutral-600">
                      No anchors retrieved — upload more past papers.
                    </div>
                  ) : (
                    <ul className="space-y-1 mt-1 list-disc pl-4">
                      {ragPreview.anchors.map((a) => (
                        <li key={a.id}>
                          <span className="font-bold uppercase mr-1">
                            [{a.difficulty}]
                          </span>
                          {(a.text || "").slice(0, 110)}…
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
