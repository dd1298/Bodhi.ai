import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import Header from "@/components/Header";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import {
  Plus,
  FileText,
  BookOpen,
  Bookmark,
  Clock,
  ArrowRight,
  CheckCircle,
} from "@phosphor-icons/react";

const StatCard = ({ label, value, testid }) => (
  <div
    className="border-2 border-black bg-white p-6 hard-shadow"
    data-testid={testid}
  >
    <div className="overline text-neutral-500 mb-3">{label}</div>
    <div className="font-display text-5xl leading-none">{value}</div>
  </div>
);

export default function Dashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [papers, setPapers] = useState([]);
  const [textbooks, setTextbooks] = useState([]);
  const [qbankCount, setQbankCount] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.get("/papers").then((r) => setPapers(r.data)),
      api.get("/textbooks").then((r) => setTextbooks(r.data)),
      api.get("/qbank").then((r) => setQbankCount(r.data.length)),
    ])
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="min-h-screen bg-[#FAFAFA]">
      <Header />
      <main className="max-w-7xl mx-auto p-6 md:p-12" data-testid="dashboard-page">
        {/* Hero */}
        <section className="mb-12">
          <div className="overline text-neutral-500 mb-3">
            // CONTROL ROOM / {new Date().toLocaleDateString("en-US", {
              weekday: "long",
              year: "numeric",
              month: "long",
              day: "numeric",
            })}
          </div>
          <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-6">
            <h1 className="font-display text-5xl md:text-6xl lg:text-7xl leading-[0.9]">
              Hello,
              <br />
              <span className="text-[#002FA7]">{user?.full_name?.split(" ")[0] || "there"}.</span>
            </h1>
            <Link
              to="/papers/new"
              data-testid="cta-new-paper"
              className="qp-btn qp-btn-primary text-base py-3 px-5 self-start md:self-end"
            >
              <Plus size={18} weight="bold" />
              Generate New Paper
            </Link>
          </div>
          {papers.some((p) => !p.has_solution) && false /* placeholder */}
          {papers.length > 0 && (
            <div className="mt-6">
              <button
                onClick={bulkGenerateSolutions}
                disabled={bulkBusy}
                className="qp-btn qp-btn-secondary text-xs"
                data-testid="bulk-generate-solutions-button"
              >
                <CheckCircle size={14} weight="bold" />
                {bulkBusy
                  ? "Generating solutions..."
                  : "Generate solutions for all papers without one"}
              </button>
            </div>
          )}
        </section>

        {/* Stats */}
        <section className="grid grid-cols-1 md:grid-cols-3 gap-6 md:gap-8 mb-12">
          <StatCard
            label="Textbooks Indexed"
            value={textbooks.length}
            testid="stat-textbooks"
          />
          <StatCard
            label="Papers Generated"
            value={papers.length}
            testid="stat-papers"
          />
          <StatCard
            label="Questions Saved"
            value={qbankCount}
            testid="stat-qbank"
          />
        </section>

        {/* Papers + textbooks */}
        <section className="grid grid-cols-1 lg:grid-cols-3 gap-6 md:gap-8">
          <div className="lg:col-span-2">
            <div className="flex items-center justify-between mb-4">
              <div className="overline">// RECENT PAPERS</div>
              <Link
                to="/papers/new"
                className="qp-btn-ghost text-xs uppercase tracking-wider"
                data-testid="link-new-paper"
              >
                + New
              </Link>
            </div>
            <div className="border-2 border-black bg-white">
              {loading ? (
                <div className="p-8 text-neutral-500">Loading...</div>
              ) : papers.length === 0 ? (
                <EmptyState
                  title="No papers yet"
                  description="Generate your first AI-powered question paper to see it here."
                  actionLabel="Generate Paper"
                  onAction={() => navigate("/papers/new")}
                  testid="papers-empty"
                />
              ) : (
                papers.slice(0, 8).map((p, idx) => (
                  <Link
                    to={`/papers/${p.id}`}
                    key={p.id}
                    data-testid={`paper-row-${idx}`}
                    className={`flex items-center justify-between p-4 hover:bg-neutral-50 ${
                      idx !== papers.slice(0, 8).length - 1
                        ? "border-b border-neutral-200"
                        : ""
                    }`}
                  >
                    <div className="flex items-center gap-4 min-w-0">
                      <div className="w-10 h-10 border-2 border-black flex items-center justify-center shrink-0">
                        <FileText size={18} weight="bold" />
                      </div>
                      <div className="min-w-0">
                        <div className="font-bold truncate">{p.title}</div>
                        <div className="text-xs text-neutral-500 font-mono mt-0.5">
                          {p.subject} · Class {p.class_name} · {p.total_marks}{" "}
                          marks · {p.duration_minutes} min
                        </div>
                      </div>
                    </div>
                    <ArrowRight size={18} weight="bold" className="shrink-0" />
                  </Link>
                ))
              )}
            </div>
          </div>

          <div>
            <div className="overline mb-4">// TEXTBOOKS</div>
            <div className="space-y-3">
              <Link
                to="/textbooks"
                data-testid="link-textbooks"
                className="block border-2 border-black bg-white p-4 hard-shadow"
              >
                <div className="flex items-center gap-3">
                  <BookOpen size={22} weight="bold" />
                  <div className="flex-1">
                    <div className="font-bold uppercase text-sm">
                      Manage textbooks
                    </div>
                    <div className="text-xs text-neutral-500 font-mono">
                      {textbooks.length} indexed
                    </div>
                  </div>
                  <ArrowRight size={18} weight="bold" />
                </div>
              </Link>
              <Link
                to="/qbank"
                data-testid="link-qbank"
                className="block border-2 border-black bg-white p-4 hard-shadow"
              >
                <div className="flex items-center gap-3">
                  <Bookmark size={22} weight="bold" />
                  <div className="flex-1">
                    <div className="font-bold uppercase text-sm">
                      Question Bank
                    </div>
                    <div className="text-xs text-neutral-500 font-mono">
                      {qbankCount} saved
                    </div>
                  </div>
                  <ArrowRight size={18} weight="bold" />
                </div>
              </Link>

              <div className="border-2 border-black bg-black text-white p-5">
                <Clock size={22} weight="bold" color="#FFC300" />
                <div className="font-display text-2xl mt-2 leading-tight">
                  Papers, built in minutes.
                </div>
                <div className="text-xs text-neutral-300 mt-2 font-mono">
                  Upload a textbook · Select topics · Tune distribution ·
                  Download PDF.
                </div>
              </div>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}

const EmptyState = ({ title, description, actionLabel, onAction, testid }) => (
  <div
    className="flex flex-col items-center justify-center text-center p-10"
    data-testid={testid}
  >
    <div
      className="w-32 h-32 mb-4 bg-cover bg-center opacity-60 grayscale"
      style={{
        backgroundImage:
          "url(https://images.unsplash.com/photo-1656612514884-9d33fcaa8288?crop=entropy&cs=srgb&fm=jpg&ixid=M3w3NTY2Nzd8MHwxfHNlYXJjaHwxfHxhYnN0cmFjdCUyMHdpcmVmcmFtZSUyMGFyY2hpdGVjdHVyZXxlbnwwfHx8fDE3NzYzNjkyNTl8MA&ixlib=rb-4.1.0&q=85)",
      }}
    />
    <div className="font-display text-2xl">{title}</div>
    <div className="text-neutral-500 mt-1 max-w-sm text-sm">{description}</div>
    {actionLabel && (
      <button
        onClick={onAction}
        className="qp-btn qp-btn-primary mt-5"
        data-testid={`${testid}-action`}
      >
        {actionLabel}
      </button>
    )}
  </div>
);
