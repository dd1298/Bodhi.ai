import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import Header from "@/components/Header";
import { useAuth } from "@/context/AuthContext";
import {
  Plus,
  Clock,
  CheckCircle,
  ArrowRight,
  Hourglass,
  Trophy,
} from "@phosphor-icons/react";

const StatusPill = ({ status }) => {
  const map = {
    not_started: { label: "Ready to start", bg: "bg-yellow-100", color: "text-yellow-900" },
    in_progress: { label: "In progress", bg: "bg-blue-100", color: "text-blue-900" },
    submitted: { label: "Submitted", bg: "bg-green-100", color: "text-green-900" },
    expired: { label: "Expired", bg: "bg-red-100", color: "text-red-900" },
  };
  const s = map[status] || { label: status, bg: "bg-neutral-100", color: "text-neutral-700" };
  return (
    <span
      className={`px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${s.bg} ${s.color}`}
      data-testid={`mock-status-${status}`}
    >
      {s.label}
    </span>
  );
};

export default function StudentDashboard() {
  const { user } = useAuth();
  const [tests, setTests] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const { data } = await api.get("/student/mock-tests");
        if (!cancelled) setTests(data || []);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    const poll = setInterval(load, 6000);
    return () => {
      cancelled = true;
      clearInterval(poll);
    };
  }, []);

  const submitted = tests.filter((t) => t.status === "submitted");
  const avgPct = submitted.length
    ? Math.round(
        submitted.reduce((sum, t) => sum + (t.score?.percent || 0), 0) /
          submitted.length
      )
    : null;

  return (
    <div className="min-h-screen bg-[#FAFAFA]">
      <Header />
      <main
        className="max-w-6xl mx-auto p-6 md:p-12"
        data-testid="student-dashboard"
      >
        <div className="flex items-end justify-between flex-wrap gap-4 mb-10">
          <div>
            <div className="overline text-neutral-500 mb-2">// STUDENT</div>
            <h1 className="font-display text-5xl">
              Welcome back, <span className="text-[#002FA7]">{user?.full_name?.split(" ")[0] || "learner"}.</span>
            </h1>
            <p className="text-neutral-600 mt-2">
              Sharpen any topic with a timed practice paper, graded instantly.
            </p>
          </div>
          <Link
            to="/student/mock-tests/new"
            data-testid="cta-new-mock-test"
            className="qp-btn qp-btn-primary"
          >
            <Plus size={16} weight="bold" /> New mock test
          </Link>
        </div>

        <div className="grid sm:grid-cols-3 gap-4 mb-10">
          <div className="border-2 border-black bg-white p-6 hard-shadow" data-testid="stat-total-tests">
            <div className="overline text-neutral-500 mb-2">Total tests</div>
            <div className="font-display text-5xl">{tests.length}</div>
          </div>
          <div className="border-2 border-black bg-white p-6 hard-shadow" data-testid="stat-submitted-tests">
            <div className="overline text-neutral-500 mb-2">Submitted</div>
            <div className="font-display text-5xl">{submitted.length}</div>
          </div>
          <div className="border-2 border-black bg-white p-6 hard-shadow" data-testid="stat-avg-score">
            <div className="overline text-neutral-500 mb-2">Avg score</div>
            <div className="font-display text-5xl">
              {avgPct == null ? "—" : `${avgPct}%`}
            </div>
          </div>
        </div>

        <div className="overline text-neutral-500 mb-3">// YOUR TESTS</div>
        {loading ? (
          <div className="text-neutral-500 text-sm">Loading…</div>
        ) : tests.length === 0 ? (
          <div className="border-2 border-dashed border-neutral-300 p-12 text-center bg-white">
            <Hourglass size={32} className="mx-auto text-neutral-400 mb-3" />
            <p className="text-neutral-600 mb-4">
              You haven't taken any mock tests yet.
            </p>
            <Link
              to="/student/mock-tests/new"
              data-testid="cta-new-mock-empty"
              className="qp-btn qp-btn-primary"
            >
              Start your first test <ArrowRight size={16} weight="bold" />
            </Link>
          </div>
        ) : (
          <div className="space-y-3">
            {tests.map((t) => (
              <Link
                key={t.id}
                to={`/student/mock-tests/${t.id}`}
                data-testid={`mock-test-card-${t.id}`}
                className="block border-2 border-black bg-white p-5 hard-shadow hover:bg-neutral-50 transition-colors"
              >
                <div className="flex items-start justify-between gap-4 flex-wrap">
                  <div>
                    <div className="flex items-center gap-3 mb-1">
                      <StatusPill status={t.status} />
                      {t.paper?.generation_status === "pending" && (
                        <span className="text-xs text-neutral-500">
                          Generating questions…
                        </span>
                      )}
                    </div>
                    <h3 className="font-display text-2xl leading-tight">
                      {t.paper?.title || "Mock Test"}
                    </h3>
                    <div className="text-xs text-neutral-600 mt-1">
                      {t.paper?.subject} · Class {t.paper?.class_name} ·{" "}
                      {t.duration_minutes} min · {t.question_count} questions
                    </div>
                  </div>
                  <div className="text-right">
                    {t.status === "submitted" && t.score ? (
                      <div className="flex items-center gap-2">
                        <Trophy size={20} weight="fill" className="text-[#FFC300]" />
                        <div>
                          <div className="font-display text-2xl leading-none">
                            {t.score.percent}%
                          </div>
                          <div className="text-xs text-neutral-500">
                            {t.score.obtained}/{t.score.total} marks
                          </div>
                        </div>
                      </div>
                    ) : t.status === "in_progress" ? (
                      <div className="flex items-center gap-2 text-blue-700">
                        <Clock size={16} weight="bold" />
                        <span className="font-bold text-sm">Resume</span>
                      </div>
                    ) : t.status === "not_started" ? (
                      <div className="flex items-center gap-2 text-green-700">
                        <CheckCircle size={16} weight="bold" />
                        <span className="font-bold text-sm">Start</span>
                      </div>
                    ) : null}
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
