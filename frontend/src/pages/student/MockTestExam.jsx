import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "@/lib/api";
import Header from "@/components/Header";
import { toast } from "sonner";
import MathText from "@/components/MathText";
import {
  Clock,
  ArrowLeft,
  ArrowRight,
  CheckCircle,
  Spinner,
  Warning,
  Flag,
} from "@phosphor-icons/react";

const formatTime = (sec) => {
  if (sec == null || sec < 0) sec = 0;
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
};

export default function MockTestExam() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [test, setTest] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeIdx, setActiveIdx] = useState(0);
  const [answers, setAnswers] = useState({}); // {qid: selected_option}
  const [secondsLeft, setSecondsLeft] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const dirtyRef = useRef(new Set()); // qids needing save
  const submittedRef = useRef(false);

  // Flatten all questions across sections for navigation.
  const allQs = useMemo(() => {
    if (!test?.paper?.sections) return [];
    return test.paper.sections.flatMap((s) => s.questions || []);
  }, [test]);

  const fetchTest = useCallback(async () => {
    const { data } = await api.get(`/student/mock-tests/${id}`);
    setTest(data);
    // Hydrate local answers from server state.
    if (data.answers) {
      const local = {};
      Object.entries(data.answers).forEach(([qid, a]) => {
        if (a && a.selected_option != null) local[qid] = a.selected_option;
      });
      setAnswers((prev) => ({ ...local, ...prev }));
    }
    return data;
  }, [id]);

  // Initial load + polling while paper is still generating.
  useEffect(() => {
    let active = true;
    const pollGen = async () => {
      try {
        const data = await fetchTest();
        if (!active) return;
        if (data.paper?.generation_status === "pending") {
          setTimeout(pollGen, 3000);
        } else {
          setLoading(false);
        }
      } catch (err) {
        if (active) {
          toast.error("Could not load mock test");
          setLoading(false);
        }
      }
    };
    pollGen();
    return () => {
      active = false;
    };
  }, [fetchTest]);

  // Timer countdown derived from server's ends_at to avoid drift.
  useEffect(() => {
    if (test?.status !== "in_progress" || !test?.ends_at) {
      setSecondsLeft(null);
      return;
    }
    const tick = () => {
      const left = Math.max(
        0,
        Math.round((new Date(test.ends_at).getTime() - Date.now()) / 1000)
      );
      setSecondsLeft(left);
      if (left === 0 && !submittedRef.current) {
        submittedRef.current = true;
        toast.warning("Time's up — submitting your answers…");
        submit(true);
      }
    };
    tick();
    const iv = setInterval(tick, 1000);
    return () => clearInterval(iv);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [test?.status, test?.ends_at]);

  // Autosave: flush dirty answers every 3s.
  useEffect(() => {
    if (test?.status !== "in_progress") return;
    const iv = setInterval(async () => {
      if (dirtyRef.current.size === 0) return;
      const batch = Array.from(dirtyRef.current).map((qid) => ({
        question_id: qid,
        selected_option: answers[qid] ?? null,
        text_answer: "",
      }));
      dirtyRef.current.clear();
      try {
        await api.patch(`/student/mock-tests/${id}/answers`, { answers: batch });
      } catch (err) {
        // Re-queue on failure, so next tick retries.
        batch.forEach((b) => dirtyRef.current.add(b.question_id));
      }
    }, 3000);
    return () => clearInterval(iv);
  }, [test?.status, answers, id]);

  const startTest = async () => {
    try {
      const { data } = await api.post(`/student/mock-tests/${id}/start`);
      setTest((prev) => ({ ...(prev || {}), ...data, paper: prev?.paper }));
      toast.success("Timer started — good luck!");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not start test");
    }
  };

  const pickOption = (qid, optIdx) => {
    setAnswers((prev) => ({ ...prev, [qid]: optIdx }));
    dirtyRef.current.add(qid);
  };

  const flushAndSubmit = async () => {
    if (dirtyRef.current.size > 0) {
      const batch = Array.from(dirtyRef.current).map((qid) => ({
        question_id: qid,
        selected_option: answers[qid] ?? null,
        text_answer: "",
      }));
      dirtyRef.current.clear();
      try {
        await api.patch(`/student/mock-tests/${id}/answers`, { answers: batch });
      } catch (err) {
        // proceed anyway; backend has whatever was saved last
      }
    }
  };

  const submit = async (silent = false) => {
    if (submitting) return;
    setSubmitting(true);
    try {
      await flushAndSubmit();
      await api.post(`/student/mock-tests/${id}/submit`);
      if (!silent) toast.success("Submitted — let's see your result");
      navigate(`/student/mock-tests/${id}/result`);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not submit");
    } finally {
      setSubmitting(false);
    }
  };

  if (loading || !test) {
    return (
      <div className="min-h-screen bg-[#FAFAFA]">
        <Header />
        <main className="max-w-3xl mx-auto p-12 text-neutral-500">Loading…</main>
      </div>
    );
  }

  // Paper still being generated (background LLM job).
  if (test.paper?.generation_status === "pending") {
    return (
      <div className="min-h-screen bg-[#FAFAFA]">
        <Header />
        <main className="max-w-2xl mx-auto p-12 text-center">
          <Spinner size={48} className="animate-spin mx-auto text-[#002FA7] mb-4" />
          <h2 className="font-display text-3xl mb-2">
            Drafting your questions…
          </h2>
          <p className="text-neutral-600 text-sm">
            This usually takes 15-30 seconds. We'll auto-refresh.
          </p>
        </main>
      </div>
    );
  }

  if (test.paper?.generation_status === "failed") {
    return (
      <div className="min-h-screen bg-[#FAFAFA]">
        <Header />
        <main className="max-w-2xl mx-auto p-12">
          <div className="border-2 border-red-300 bg-red-50 p-8" data-testid="mock-test-failed">
            <Warning size={28} className="text-red-700 mb-3" />
            <h2 className="font-display text-3xl text-red-900 mb-2">
              Question generation failed
            </h2>
            <p className="text-sm text-red-800 mb-4 font-mono break-words">
              {test.paper?.generation_error || "Unknown error"}
            </p>
            <button
              onClick={() => navigate("/student/mock-tests/new")}
              className="qp-btn qp-btn-primary"
              data-testid="mock-test-failed-new"
            >
              Start a new mock test <ArrowRight size={16} weight="bold" />
            </button>
          </div>
        </main>
      </div>
    );
  }

  // Submitted? Redirect to result.
  if (test.status === "submitted") {
    navigate(`/student/mock-tests/${id}/result`, { replace: true });
    return null;
  }

  // Not started yet — show the start screen.
  if (test.status === "not_started") {
    return (
      <div className="min-h-screen bg-[#FAFAFA]">
        <Header />
        <main className="max-w-2xl mx-auto p-6 md:p-12">
          <div className="qp-card hard-shadow-static" data-testid="mock-test-start-card">
            <div className="overline text-neutral-500 mb-2">// READY TO START</div>
            <h1 className="font-display text-4xl mb-2">
              {test.paper?.title || "Mock Test"}
            </h1>
            <p className="text-neutral-600 mb-6 text-sm">
              {test.paper?.subject} · Class {test.paper?.class_name}
            </p>
            <div className="grid grid-cols-3 gap-2 text-center mb-8 border-2 border-black">
              <div className="p-4 border-r-2 border-black">
                <div className="overline text-neutral-500">Questions</div>
                <div className="font-display text-3xl">{allQs.length}</div>
              </div>
              <div className="p-4 border-r-2 border-black">
                <div className="overline text-neutral-500">Duration</div>
                <div className="font-display text-3xl">
                  {test.duration_minutes}
                  <span className="text-base ml-1">min</span>
                </div>
              </div>
              <div className="p-4">
                <div className="overline text-neutral-500">Marks</div>
                <div className="font-display text-3xl">
                  {test.paper?.total_marks || allQs.length}
                </div>
              </div>
            </div>
            <ul className="text-sm text-neutral-600 mb-8 space-y-1 list-disc pl-5">
              <li>Timer starts the moment you click Start.</li>
              <li>Your answers autosave every few seconds.</li>
              <li>You can navigate freely between questions.</li>
              <li>When the timer runs out, your paper is auto-submitted.</li>
            </ul>
            <button
              onClick={startTest}
              className="qp-btn qp-btn-primary w-full"
              data-testid="mock-test-start-btn"
            >
              Start the test <ArrowRight size={16} weight="bold" />
            </button>
          </div>
        </main>
      </div>
    );
  }

  // In progress
  const q = allQs[activeIdx];
  const answeredCount = Object.keys(answers).filter(
    (k) => answers[k] !== null && answers[k] !== undefined
  ).length;
  const lowTime = secondsLeft != null && secondsLeft < 60;

  return (
    <div className="min-h-screen bg-[#FAFAFA]" data-testid="mock-test-exam-page">
      <Header />
      <main className="max-w-6xl mx-auto p-4 md:p-6">
        <div
          className={`flex items-center justify-between p-4 mb-4 border-2 border-black ${
            lowTime ? "bg-red-50" : "bg-white"
          }`}
          data-testid="mock-test-toolbar"
        >
          <div className="flex items-center gap-3">
            <Clock
              size={22}
              weight={lowTime ? "fill" : "regular"}
              className={lowTime ? "text-red-700" : "text-black"}
            />
            <div
              className={`font-display text-2xl ${
                lowTime ? "text-red-700" : "text-black"
              }`}
              data-testid="mock-test-timer"
            >
              {formatTime(secondsLeft)}
            </div>
          </div>
          <div className="text-xs uppercase tracking-wider font-bold text-neutral-600">
            {answeredCount} / {allQs.length} answered
          </div>
          <button
            onClick={() => submit(false)}
            disabled={submitting}
            className="qp-btn qp-btn-primary"
            data-testid="mock-test-submit-btn"
          >
            <Flag size={16} weight="bold" />
            {submitting ? "Submitting…" : "Submit"}
          </button>
        </div>

        <div className="grid md:grid-cols-[1fr_220px] gap-4">
          <div className="qp-card hard-shadow-static" data-testid="mock-test-question-card">
            <div className="overline text-neutral-500 mb-2">
              Question {activeIdx + 1} of {allQs.length}
              {q?.marks ? ` · ${q.marks} mark${q.marks === 1 ? "" : "s"}` : ""}
            </div>
            <div className="text-lg mb-6 leading-relaxed" data-testid="mock-test-question-text">
              <MathText text={q?.question || ""} />
            </div>
            {(q?.format || "").toLowerCase() === "mcq" && q?.options?.length ? (
              <div className="space-y-3">
                {q.options.map((opt, idx) => {
                  const isSelected = answers[q.id] === idx;
                  return (
                    <button
                      type="button"
                      key={idx}
                      onClick={() => pickOption(q.id, idx)}
                      data-testid={`mock-test-option-${idx}`}
                      className={`w-full text-left border-2 p-4 transition-colors flex items-start gap-3 ${
                        isSelected
                          ? "border-[#002FA7] bg-[#EEF2FF]"
                          : "border-black bg-white hover:bg-neutral-50"
                      }`}
                    >
                      <div
                        className={`w-7 h-7 border-2 flex items-center justify-center font-bold text-sm shrink-0 ${
                          isSelected
                            ? "border-[#002FA7] bg-[#002FA7] text-white"
                            : "border-black"
                        }`}
                      >
                        {String.fromCharCode(65 + idx)}
                      </div>
                      <div className="text-base">
                        <MathText text={String(opt)} />
                      </div>
                    </button>
                  );
                })}
              </div>
            ) : (
              <div className="text-sm text-neutral-500 italic">
                This question has no MCQ options (auto-grading skips it).
              </div>
            )}
            <div className="flex items-center justify-between mt-8">
              <button
                disabled={activeIdx === 0}
                onClick={() => setActiveIdx((i) => Math.max(0, i - 1))}
                className="qp-btn qp-btn-secondary disabled:opacity-40"
                data-testid="mock-test-prev"
              >
                <ArrowLeft size={16} weight="bold" /> Previous
              </button>
              <button
                disabled={activeIdx === allQs.length - 1}
                onClick={() =>
                  setActiveIdx((i) => Math.min(allQs.length - 1, i + 1))
                }
                className="qp-btn qp-btn-primary disabled:opacity-40"
                data-testid="mock-test-next"
              >
                Next <ArrowRight size={16} weight="bold" />
              </button>
            </div>
          </div>

          <aside
            className="border-2 border-black bg-white p-4 h-fit hard-shadow-static"
            data-testid="mock-test-navigator"
          >
            <div className="overline text-neutral-500 mb-3">// NAVIGATOR</div>
            <div className="grid grid-cols-5 gap-2">
              {allQs.map((qq, idx) => {
                const answered =
                  answers[qq.id] !== null && answers[qq.id] !== undefined;
                const isActive = idx === activeIdx;
                return (
                  <button
                    key={qq.id || idx}
                    onClick={() => setActiveIdx(idx)}
                    data-testid={`mock-test-nav-${idx}`}
                    className={`aspect-square text-xs font-bold border-2 transition-colors ${
                      isActive
                        ? "border-[#002FA7] bg-[#002FA7] text-white"
                        : answered
                        ? "border-green-700 bg-green-50 text-green-900"
                        : "border-black bg-white hover:bg-neutral-50"
                    }`}
                  >
                    {idx + 1}
                  </button>
                );
              })}
            </div>
            <div className="mt-4 text-[10px] text-neutral-500 space-y-1">
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 border-2 border-green-700 bg-green-50 inline-block" />
                Answered
              </div>
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 border-2 border-black bg-white inline-block" />
                Unanswered
              </div>
            </div>
          </aside>
        </div>
      </main>
    </div>
  );
}
