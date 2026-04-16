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
} from "@phosphor-icons/react";

const typeBadge = (t) => {
  if (t === "information") return "qp-badge qp-badge-blue";
  if (t === "application") return "qp-badge qp-badge-red";
  return "qp-badge qp-badge-yellow";
};

export default function PaperView() {
  const { id } = useParams();
  const [paper, setPaper] = useState(null);
  const [downloading, setDownloading] = useState(false);

  const load = async () => {
    const { data } = await api.get(`/papers/${id}`);
    setPaper(data);
  };

  useEffect(() => {
    load();
  }, [id]); // eslint-disable-line

  const toggleImportant = async (qid) => {
    try {
      const { data } = await api.patch(
        `/papers/${id}/question/${qid}/toggle-important`
      );
      setPaper({ ...paper, sections: data.sections });
    } catch (err) {
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
    setDownloading(true);
    try {
      const token = localStorage.getItem("qp_token");
      const resp = await fetch(`${API}/papers/${id}/pdf`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!resp.ok) throw new Error("Download failed");
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${paper.title}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      toast.error("Download failed");
    } finally {
      setDownloading(false);
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
            <button
              onClick={() => window.print()}
              className="qp-btn qp-btn-secondary"
              data-testid="print-button"
            >
              <Printer size={16} weight="bold" /> Print
            </button>
            <button
              onClick={download}
              disabled={downloading}
              className="qp-btn qp-btn-primary"
              data-testid="download-pdf-button"
            >
              <Download size={16} weight="bold" />
              {downloading ? "Downloading..." : "Download PDF"}
            </button>
          </div>
        </div>

        {/* Paper */}
        <div
          className="bg-white border-2 border-black p-8 md:p-12 hard-shadow-static-lg"
          data-testid="paper-preview"
        >
          <div className="text-center border-b-2 border-black pb-6 mb-6">
            <h1 className="font-display text-3xl md:text-4xl">{paper.title}</h1>
            <div className="mt-3 font-mono text-sm text-neutral-700">
              Class <b>{paper.class_name}</b> · Subject <b>{paper.subject}</b>
            </div>
            <div className="mt-1 font-mono text-sm text-neutral-700">
              Total Marks: <b>{paper.total_marks}</b> · Duration:{" "}
              <b>{paper.duration_minutes} min</b> · Difficulty:{" "}
              <b className="uppercase">{paper.difficulty}</b>
            </div>
          </div>

          {paper.instructions && (
            <div className="mb-6 border border-neutral-300 bg-neutral-50 p-4 text-sm">
              <span className="font-bold">Instructions: </span>
              {paper.instructions}
            </div>
          )}

          {(paper.sections || []).map((section, si) => (
            <section key={si} className="mb-8" data-testid={`section-${si}`}>
              <h2 className="font-display text-xl md:text-2xl text-[#002FA7] mb-4 border-b border-neutral-300 pb-2">
                {section.title}
              </h2>
              <ol className="space-y-4">
                {(section.questions || []).map((q) => {
                  const qNum = counter++;
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
                          <span className="flex-1">{q.question}</span>
                          <span className="font-mono font-bold text-sm shrink-0">
                            [{q.marks}]
                          </span>
                        </div>
                        <div className="mt-2 flex flex-wrap gap-1 pl-6">
                          <span className={typeBadge(q.type)}>{q.type}</span>
                          <span className="qp-badge">{q.difficulty}</span>
                        </div>
                      </div>
                      <div className="no-print flex gap-1 pl-6 md:pl-0">
                        <button
                          onClick={() => toggleImportant(q.id)}
                          className={`qp-btn ${
                            q.important
                              ? "qp-btn-primary"
                              : "qp-btn-secondary"
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
