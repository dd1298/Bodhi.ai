import React, { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { api, API } from "@/lib/api";
import Header from "@/components/Header";
import { toast } from "sonner";
import {
  ArrowLeft,
  Download,
  PencilSimple,
  FloppyDisk,
  X,
  CheckCircle,
  WarningCircle,
  Image as ImageIcon,
} from "@phosphor-icons/react";

const typeBadge = (t) => {
  if (t === "information") return "qp-badge qp-badge-blue";
  if (t === "application") return "qp-badge qp-badge-red";
  return "qp-badge qp-badge-yellow";
};

export default function SolutionView() {
  const { id } = useParams();
  const [paper, setPaper] = useState(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(null); // { sections: [ {title, answers: [{question_id, answer}]} ] }
  const [saving, setSaving] = useState(false);
  const [regenerating, setRegenerating] = useState(false);

  const load = async () => {
    const { data } = await api.get(`/papers/${id}`);
    setPaper(data);
  };

  useEffect(() => {
    load();
  }, [id]); // eslint-disable-line

  const regenerate = async () => {
    if (
      paper?.solution &&
      !window.confirm("Regenerate solution? Your current edits will be overwritten.")
    ) {
      return;
    }
    setRegenerating(true);
    try {
      await api.post(`/papers/${id}/solution/generate`);
      toast.success("Solution generated");
      await load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed");
    } finally {
      setRegenerating(false);
    }
  };

  const enterEdit = () => {
    const sol = paper?.solution;
    if (!sol) return;
    setDraft(JSON.parse(JSON.stringify(sol)));
    setEditing(true);
  };

  const cancelEdit = () => {
    setDraft(null);
    setEditing(false);
  };

  const updateAnswer = (si, ai, value) => {
    const next = { ...draft };
    next.sections = next.sections.map((s, i) =>
      i === si
        ? {
            ...s,
            answers: s.answers.map((a, j) =>
              j === ai ? { ...a, answer: value } : a
            ),
          }
        : s
    );
    setDraft(next);
  };

  const saveEdit = async () => {
    setSaving(true);
    try {
      await api.patch(`/papers/${id}/solution`, {
        sections: draft.sections,
      });
      toast.success("Solution saved — AI will learn from your edits");
      setEditing(false);
      setDraft(null);
      await load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const download = async () => {
    try {
      const token = localStorage.getItem("qp_token");
      const resp = await fetch(`${API}/papers/${id}/solution/pdf`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const ab = await resp.arrayBuffer();
      const blob = new Blob([ab], { type: "application/pdf" });
      const blobUrl = URL.createObjectURL(blob);
      const safeTitle =
        (paper.title || "paper").replace(/[^a-zA-Z0-9_\- ]/g, "").trim() ||
        "paper";
      const a = document.createElement("a");
      a.style.display = "none";
      a.href = blobUrl;
      a.download = `${safeTitle} - Solution.pdf`;
      document.body.appendChild(a);
      a.click();
      setTimeout(() => {
        try {
          document.body.removeChild(a);
          URL.revokeObjectURL(blobUrl);
        } catch {}
      }, 3000);
      toast.success("Download started");
    } catch (err) {
      toast.error(`Download failed: ${err.message || err}`);
    }
  };

  if (!paper) {
    return (
      <div className="min-h-screen bg-[#FAFAFA]">
        <Header />
        <div className="max-w-5xl mx-auto p-12 text-neutral-500">
          Loading...
        </div>
      </div>
    );
  }

  const solution = editing ? draft : paper.solution;

  // Build answer lookup by question_id
  const answerByQid = {};
  (solution?.sections || []).forEach((s) =>
    (s.answers || []).forEach((a) => {
      answerByQid[a.question_id] = a.answer;
    })
  );

  let counter = 1;

  return (
    <div className="min-h-screen bg-[#FAFAFA]">
      <Header />
      <main className="max-w-5xl mx-auto p-6 md:p-12" data-testid="solution-view-page">
        {/* Toolbar */}
        <div className="no-print flex items-center justify-between mb-8 flex-wrap gap-3">
          <Link
            to={`/papers/${id}`}
            className="qp-btn-ghost inline-flex items-center gap-2"
            data-testid="back-to-paper"
          >
            <ArrowLeft size={16} weight="bold" /> Back to paper
          </Link>
          <div className="flex gap-2">
            {!solution ? (
              <button
                onClick={regenerate}
                disabled={regenerating}
                className="qp-btn qp-btn-primary"
                data-testid="generate-solution-button"
              >
                <CheckCircle size={16} weight="bold" />
                {regenerating ? "Generating..." : "Generate Solution"}
              </button>
            ) : editing ? (
              <>
                <button
                  onClick={cancelEdit}
                  className="qp-btn qp-btn-secondary"
                  data-testid="cancel-solution-edit-button"
                >
                  <X size={16} weight="bold" /> Cancel
                </button>
                <button
                  onClick={saveEdit}
                  disabled={saving}
                  className="qp-btn qp-btn-primary"
                  data-testid="save-solution-edit-button"
                >
                  <FloppyDisk size={16} weight="bold" />
                  {saving ? "Saving..." : "Save"}
                </button>
              </>
            ) : (
              <>
                <button
                  onClick={regenerate}
                  disabled={regenerating}
                  className="qp-btn qp-btn-secondary"
                  data-testid="regenerate-solution-button"
                >
                  {regenerating ? "Regenerating..." : "Regenerate"}
                </button>
                <button
                  onClick={enterEdit}
                  className="qp-btn qp-btn-secondary"
                  data-testid="enter-solution-edit-button"
                >
                  <PencilSimple size={16} weight="bold" /> Edit
                </button>
                <button
                  onClick={download}
                  className="qp-btn qp-btn-primary"
                  data-testid="download-solution-pdf-button"
                >
                  <Download size={16} weight="bold" /> Download Solution PDF
                </button>
              </>
            )}
          </div>
        </div>

        {/* Empty state */}
        {!solution && (
          <div
            className="bg-white border-2 border-black p-10 md:p-16 text-center hard-shadow-static"
            data-testid="solution-empty-state"
          >
            <div className="overline text-neutral-500 mb-3">// ANSWER KEY</div>
            <h1 className="font-display text-4xl md:text-5xl mb-3">
              No solution yet.
            </h1>
            <p className="text-neutral-600 max-w-md mx-auto mb-6">
              Generate an AI answer key for <b>{paper.title}</b> so you can
              verify student responses. Answers are tailored per question type:
              concise for Information, explained for Concept, step-by-step for
              Application.
            </p>
            <button
              onClick={regenerate}
              disabled={regenerating}
              className="qp-btn qp-btn-primary"
              data-testid="generate-solution-cta"
            >
              <CheckCircle size={16} weight="bold" />
              {regenerating ? "Generating..." : "Generate Solution"}
            </button>
          </div>
        )}

        {/* Solution body */}
        {solution && (
          <div
            className="bg-white border-2 border-black p-8 md:p-12 hard-shadow-static-lg"
            data-testid="solution-body"
          >
            <div className="text-center border-b-2 border-black pb-6 mb-6">
              <div className="overline text-neutral-500 mb-2">
                // ANSWER KEY
              </div>
              <h1 className="font-display text-3xl md:text-4xl">
                {paper.title}
              </h1>
              <div className="mt-3 font-mono text-sm text-neutral-700">
                Class <b>{paper.class_name}</b> · Subject{" "}
                <b>{paper.subject}</b> · Total Marks{" "}
                <b>{paper.total_marks}</b>
              </div>
            </div>

            {solution.is_stale && (
              <div
                className="mb-6 border-2 border-[#E63946] bg-red-50 p-4 flex items-start gap-3"
                data-testid="stale-banner"
              >
                <WarningCircle
                  size={24}
                  weight="fill"
                  color="#E63946"
                  className="shrink-0"
                />
                <div className="flex-1">
                  <div className="font-bold uppercase tracking-wider text-sm">
                    Solution out of date
                  </div>
                  <div className="text-sm text-neutral-700 mt-1">
                    The question paper has been edited after this solution was
                    generated. Regenerate to refresh answers.
                  </div>
                </div>
                <button
                  onClick={regenerate}
                  disabled={regenerating}
                  className="qp-btn qp-btn-primary text-xs"
                  data-testid="stale-regenerate-button"
                >
                  {regenerating ? "..." : "Regenerate"}
                </button>
              </div>
            )}

            {(paper.sections || []).map((section, si) => (
              <section key={si} className="mb-8">
                <h2 className="font-display text-xl md:text-2xl text-[#002FA7] mb-4 border-b border-neutral-300 pb-2">
                  {section.title}
                </h2>
                <ol className="space-y-6">
                  {(section.questions || []).map((q, qi) => {
                    const qNum = counter++;
                    const solSection = solution.sections?.[si];
                    const aIdx = (solSection?.answers || []).findIndex(
                      (a) => a.question_id === q.id
                    );
                    return (
                      <li
                        key={q.id}
                        className="border-b border-dashed border-neutral-200 pb-6 last:border-0"
                        data-testid={`solution-item-${q.id}`}
                      >
                        <div className="flex items-start gap-2">
                          <span className="font-bold">Q{qNum}.</span>
                          <span className="flex-1">{q.question}</span>
                          <span className="font-mono font-bold text-sm shrink-0">
                            [{q.marks}]
                          </span>
                        </div>
                        <div className="mt-2 flex flex-wrap gap-1 pl-6">
                          <span className={typeBadge(q.type)}>{q.type}</span>
                          <span className="qp-badge">{q.difficulty}</span>
                          {q.diagram_path && (
                            <span className="qp-badge">
                              <ImageIcon size={10} weight="bold" /> diagram
                            </span>
                          )}
                        </div>

                        <div className="mt-4 pl-6">
                          <div className="overline text-neutral-500 mb-2">
                            // ANSWER
                          </div>
                          {editing && solSection && aIdx >= 0 ? (
                            <textarea
                              value={
                                draft.sections[si].answers[aIdx].answer || ""
                              }
                              onChange={(e) =>
                                updateAnswer(si, aIdx, e.target.value)
                              }
                              className="qp-input w-full font-mono text-sm"
                              rows={Math.max(3, Math.min(12,
                                Math.ceil((draft.sections[si].answers[aIdx].answer || "").length / 80) + 1
                              ))}
                              data-testid={`edit-answer-${q.id}`}
                            />
                          ) : (
                            <div
                              className="bg-neutral-50 border border-neutral-300 p-4 whitespace-pre-wrap text-sm leading-relaxed"
                              data-testid={`answer-${q.id}`}
                            >
                              {answerByQid[q.id] || (
                                <span className="text-neutral-400 italic">
                                  (no answer)
                                </span>
                              )}
                            </div>
                          )}
                        </div>
                      </li>
                    );
                  })}
                </ol>
              </section>
            ))}

            <div className="text-center mt-8 pt-4 border-t-2 border-black font-mono text-xs text-neutral-500">
              — End of Answer Key —
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
