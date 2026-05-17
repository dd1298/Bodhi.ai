import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import Header from "@/components/Header";
import { toast } from "sonner";
import { ArrowRight, BookOpen, Sparkle } from "@phosphor-icons/react";

const DIFF = ["easy", "medium", "hard"];

export default function NewMockTest() {
  const navigate = useNavigate();
  const [books, setBooks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [bookId, setBookId] = useState("");
  const [selectedTopics, setSelectedTopics] = useState(new Set());
  const [difficulty, setDifficulty] = useState("medium");
  const [questionCount, setQuestionCount] = useState(10);
  const [duration, setDuration] = useState(20);

  useEffect(() => {
    api
      .get("/student/textbooks")
      .then((r) => {
        setBooks(r.data || []);
        if (r.data?.[0]) setBookId(r.data[0].id);
      })
      .catch(() => toast.error("Could not load practice library"))
      .finally(() => setLoading(false));
  }, []);

  const book = useMemo(() => books.find((b) => b.id === bookId), [books, bookId]);
  const topicNames = useMemo(() => {
    if (!book?.topics) return [];
    return book.topics.flatMap((t) => (t?.name ? [t.name] : []));
  }, [book]);

  useEffect(() => {
    // Default-select all topics whenever the book changes.
    setSelectedTopics(new Set(topicNames));
  }, [topicNames]);

  const toggleTopic = (name) => {
    setSelectedTopics((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  const onSubmit = async (e) => {
    e.preventDefault();
    if (!bookId) return toast.error("Pick a textbook first");
    if (selectedTopics.size === 0) return toast.error("Pick at least one topic");
    setSubmitting(true);
    try {
      const { data } = await api.post("/student/mock-tests", {
        textbook_ids: [bookId],
        topics: Array.from(selectedTopics),
        subject: book?.subject || "",
        class_name: book?.class_name || "",
        difficulty,
        question_count: questionCount,
        duration_minutes: duration,
      });
      toast.success("Generating your mock test…");
      navigate(`/student/mock-tests/${data.id}`);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not create mock test");
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-[#FAFAFA]">
        <Header />
        <main className="max-w-3xl mx-auto p-12 text-neutral-500">Loading…</main>
      </div>
    );
  }

  if (books.length === 0) {
    return (
      <div className="min-h-screen bg-[#FAFAFA]">
        <Header />
        <main className="max-w-3xl mx-auto p-12">
          <div
            className="border-2 border-dashed border-neutral-300 p-10 text-center bg-white"
            data-testid="empty-library-card"
          >
            <BookOpen size={36} className="mx-auto text-neutral-400 mb-3" />
            <h2 className="font-display text-3xl mb-2">No practice books yet.</h2>
            <p className="text-neutral-600 text-sm">
              Ask your teacher or institute admin to share textbooks for practice.
            </p>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#FAFAFA]">
      <Header />
      <main className="max-w-3xl mx-auto p-6 md:p-12">
        <div className="overline text-neutral-500 mb-2">// NEW MOCK TEST</div>
        <h1 className="font-display text-5xl mb-2">Design your practice.</h1>
        <p className="text-neutral-600 mb-8">
          Pick a textbook and topics, choose difficulty and duration. We'll
          generate 100% MCQs and auto-grade them at submit.
        </p>

        <form
          onSubmit={onSubmit}
          className="qp-card hard-shadow-static space-y-6"
          data-testid="new-mock-test-form"
        >
          <div>
            <label className="qp-label">Textbook</label>
            <select
              value={bookId}
              onChange={(e) => setBookId(e.target.value)}
              className="qp-input"
              data-testid="mock-textbook-select"
            >
              {books.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.original_filename} — {b.subject} (Class {b.class_name})
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="qp-label">
              Topics ({selectedTopics.size}/{topicNames.length} selected)
            </label>
            <div
              className="border-2 border-black p-3 max-h-64 overflow-y-auto bg-white"
              data-testid="mock-topics-list"
            >
              {topicNames.length === 0 ? (
                <div className="text-sm text-neutral-500">
                  This textbook has no topics extracted yet.
                </div>
              ) : (
                topicNames.map((name) => (
                  <label
                    key={name}
                    className="flex items-center gap-2 py-1 cursor-pointer hover:bg-neutral-50 px-2"
                  >
                    <input
                      type="checkbox"
                      checked={selectedTopics.has(name)}
                      onChange={() => toggleTopic(name)}
                      data-testid={`mock-topic-${name}`}
                    />
                    <span className="text-sm">{name}</span>
                  </label>
                ))
              )}
            </div>
          </div>

          <div className="grid md:grid-cols-3 gap-4">
            <div>
              <label className="qp-label">Difficulty</label>
              <div className="flex border-2 border-black">
                {DIFF.map((d, i) => (
                  <button
                    type="button"
                    key={d}
                    onClick={() => setDifficulty(d)}
                    data-testid={`mock-diff-${d}`}
                    className={`flex-1 py-2 text-xs font-bold uppercase ${
                      difficulty === d
                        ? "bg-black text-white"
                        : "bg-white text-black"
                    } ${i < DIFF.length - 1 ? "border-r-2 border-black" : ""}`}
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
                max={40}
                value={questionCount}
                onChange={(e) => setQuestionCount(parseInt(e.target.value, 10) || 0)}
                className="qp-input"
                data-testid="mock-question-count"
              />
            </div>
            <div>
              <label className="qp-label">Duration (min)</label>
              <input
                type="number"
                min={5}
                max={180}
                value={duration}
                onChange={(e) => setDuration(parseInt(e.target.value, 10) || 0)}
                className="qp-input"
                data-testid="mock-duration"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={submitting}
            className="qp-btn qp-btn-primary w-full"
            data-testid="mock-create-submit"
          >
            <Sparkle size={16} weight="bold" />
            {submitting ? "Creating…" : "Generate mock test"}
            <ArrowRight size={16} weight="bold" />
          </button>
        </form>
      </main>
    </div>
  );
}
