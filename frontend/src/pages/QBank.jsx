import React, { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import Header from "@/components/Header";
import { toast } from "sonner";
import {
  MagnifyingGlass,
  Trash,
  Bookmark,
  UploadSimple,
  FilePdf,
} from "@phosphor-icons/react";

export default function QBank() {
  const [items, setItems] = useState([]);
  const [q, setQ] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [difficulty, setDifficulty] = useState("");

  // Upload state
  const [subject, setSubject] = useState("");
  const [className, setClassName] = useState("");
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [showUpload, setShowUpload] = useState(false);
  const fileRef = useRef(null);

  const load = async () => {
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (typeFilter) params.set("type_filter", typeFilter);
    if (difficulty) params.set("difficulty", difficulty);
    const { data } = await api.get(`/qbank?${params.toString()}`);
    setItems(data);
  };

  useEffect(() => {
    load();
  }, []); // eslint-disable-line

  useEffect(() => {
    const t = setTimeout(load, 300);
    return () => clearTimeout(t);
  }, [q, typeFilter, difficulty]); // eslint-disable-line

  const remove = async (id) => {
    if (!window.confirm("Delete this question?")) return;
    await api.delete(`/qbank/${id}`);
    toast.success("Deleted");
    load();
  };

  const uploadQpaper = async (e) => {
    e.preventDefault();
    if (!file) return toast.error("Select a PDF");
    const fd = new FormData();
    fd.append("file", file);
    setUploading(true);
    try {
      const params = new URLSearchParams();
      if (subject) params.set("subject", subject);
      if (className) params.set("class_name", className);
      const { data } = await api.post(
        `/qpapers/upload?${params.toString()}`,
        fd,
        { headers: { "Content-Type": "multipart/form-data" } }
      );
      toast.success(`Extracted ${data.saved} questions`);
      setFile(null);
      setSubject("");
      setClassName("");
      setShowUpload(false);
      if (fileRef.current) fileRef.current.value = "";
      await load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#FAFAFA]">
      <Header />
      <main className="max-w-7xl mx-auto p-6 md:p-12" data-testid="qbank-page">
        <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4 mb-10">
          <div>
            <div className="overline text-neutral-500 mb-3">
              // QUESTION BANK
            </div>
            <h1 className="font-display text-5xl md:text-6xl">
              Saved
              <br />
              <span className="text-[#002FA7]">questions.</span>
            </h1>
          </div>
          <button
            onClick={() => setShowUpload((s) => !s)}
            className="qp-btn qp-btn-primary"
            data-testid="toggle-upload-qpaper"
          >
            <UploadSimple size={16} weight="bold" />
            Upload question paper
          </button>
        </div>

        {showUpload && (
          <form
            onSubmit={uploadQpaper}
            className="qp-card hard-shadow-static mb-8"
            data-testid="upload-qpaper-form"
          >
            <div className="overline text-neutral-500 mb-3">
              // UPLOAD EXISTING PAPER
            </div>
            <p className="text-sm text-neutral-600 mb-4">
              Upload a PDF of an existing question paper. The AI will extract
              every question and add them to your question bank.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
              <div>
                <label className="qp-label">Subject (optional)</label>
                <input
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  placeholder="e.g., Physics"
                  className="qp-input"
                  data-testid="qpaper-subject-input"
                />
              </div>
              <div>
                <label className="qp-label">Class (optional)</label>
                <input
                  value={className}
                  onChange={(e) => setClassName(e.target.value)}
                  placeholder="e.g., 12"
                  className="qp-input"
                  data-testid="qpaper-class-input"
                />
              </div>
            </div>
            <div className="flex items-center gap-3">
              <label className="qp-btn qp-btn-secondary cursor-pointer">
                <FilePdf size={16} weight="bold" />
                {file ? file.name : "Choose PDF"}
                <input
                  ref={fileRef}
                  type="file"
                  accept="application/pdf"
                  onChange={(e) => setFile(e.target.files?.[0])}
                  className="hidden"
                  data-testid="qpaper-file-input"
                />
              </label>
              <button
                type="submit"
                disabled={uploading || !file}
                className="qp-btn qp-btn-primary"
                data-testid="qpaper-upload-submit"
              >
                <UploadSimple size={16} weight="bold" />
                {uploading ? "Extracting..." : "Extract & save"}
              </button>
            </div>
          </form>
        )}

        <div className="grid grid-cols-1 md:grid-cols-4 gap-3 mb-6">
          <div className="md:col-span-2 relative">
            <MagnifyingGlass
              size={18}
              weight="bold"
              className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-500"
            />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search questions..."
              className="qp-input pl-10"
              data-testid="qbank-search-input"
            />
          </div>
          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            className="qp-input"
            data-testid="qbank-type-filter"
          >
            <option value="">All types</option>
            <option value="information">Information</option>
            <option value="concept">Concept</option>
            <option value="application">Application</option>
          </select>
          <select
            value={difficulty}
            onChange={(e) => setDifficulty(e.target.value)}
            className="qp-input"
            data-testid="qbank-difficulty-filter"
          >
            <option value="">All difficulties</option>
            <option value="easy">Easy</option>
            <option value="medium">Medium</option>
            <option value="hard">Hard</option>
          </select>
        </div>

        {items.length === 0 ? (
          <div className="border-2 border-black bg-white p-12 text-center">
            <Bookmark size={40} weight="duotone" className="mx-auto" />
            <div className="font-display text-2xl mt-3">No saved questions</div>
            <div className="text-sm text-neutral-500 mt-1">
              Save questions from a paper, or upload an existing paper to populate your bank.
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            {items.map((q) => (
              <div
                key={q.id}
                className="border-2 border-black bg-white p-4 flex items-start gap-3"
                data-testid={`qbank-item-${q.id}`}
              >
                <div className="flex-1">
                  <div className="font-body">{q.question}</div>
                  <div className="flex flex-wrap gap-1 mt-2">
                    <span className="qp-badge qp-badge-blue">{q.type}</span>
                    <span className="qp-badge">{q.difficulty}</span>
                    <span className="qp-badge">{q.marks} marks</span>
                    {q.subject && (
                      <span className="qp-badge">{q.subject}</span>
                    )}
                    {q.class_name && (
                      <span className="qp-badge">Class {q.class_name}</span>
                    )}
                    {q.source === "uploaded" && (
                      <span className="qp-badge qp-badge-yellow">Uploaded</span>
                    )}
                  </div>
                </div>
                <button
                  onClick={() => remove(q.id)}
                  className="qp-btn qp-btn-secondary text-xs"
                  aria-label="Delete"
                  data-testid={`qbank-delete-${q.id}`}
                >
                  <Trash size={14} weight="bold" />
                </button>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
