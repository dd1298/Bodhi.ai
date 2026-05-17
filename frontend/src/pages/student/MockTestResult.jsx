import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "@/lib/api";
import Header from "@/components/Header";
import MathText from "@/components/MathText";
import {
  Trophy,
  CheckCircle,
  XCircle,
  ArrowLeft,
  Sparkle,
} from "@phosphor-icons/react";

const bandFor = (pct) => {
  if (pct >= 80) return { label: "Excellent", color: "text-green-700" };
  if (pct >= 60) return { label: "Good", color: "text-blue-700" };
  if (pct >= 40) return { label: "Needs review", color: "text-yellow-700" };
  return { label: "Practice more", color: "text-red-700" };
};

const TopicRow = ({ name, stats }) => {
  const pct = stats.total ? Math.round((stats.obtained / stats.total) * 100) : 0;
  const isWeak = pct < 50;
  return (
    <div
      className={`p-3 border-2 ${
        isWeak ? "border-red-300 bg-red-50" : "border-black bg-white"
      }`}
      data-testid={`result-topic-${name}`}
    >
      <div className="flex items-center justify-between mb-1">
        <div className="text-sm font-bold">{name}</div>
        <div className="text-xs font-bold">
          {stats.correct}/{stats.count} correct · {pct}%
        </div>
      </div>
      <div className="h-2 bg-neutral-200 overflow-hidden">
        <div
          className={`h-full ${isWeak ? "bg-red-500" : "bg-[#002FA7]"}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
};

export default function MockTestResult() {
  const { id } = useParams();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [practiceBusy, setPracticeBusy] = useState(false);

  useEffect(() => {
    api
      .get(`/student/mock-tests/${id}/result`)
      .then((r) => setData(r.data))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) {
    return (
      <div className="min-h-screen bg-[#FAFAFA]">
        <Header />
        <main className="max-w-3xl mx-auto p-12 text-neutral-500">Loading…</main>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="min-h-screen bg-[#FAFAFA]">
        <Header />
        <main className="max-w-3xl mx-auto p-12">
          Result not available.
        </main>
      </div>
    );
  }

  const { score, paper, answers } = data;
  const band = bandFor(score?.percent || 0);
  const allQs = (paper?.sections || []).flatMap((s) => s.questions || []);
  const weakTopics = Object.entries(score?.by_topic || {})
    .filter(([, v]) => v.total && v.obtained / v.total < 0.5)
    .map(([k]) => k);

  const startPractice = async () => {
    if (weakTopics.length === 0) return;
    setPracticeBusy(true);
    try {
      const { data: newTest } = await api.post("/student/mock-tests", {
        textbook_ids: paper.textbook_ids || [paper.textbook_id],
        topics: weakTopics,
        subject: paper.subject,
        class_name: paper.class_name,
        difficulty: paper.difficulty || "medium",
        question_count: Math.max(5, weakTopics.length * 2),
        duration_minutes: Math.max(10, weakTopics.length * 3),
      });
      window.location.href = `/student/mock-tests/${newTest.id}`;
    } catch (e) {
      setPracticeBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#FAFAFA]">
      <Header />
      <main
        className="max-w-4xl mx-auto p-6 md:p-12"
        data-testid="mock-test-result-page"
      >
        <Link
          to="/student"
          className="qp-btn-ghost inline-flex items-center gap-2 mb-8"
          data-testid="back-to-student-dashboard"
        >
          <ArrowLeft size={16} weight="bold" /> My tests
        </Link>

        <div className="border-2 border-black bg-white p-8 hard-shadow mb-8">
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div>
              <div className="overline text-neutral-500 mb-2">// RESULT</div>
              <h1 className="font-display text-4xl mb-1">{paper?.title}</h1>
              <p className="text-neutral-600 text-sm">
                {paper?.subject} · Class {paper?.class_name}
              </p>
            </div>
            <div className="text-right">
              <div className="flex items-center gap-3 justify-end">
                <Trophy size={32} weight="fill" className="text-[#FFC300]" />
                <div className="font-display text-6xl" data-testid="result-percent">
                  {score?.percent ?? 0}
                  <span className="text-2xl">%</span>
                </div>
              </div>
              <div className={`text-sm font-bold mt-1 ${band.color}`}>
                {band.label} ·{" "}
                <span data-testid="result-marks">
                  {score?.obtained}/{score?.total} marks
                </span>{" "}
                · {score?.mcq_correct}/{score?.mcq_total} MCQs correct
              </div>
            </div>
          </div>
        </div>

        <h2 className="overline text-neutral-500 mb-3">// TOPIC BREAKDOWN</h2>
        <div className="grid sm:grid-cols-2 gap-3 mb-8" data-testid="result-topic-breakdown">
          {Object.entries(score?.by_topic || {}).map(([name, stats]) => (
            <TopicRow key={name} name={name} stats={stats} />
          ))}
        </div>

        {weakTopics.length > 0 && (
          <div
            className="border-2 border-[#002FA7] bg-[#EEF2FF] p-5 mb-8 flex items-center justify-between flex-wrap gap-4"
            data-testid="result-practice-cta"
          >
            <div>
              <div className="font-bold mb-1 flex items-center gap-2">
                <Sparkle size={18} weight="fill" className="text-[#002FA7]" />
                Practice recommendation
              </div>
              <div className="text-sm text-neutral-700">
                You're below 50% on {weakTopics.length} topic
                {weakTopics.length === 1 ? "" : "s"}:{" "}
                <span className="font-bold">{weakTopics.join(", ")}</span>. Drill them
                with a focused practice set?
              </div>
            </div>
            <button
              onClick={startPractice}
              disabled={practiceBusy}
              className="qp-btn qp-btn-primary"
              data-testid="result-practice-btn"
            >
              {practiceBusy ? "Generating…" : "Start practice drill"}
            </button>
          </div>
        )}

        <h2 className="overline text-neutral-500 mb-3">// QUESTION REVIEW</h2>
        <div className="space-y-4">
          {allQs.map((q, idx) => {
            const ans = (answers || {})[q.id] || {};
            const selected = ans.selected_option;
            const correct = q.correct_option;
            const isCorrect =
              selected != null && correct != null && Number(selected) === Number(correct);
            return (
              <div
                key={q.id || idx}
                className={`border-2 p-5 bg-white ${
                  isCorrect ? "border-green-700" : selected == null ? "border-neutral-300" : "border-red-500"
                }`}
                data-testid={`result-question-${idx}`}
              >
                <div className="flex items-start gap-3 mb-3">
                  {isCorrect ? (
                    <CheckCircle size={22} weight="fill" className="text-green-700 shrink-0 mt-1" />
                  ) : (
                    <XCircle size={22} weight="fill" className="text-red-500 shrink-0 mt-1" />
                  )}
                  <div className="text-base font-bold flex-1">
                    Q{idx + 1}. <MathText text={q.question || ""} />
                  </div>
                </div>
                {q.options?.length ? (
                  <div className="space-y-1.5 ml-7">
                    {q.options.map((opt, oi) => {
                      const isAns = oi === correct;
                      const isPick = oi === selected;
                      return (
                        <div
                          key={oi}
                          className={`text-sm flex items-center gap-2 p-2 border ${
                            isAns
                              ? "border-green-700 bg-green-50"
                              : isPick && !isAns
                              ? "border-red-500 bg-red-50"
                              : "border-neutral-200"
                          }`}
                        >
                          <span className="font-bold w-5">
                            {String.fromCharCode(65 + oi)}.
                          </span>
                          <span className="flex-1">
                            <MathText text={String(opt)} />
                          </span>
                          {isAns && (
                            <span className="text-xs font-bold text-green-700 uppercase">
                              Correct
                            </span>
                          )}
                          {isPick && !isAns && (
                            <span className="text-xs font-bold text-red-600 uppercase">
                              Your pick
                            </span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      </main>
    </div>
  );
}
