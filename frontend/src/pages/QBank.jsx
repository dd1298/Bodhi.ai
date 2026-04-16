import React, { useEffect, useState } from "react";
import { api } from "@/lib/api";
import Header from "@/components/Header";
import { toast } from "sonner";
import { MagnifyingGlass, Trash, Bookmark } from "@phosphor-icons/react";

export default function QBank() {
  const [items, setItems] = useState([]);
  const [q, setQ] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [difficulty, setDifficulty] = useState("");

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

  return (
    <div className="min-h-screen bg-[#FAFAFA]">
      <Header />
      <main className="max-w-7xl mx-auto p-6 md:p-12" data-testid="qbank-page">
        <div className="overline text-neutral-500 mb-3">// QUESTION BANK</div>
        <h1 className="font-display text-5xl md:text-6xl mb-10">
          Saved
          <br />
          <span className="text-[#002FA7]">questions.</span>
        </h1>

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
              Save questions from generated papers to build your bank.
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
