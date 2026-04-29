import React, { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { api, API } from "@/lib/api";
import Header from "@/components/Header";
import { toast } from "sonner";
import {
  Star,
  ArrowLeft,
  Download,
  Printer,
  BookmarkSimple,
  PencilSimple,
  FloppyDisk,
  Trash,
  Plus,
  X,
  Image as ImageIcon,
  CheckCircle,
} from "@phosphor-icons/react";
import MathText from "@/components/MathText";

const typeBadge = (t) => {
  if (t === "information") return "qp-badge qp-badge-blue";
  if (t === "application") return "qp-badge qp-badge-red";
  return "qp-badge qp-badge-yellow";
};

const TYPE_OPTIONS = ["information", "concept", "application"];
const DIFF_OPTIONS = ["easy", "medium", "hard"];

export default function PaperView() {
  const { id } = useParams();
  const [paper, setPaper] = useState(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(null);
  const [saving, setSaving] = useState(false);

  const load = async () => {
    const { data } = await api.get(`/papers/${id}`);
    setPaper(data);
  };

  useEffect(() => {
    load();
  }, [id]); // eslint-disable-line

  // Poll for diagram completion when any are still pending.
  useEffect(() => {
    if (!paper || editing) return;
    if ((paper.diagrams_pending || 0) === 0) return;
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, [paper, editing]); // eslint-disable-line

  const enterEdit = () => {
    setDraft(JSON.parse(JSON.stringify(paper)));
    setEditing(true);
  };

  const cancelEdit = () => {
    setDraft(null);
    setEditing(false);
  };

  const saveEdit = async () => {
    setSaving(true);
    try {
      const payload = {
        title: draft.title,
        instructions: draft.instructions,
        duration_minutes: Number(draft.duration_minutes),
        total_marks: Number(draft.total_marks),
        sections: draft.sections.map((s) => ({
          title: s.title,
          questions: s.questions,
        })),
      };
      const { data } = await api.patch(`/papers/${id}`, payload);
      setPaper(data);
      setDraft(null);
      setEditing(false);
      toast.success("Paper saved — AI will learn from your edits");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const updateQ = (si, qi, patch) => {
    const next = { ...draft };
    next.sections = next.sections.map((s, i) =>
      i === si
        ? {
            ...s,
            questions: s.questions.map((q, j) =>
              j === qi ? { ...q, ...patch } : q
            ),
          }
        : s
    );
    setDraft(next);
  };

  const deleteQ = (si, qi) => {
    const next = { ...draft };
    next.sections = next.sections.map((s, i) =>
      i === si
        ? { ...s, questions: s.questions.filter((_, j) => j !== qi) }
        : s
    );
    setDraft(next);
  };

  const addQ = (si) => {
    const next = { ...draft };
    next.sections = next.sections.map((s, i) =>
      i === si
        ? {
            ...s,
            questions: [
              ...s.questions,
              {
                id: `new-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
                question: "",
                type: "concept",
                difficulty: "medium",
                marks: 2,
                important: false,
                needs_diagram: false,
              },
            ],
          }
        : s
    );
    setDraft(next);
  };

  const toggleImportant = async (qid) => {
    try {
      const { data } = await api.patch(
        `/papers/${id}/question/${qid}/toggle-important`
      );
      setPaper({ ...paper, sections: data.sections });
    } catch {
      toast.error("Failed");
    }
  };

  const saveToBank = async (qid) => {
    try {
      await api.post(`/qbank/save-from-paper/${id}/${qid}`);
      toast.success("Saved to question bank");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed");
    }
  };

  const download = async () => {
    try {
      const token = localStorage.getItem("qp_token");
      const resp = await fetch(`${API}/papers/${id}/pdf`, {
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
      a.download = `${safeTitle}.pdf`;
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
          Loading paper...
        </div>
      </div>
    );
  }

  const view = editing ? draft : paper;
  let counter = 1;

  return (
    <div className="min-h-screen bg-[#FAFAFA]">
      <Header />
      <main className="max-w-5xl mx-auto p-6 md:p-12" data-testid="paper-view-page">
        {/* Toolbar */}
        <div className="no-print flex items-center justify-between mb-8 flex-wrap gap-3">
          <Link
            to="/"
            className="qp-btn-ghost inline-flex items-center gap-2"
            data-testid="back-to-dashboard"
          >
            <ArrowLeft size={16} weight="bold" /> Dashboard
          </Link>
          <div className="flex gap-2">
            {editing ? (
              <>
                <button
                  onClick={cancelEdit}
                  className="qp-btn qp-btn-secondary"
                  data-testid="cancel-edit-button"
                >
                  <X size={16} weight="bold" /> Cancel
                </button>
                <button
                  onClick={saveEdit}
                  disabled={saving}
                  className="qp-btn qp-btn-primary"
                  data-testid="save-edit-button"
                >
                  <FloppyDisk size={16} weight="bold" />
                  {saving ? "Saving..." : "Save"}
                </button>
              </>
            ) : (
              <>
                <button
                  onClick={enterEdit}
                  className="qp-btn qp-btn-secondary"
                  data-testid="enter-edit-button"
                >
                  <PencilSimple size={16} weight="bold" /> Edit
                </button>
                <Link
                  to={`/papers/${id}/solution`}
                  className="qp-btn qp-btn-secondary"
                  data-testid="open-solution-button"
                >
                  <CheckCircle size={16} weight="bold" /> Solution
                </Link>
                <button
                  onClick={() => window.print()}
                  className="qp-btn qp-btn-secondary"
                  data-testid="print-button"
                >
                  <Printer size={16} weight="bold" /> Print
                </button>
                <button
                  onClick={download}
                  className="qp-btn qp-btn-primary"
                  data-testid="download-pdf-button"
                >
                  <Download size={16} weight="bold" /> Download PDF
                </button>
              </>
            )}
          </div>
        </div>

        {/* Paper */}
        <div
          className="bg-white border-2 border-black p-8 md:p-12 hard-shadow-static-lg"
          data-testid="paper-preview"
        >
          <div className="text-center border-b-2 border-black pb-6 mb-6">
            {editing ? (
              <input
                value={view.title}
                onChange={(e) =>
                  setDraft({ ...draft, title: e.target.value })
                }
                className="qp-input text-center font-display text-3xl md:text-4xl"
                data-testid="edit-title-input"
              />
            ) : (
              <h1 className="font-display text-3xl md:text-4xl">
                {view.title}
              </h1>
            )}
            <div className="mt-3 font-mono text-sm text-neutral-700">
              Class <b>{view.class_name}</b> · Subject <b>{view.subject}</b>
            </div>
            <div className="mt-1 font-mono text-sm text-neutral-700 flex flex-wrap gap-3 justify-center items-center">
              <span>
                Total Marks:{" "}
                {editing ? (
                  <input
                    type="number"
                    value={view.total_marks}
                    onChange={(e) =>
                      setDraft({ ...draft, total_marks: e.target.value })
                    }
                    className="qp-input inline-block w-20 py-1 text-sm"
                    data-testid="edit-marks-input"
                  />
                ) : (
                  <b>{view.total_marks}</b>
                )}
              </span>
              <span>
                Duration:{" "}
                {editing ? (
                  <input
                    type="number"
                    value={view.duration_minutes}
                    onChange={(e) =>
                      setDraft({ ...draft, duration_minutes: e.target.value })
                    }
                    className="qp-input inline-block w-20 py-1 text-sm"
                    data-testid="edit-duration-input"
                  />
                ) : (
                  <b>{view.duration_minutes} min</b>
                )}
              </span>
              <span>
                Difficulty:{" "}
                <b className="uppercase">{view.difficulty}</b>
              </span>
            </div>
          </div>

          {editing ? (
            <textarea
              value={view.instructions || ""}
              onChange={(e) =>
                setDraft({ ...draft, instructions: e.target.value })
              }
              className="qp-input w-full mb-6"
              rows={2}
              placeholder="Instructions (e.g., attempt all questions)"
              data-testid="edit-instructions-input"
            />
          ) : (
            view.instructions && (
              <div className="mb-6 border border-neutral-300 bg-neutral-50 p-4 text-sm">
                <span className="font-bold">Instructions: </span>
                {view.instructions}
              </div>
            )
          )}

          {(view.sections || []).map((section, si) => (
            <section key={si} className="mb-8" data-testid={`section-${si}`}>
              <h2 className="font-display text-xl md:text-2xl text-[#002FA7] mb-4 border-b border-neutral-300 pb-2">
                {section.title}
              </h2>
              <ol className="space-y-4">
                {(section.questions || []).map((q, qi) => {
                  const qNum = counter++;
                  if (editing) {
                    return (
                      <li
                        key={q.id}
                        className="border-2 border-neutral-300 p-4"
                        data-testid={`edit-question-${q.id}`}
                      >
                        <div className="flex items-start gap-2 mb-2">
                          <span className="font-bold pt-2">Q{qNum}.</span>
                          <textarea
                            value={q.question}
                            onChange={(e) =>
                              updateQ(si, qi, { question: e.target.value })
                            }
                            className="qp-input flex-1"
                            rows={2}
                            data-testid={`edit-q-text-${q.id}`}
                          />
                          <button
                            onClick={() => deleteQ(si, qi)}
                            className="qp-btn qp-btn-secondary text-xs shrink-0"
                            data-testid={`edit-q-delete-${q.id}`}
                          >
                            <Trash size={14} weight="bold" />
                          </button>
                        </div>
                        <div className="grid grid-cols-3 gap-2 mt-2 pl-6">
                          <select
                            value={q.type}
                            onChange={(e) =>
                              updateQ(si, qi, { type: e.target.value })
                            }
                            className="qp-input text-sm py-1"
                            data-testid={`edit-q-type-${q.id}`}
                          >
                            {TYPE_OPTIONS.map((t) => (
                              <option key={t} value={t}>
                                {t}
                              </option>
                            ))}
                          </select>
                          <select
                            value={q.difficulty}
                            onChange={(e) =>
                              updateQ(si, qi, { difficulty: e.target.value })
                            }
                            className="qp-input text-sm py-1"
                            data-testid={`edit-q-diff-${q.id}`}
                          >
                            {DIFF_OPTIONS.map((d) => (
                              <option key={d} value={d}>
                                {d}
                              </option>
                            ))}
                          </select>
                          <input
                            type="number"
                            value={q.marks}
                            onChange={(e) =>
                              updateQ(si, qi, {
                                marks: Number(e.target.value),
                              })
                            }
                            className="qp-input text-sm py-1"
                            data-testid={`edit-q-marks-${q.id}`}
                          />
                        </div>
                        {q.diagram_path && (
                          <div className="mt-3 pl-6">
                            <DiagramImage paperId={id} questionId={q.id} />
                          </div>
                        )}
                      </li>
                    );
                  }
                  return (
                    <li
                      key={q.id}
                      className="flex flex-col md:flex-row md:items-start gap-3 border-b border-dashed border-neutral-200 pb-4 last:border-0"
                      data-testid={`question-item-${q.id}`}
                    >
                      <div className="flex-1">
                        <div className="flex items-start gap-2">
                          <span className="font-bold">Q{qNum}.</span>
                          {q.important && (
                            <Star
                              size={16}
                              weight="fill"
                              color="#FFC300"
                              className="mt-1"
                            />
                          )}
                          <span className="flex-1">
                            <MathText text={q.question} />
                          </span>
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
                        {q.diagram_path ? (
                          <div className="mt-3 pl-6">
                            <DiagramImage paperId={id} questionId={q.id} />
                          </div>
                        ) : q.diagram_status === "pending" ? (
                          <div className="mt-3 pl-6">
                            <div
                              className="w-48 h-32 border-2 border-dashed border-neutral-300 flex items-center justify-center text-neutral-500 text-xs bg-neutral-50"
                              data-testid={`diagram-pending-${q.id}`}
                            >
                              <ImageIcon size={18} /> &nbsp; generating diagram...
                            </div>
                          </div>
                        ) : null}
                      </div>
                      <div className="no-print flex gap-1 pl-6 md:pl-0">
                        <button
                          onClick={() => toggleImportant(q.id)}
                          className={`qp-btn ${
                            q.important ? "qp-btn-primary" : "qp-btn-secondary"
                          } text-xs`}
                          data-testid={`toggle-important-${q.id}`}
                          title="Mark important"
                        >
                          <Star
                            size={14}
                            weight={q.important ? "fill" : "bold"}
                          />
                        </button>
                        <button
                          onClick={() => saveToBank(q.id)}
                          className="qp-btn qp-btn-secondary text-xs"
                          data-testid={`save-bank-${q.id}`}
                          title="Save to question bank"
                        >
                          <BookmarkSimple size={14} weight="bold" />
                        </button>
                      </div>
                    </li>
                  );
                })}
              </ol>
              {editing && (
                <button
                  onClick={() => addQ(si)}
                  className="qp-btn qp-btn-secondary text-xs mt-3"
                  data-testid={`add-question-${si}`}
                >
                  <Plus size={14} weight="bold" /> Add question
                </button>
              )}
            </section>
          ))}

          <div className="text-center mt-8 pt-4 border-t-2 border-black font-mono text-xs text-neutral-500">
            — End of Paper —
          </div>
        </div>
      </main>
    </div>
  );
}

// Fetches the diagram as a blob URL so the auth token can be sent via header.
const DiagramImage = ({ paperId, questionId }) => {
  const [src, setSrc] = useState(null);
  useEffect(() => {
    let revoked = false;
    let currentUrl = null;
    const token = localStorage.getItem("qp_token");
    fetch(`${API}/papers/${paperId}/diagrams/${questionId}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => (r.ok ? r.blob() : null))
      .then((blob) => {
        if (!blob || revoked) return;
        currentUrl = URL.createObjectURL(blob);
        setSrc(currentUrl);
      })
      .catch(() => {});
    return () => {
      revoked = true;
      if (currentUrl) URL.revokeObjectURL(currentUrl);
    };
  }, [paperId, questionId]);
  if (!src) {
    return (
      <div className="w-48 h-48 border-2 border-dashed border-neutral-300 flex items-center justify-center text-neutral-400 text-xs">
        <ImageIcon size={18} /> &nbsp; diagram loading...
      </div>
    );
  }
  return (
    <img
      src={src}
      alt="diagram"
      className="max-w-xs border border-neutral-300 bg-white"
      data-testid={`diagram-${questionId}`}
    />
  );
};
