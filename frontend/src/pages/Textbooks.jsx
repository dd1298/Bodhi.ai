import React, { useEffect, useState } from "react";
import { api } from "@/lib/api";
import Header from "@/components/Header";
import { toast } from "sonner";
import {
  UploadSimple,
  FolderOpen,
  Sparkle,
  Trash,
  CheckCircle,
  CaretRight,
  CaretDown,
} from "@phosphor-icons/react";

export default function Textbooks() {
  const [textbooks, setTextbooks] = useState([]);
  const [subject, setSubject] = useState("");
  const [className, setClassName] = useState("");
  const [file, setFile] = useState(null);
  const [dragActive, setDragActive] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [extractingId, setExtractingId] = useState(null);
  const [expanded, setExpanded] = useState({});
  const [detailTopics, setDetailTopics] = useState({}); // id -> topics

  const load = async () => {
    const { data } = await api.get("/textbooks");
    setTextbooks(data);
  };

  useEffect(() => {
    load();
  }, []);

  // Poll every 5s while any textbook is still ingesting so users see the
  // status flip from "ingesting" → "indexed"/"topics_ready" without needing
  // to reload the page. Background OCR of a large scanned PDF can take
  // 30-120s and users otherwise have no signal of progress.
  useEffect(() => {
    const hasIngesting = textbooks.some((tb) => tb.status === "ingesting");
    if (!hasIngesting) return;
    const iv = setInterval(load, 5000);
    return () => clearInterval(iv);
  }, [textbooks]);

  const onFile = (f) => {
    if (!f) return;
    if (!f.name.toLowerCase().endsWith(".pdf")) {
      toast.error("Only PDF files are accepted");
      return;
    }
    setFile(f);
  };

  const onDrop = (e) => {
    e.preventDefault();
    setDragActive(false);
    onFile(e.dataTransfer.files?.[0]);
  };

  const upload = async (e) => {
    e.preventDefault();
    if (!file) return toast.error("Please select a PDF");
    if (!subject || !className) return toast.error("Subject & Class required");
    const fd = new FormData();
    fd.append("file", file);
    setUploading(true);
    try {
      await api.post(
        `/textbooks/upload?subject=${encodeURIComponent(
          subject
        )}&class_name=${encodeURIComponent(className)}`,
        fd,
        { headers: { "Content-Type": "multipart/form-data" } }
      );
      toast.success("Uploaded — indexing in the background");
      setFile(null);
      setSubject("");
      setClassName("");
      await load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const extractTopics = async (id) => {
    setExtractingId(id);
    try {
      const { data } = await api.post(`/textbooks/${id}/extract-topics`);
      setDetailTopics({ ...detailTopics, [id]: data.topics });
      setExpanded({ ...expanded, [id]: true });
      toast.success("Topics extracted");
      await load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Extraction failed");
    } finally {
      setExtractingId(null);
    }
  };

  const deleteTextbook = async (id) => {
    if (!window.confirm("Delete this textbook?")) return;
    await api.delete(`/textbooks/${id}`);
    toast.success("Deleted");
    await load();
  };

  const toggleExpand = async (tb) => {
    const nextOpen = !expanded[tb.id];
    setExpanded({ ...expanded, [tb.id]: nextOpen });
    if (nextOpen && !detailTopics[tb.id]) {
      const { data } = await api.get(`/textbooks/${tb.id}`);
      setDetailTopics({ ...detailTopics, [tb.id]: data.topics || [] });
    }
  };

  return (
    <div className="min-h-screen bg-[#FAFAFA]">
      <Header />
      <main className="max-w-7xl mx-auto p-6 md:p-12" data-testid="textbooks-page">
        <div className="overline text-neutral-500 mb-3">// TEXTBOOK INDEX</div>
        <h1 className="font-display text-5xl md:text-6xl mb-10">
          Textbooks &<br />
          <span className="text-[#002FA7]">Topic Extraction.</span>
        </h1>

        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6 md:gap-8">
          {/* Upload */}
          <form
            onSubmit={upload}
            className="lg:col-span-2 qp-card hard-shadow-static"
            data-testid="textbook-upload-form"
          >
            <div className="overline text-neutral-500 mb-3">// NEW UPLOAD</div>
            <h2 className="font-display text-3xl mb-6">Upload PDF</h2>

            <div className="mb-4">
              <label className="qp-label">Subject</label>
              <input
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                placeholder="e.g., Physics"
                className="qp-input"
                data-testid="upload-subject-input"
                required
              />
            </div>
            <div className="mb-4">
              <label className="qp-label">Class</label>
              <input
                value={className}
                onChange={(e) => setClassName(e.target.value)}
                placeholder="e.g., 10"
                className="qp-input"
                data-testid="upload-class-input"
                required
              />
            </div>

            <label
              onDragOver={(e) => {
                e.preventDefault();
                setDragActive(true);
              }}
              onDragLeave={() => setDragActive(false)}
              onDrop={onDrop}
              className={`qp-drop mt-2 ${dragActive ? "active" : ""}`}
              data-testid="upload-drop-zone"
            >
              <UploadSimple size={32} weight="bold" />
              <div className="mt-3 font-bold uppercase tracking-wider text-sm">
                {file ? file.name : "Drop PDF or click to browse"}
              </div>
              <div className="text-xs text-neutral-500 font-mono mt-1">
                Max 500MB · Textbook chapters recommended
              </div>
              <input
                type="file"
                accept="application/pdf"
                onChange={(e) => onFile(e.target.files?.[0])}
                className="hidden"
                data-testid="upload-file-input"
              />
            </label>

            <button
              type="submit"
              disabled={uploading}
              className="qp-btn qp-btn-primary w-full mt-6"
              data-testid="upload-submit-button"
            >
              {uploading ? "Uploading & indexing..." : "Upload & Index"}
            </button>
          </form>

          {/* List */}
          <div className="lg:col-span-3">
            <div className="overline text-neutral-500 mb-3">
              // INDEXED ({textbooks.length})
            </div>
            {textbooks.length === 0 ? (
              <div className="border-2 border-black bg-white p-10 text-center">
                <FolderOpen size={40} weight="duotone" className="mx-auto" />
                <div className="mt-3 font-display text-2xl">
                  No textbooks yet
                </div>
                <div className="text-sm text-neutral-500 mt-1">
                  Upload your first textbook to start generating papers.
                </div>
              </div>
            ) : (
              <div className="space-y-3">
                {textbooks.map((tb) => (
                  <div
                    key={tb.id}
                    className="border-2 border-black bg-white"
                    data-testid={`textbook-${tb.id}`}
                  >
                    <div className="p-4 flex flex-col md:flex-row md:items-center gap-3">
                      <button
                        onClick={() => toggleExpand(tb)}
                        className="flex-1 flex items-start gap-3 text-left"
                        data-testid={`textbook-toggle-${tb.id}`}
                      >
                        {expanded[tb.id] ? (
                          <CaretDown size={20} weight="bold" />
                        ) : (
                          <CaretRight size={20} weight="bold" />
                        )}
                        <div className="flex-1 min-w-0">
                          <div className="font-bold truncate">
                            {tb.original_filename}
                          </div>
                          <div className="text-xs font-mono text-neutral-500 mt-0.5">
                            {tb.subject} · Class {tb.class_name}
                          </div>
                        </div>
                        <div className="flex flex-wrap gap-1">
                          {tb.is_shared && (
                            <span
                              className="qp-badge qp-badge-yellow"
                              data-testid={`shared-badge-${tb.id}`}
                            >
                              shared library
                            </span>
                          )}
                          <span
                            className={`qp-badge ${
                              tb.status === "topics_ready"
                                ? "qp-badge-success"
                                : tb.status === "indexed"
                                ? "qp-badge-blue"
                                : "qp-badge-red"
                            }`}
                          >
                            {tb.status.replace("_", " ")}
                          </span>
                          {tb.topic_count > 0 && (
                            <span className="qp-badge">
                              {tb.topic_count} topics
                            </span>
                          )}
                        </div>
                      </button>
                      <div className="flex gap-2">
                        <button
                          onClick={() => extractTopics(tb.id)}
                          disabled={
                            extractingId === tb.id ||
                            tb.is_owned === false ||
                            tb.status === "ingesting"
                          }
                          className="qp-btn qp-btn-secondary text-xs"
                          title={
                            tb.status === "ingesting"
                              ? "Still OCR'ing the PDF — please wait a moment"
                              : tb.is_owned === false
                              ? "Shared library — read-only"
                              : undefined
                          }
                          data-testid={`extract-topics-${tb.id}`}
                        >
                          <Sparkle size={14} weight="bold" />
                          {tb.status === "ingesting"
                            ? "Processing PDF..."
                            : extractingId === tb.id
                            ? "Analyzing..."
                            : tb.topic_count > 0
                            ? "Re-extract"
                            : "Extract topics"}
                        </button>
                        <button
                          onClick={() => deleteTextbook(tb.id)}
                          disabled={tb.is_owned === false}
                          className="qp-btn qp-btn-secondary text-xs"
                          aria-label="Delete textbook"
                          title={tb.is_owned === false ? "Shared library — read-only" : undefined}
                          data-testid={`delete-textbook-${tb.id}`}
                        >
                          <Trash size={14} weight="bold" />
                        </button>
                      </div>
                    </div>

                    {expanded[tb.id] && (
                      <div className="border-t border-neutral-200 p-4 bg-neutral-50">
                        {detailTopics[tb.id]?.length ? (
                          <div className="font-mono text-sm space-y-2">
                            {detailTopics[tb.id].map((t, i) => (
                              <div
                                key={i}
                                data-testid={`topic-${tb.id}-${i}`}
                              >
                                <div className="flex items-center gap-2 font-bold">
                                  <CheckCircle
                                    size={14}
                                    weight="fill"
                                    color="#002FA7"
                                  />
                                  {t.name}
                                </div>
                                {t.subtopics?.length > 0 && (
                                  <ul className="pl-7 text-neutral-600">
                                    {t.subtopics.map((s, j) => (
                                      <li key={j}>— {s}</li>
                                    ))}
                                  </ul>
                                )}
                              </div>
                            ))}
                          </div>
                        ) : (
                          <div className="text-sm text-neutral-500">
                            No topics extracted yet. Click{" "}
                            <b>Extract topics</b> to generate.
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
