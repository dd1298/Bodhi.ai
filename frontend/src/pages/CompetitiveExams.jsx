import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import Header from "@/components/Header";
import { toast } from "sonner";
import {
  Plus,
  Trophy,
  ArrowRight,
  Books,
} from "@phosphor-icons/react";

export default function CompetitiveExams() {
  const [exams, setExams] = useState([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ name: "", description: "", is_shared: true });

  const load = async () => {
    try {
      const { data } = await api.get("/competitive-exams");
      setExams(data || []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const create = async (e) => {
    e.preventDefault();
    if (!form.name.trim()) return toast.error("Name required");
    setCreating(true);
    try {
      await api.post("/competitive-exams", form);
      toast.success("Exam created");
      setForm({ name: "", description: "", is_shared: true });
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not create exam");
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#FAFAFA]">
      <Header />
      <main className="max-w-6xl mx-auto p-6 md:p-12" data-testid="competitive-exams-page">
        <div className="flex items-end justify-between flex-wrap gap-4 mb-10">
          <div>
            <div className="overline text-neutral-500 mb-2">// COMPETITIVE EXAMS</div>
            <h1 className="font-display text-5xl">
              Train against <span className="text-[#002FA7]">past papers.</span>
            </h1>
            <p className="text-neutral-600 mt-2 max-w-xl">
              Upload past papers for any competitive exam (JEE, NEET, CAT, GATE…).
              Generated practice papers will be difficulty-calibrated by similarity
              search across what you've uploaded — RAG, in the open.
            </p>
          </div>
        </div>

        <div className="grid lg:grid-cols-[1fr_360px] gap-6">
          <div>
            <div className="overline text-neutral-500 mb-3">// YOUR LIBRARY</div>
            {loading ? (
              <div className="text-neutral-500 text-sm">Loading…</div>
            ) : exams.length === 0 ? (
              <div className="border-2 border-dashed border-neutral-300 p-12 text-center bg-white">
                <Books size={36} className="mx-auto text-neutral-400 mb-3" />
                <p className="text-neutral-600 text-sm">
                  No competitive exam libraries yet. Create your first one on the right.
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {exams.map((e) => (
                  <Link
                    key={e.id}
                    to={`/competitive-exams/${e.id}`}
                    data-testid={`exam-card-${e.id}`}
                    className="block border-2 border-black bg-white p-5 hard-shadow hover:bg-neutral-50 transition-colors"
                  >
                    <div className="flex items-start justify-between gap-4 flex-wrap">
                      <div>
                        <div className="flex items-center gap-2 mb-1">
                          <Trophy size={18} weight="fill" className="text-[#FFC300]" />
                          <h3 className="font-display text-2xl leading-tight">{e.name}</h3>
                          {e.is_shared && (
                            <span className="px-2 py-0.5 text-[10px] font-bold uppercase bg-[#EEF2FF] text-[#002FA7]">
                              Shared
                            </span>
                          )}
                        </div>
                        {e.description && (
                          <p className="text-sm text-neutral-600">{e.description}</p>
                        )}
                        <div className="text-xs text-neutral-500 mt-2">
                          {e.papers_count || 0} past paper(s) ·{" "}
                          {e.questions_count || 0} question(s) indexed
                        </div>
                      </div>
                      <ArrowRight size={20} weight="bold" className="text-neutral-400" />
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </div>

          <aside>
            <form
              onSubmit={create}
              className="qp-card hard-shadow-static"
              data-testid="new-exam-form"
            >
              <div className="overline text-neutral-500 mb-2">// NEW EXAM</div>
              <h3 className="font-display text-2xl mb-3">Create exam</h3>
              <div className="mb-3">
                <label className="qp-label">Name</label>
                <input
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  className="qp-input"
                  placeholder="JEE Main 2026"
                  data-testid="new-exam-name"
                />
              </div>
              <div className="mb-3">
                <label className="qp-label">Description</label>
                <textarea
                  value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })}
                  className="qp-input"
                  rows={3}
                  placeholder="Physics + Chemistry + Maths…"
                  data-testid="new-exam-description"
                />
              </div>
              <label className="flex items-center gap-2 text-sm mb-4">
                <input
                  type="checkbox"
                  checked={form.is_shared}
                  onChange={(e) => setForm({ ...form, is_shared: e.target.checked })}
                  data-testid="new-exam-shared"
                />
                Visible to students
              </label>
              <button
                type="submit"
                disabled={creating}
                className="qp-btn qp-btn-primary w-full"
                data-testid="new-exam-submit"
              >
                <Plus size={16} weight="bold" /> {creating ? "Creating…" : "Create exam"}
              </button>
            </form>
          </aside>
        </div>
      </main>
    </div>
  );
}
