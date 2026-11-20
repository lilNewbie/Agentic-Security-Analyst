"use client";

import { useEffect, useState, useRef } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import type { QuestionnaireQuestion, QuestionStatus } from "@/lib/types";

const STATUS_META: Record<QuestionStatus, { label: string; classes: string }> = {
  verified_from_documents: { label: "Verified", classes: "bg-emerald-100 text-emerald-700" },
  confirmed_by_user: { label: "Confirmed", classes: "bg-emerald-100 text-emerald-700" },
  not_applicable: { label: "N/A", classes: "bg-gray-100 text-gray-500" },
  partial: { label: "Partial", classes: "bg-amber-100 text-amber-700" },
  unknown: { label: "Unknown", classes: "bg-gray-100 text-gray-400" },
};

type FilterOption = QuestionStatus | "answered" | "all";

const FILTERS: { value: FilterOption; label: string }[] = [
  { value: "all", label: "All" },
  { value: "answered", label: "Answered" },
  { value: "partial", label: "Partial" },
  { value: "unknown", label: "Unknown" },
  { value: "not_applicable", label: "N/A" },
];

function StatusChip({ status }: { status: QuestionStatus }) {
  const { label, classes } = STATUS_META[status] ?? { label: status, classes: "bg-gray-100 text-gray-400" };
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${classes}`}>
      {label}
    </span>
  );
}

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color = pct >= 70 ? "bg-emerald-400" : pct >= 40 ? "bg-amber-400" : "bg-red-400";
  return (
    <div className="flex items-center gap-1.5">
      <div className="w-16 h-1.5 rounded-full bg-gray-100 overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-gray-400 tabular-nums">{pct}%</span>
    </div>
  );
}

function QuestionRow({ q, companyId }: { q: QuestionnaireQuestion; companyId: string }) {
  const [open, setOpen] = useState(false);
  const hasEvidence = q.evidence.length > 0;

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full text-left px-5 py-4 flex items-start gap-4 hover:bg-gray-50 transition-colors"
      >
        <span className="text-xs font-mono text-gray-400 w-7 shrink-0 mt-0.5">Q{q.question_id}</span>
        <div className="flex-1 min-w-0">
          <p className="text-sm text-gray-800 leading-snug">{q.label || `Question ${q.question_id}`}</p>
          {q.response && (
            <p className="mt-1 text-xs text-gray-500 truncate">{q.response}</p>
          )}
        </div>
        <div className="shrink-0 flex flex-col items-end gap-1.5">
          <StatusChip status={q.status} />
          {(q.status === "verified_from_documents" || q.status === "confirmed_by_user" || q.status === "partial") && (
            <ConfidenceBar value={q.confidence} />
          )}
        </div>
        <span className="text-gray-300 text-xs mt-1 shrink-0">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="border-t border-gray-100 px-5 py-4 space-y-3 bg-gray-50">
          {q.response ? (
            <div>
              <p className="text-xs font-medium text-gray-500 mb-1">Response</p>
              <p className="text-sm text-gray-800 bg-white rounded-lg border border-gray-200 px-3 py-2">
                {q.response}
              </p>
            </div>
          ) : (
            <p className="text-xs text-gray-400 italic">No response generated yet.</p>
          )}

          {hasEvidence && (
            <div>
              <p className="text-xs font-medium text-gray-500 mb-2">Evidence ({q.evidence.length})</p>
              <div className="space-y-2">
                {q.evidence.slice(0, 3).map((ev, i) => (
                  <div key={i} className="rounded-lg bg-white border border-gray-200 px-3 py-2">
                    {ev.span && (
                      <p className="text-xs text-gray-700 italic mb-1">
                        &ldquo;{ev.span.slice(0, 160)}{ev.span.length > 160 ? "…" : ""}&rdquo;
                      </p>
                    )}
                    <p className="text-xs text-gray-400">
                      {ev.date || ""}
                      {ev.page != null && ` · p.${ev.page}`}
                    </p>
                  </div>
                ))}
                {q.evidence.length > 3 && (
                  <p className="text-xs text-gray-400">+{q.evidence.length - 3} more</p>
                )}
              </div>
            </div>
          )}

          <div className="pt-1">
            <Link
              href={`/${companyId}/graph`}
              className="text-xs text-blue-500 hover:text-blue-700 transition-colors"
            >
              View in graph →
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}

function downloadCSV(questions: QuestionnaireQuestion[]) {
  const rows = [
    ["Q#", "Question", "Status", "Response", "Confidence %"],
    ...questions.map((q) => [
      String(q.question_id),
      `"${(q.label || "").replace(/"/g, '""')}"`,
      q.status,
      `"${(q.response || "").replace(/"/g, '""')}"`,
      String(Math.round(q.confidence * 100)),
    ]),
  ];
  const csv = rows.map((r) => r.join(",")).join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "questionnaire.csv";
  a.click();
  URL.revokeObjectURL(url);
}

export default function QuestionnairePage() {
  const params = useParams();
  const companyId = params.companyId as string;
  const [questions, setQuestions] = useState<QuestionnaireQuestion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<FilterOption>("all");

  useEffect(() => {
    api.getQuestionnaire(companyId)
      .then((r) => setQuestions(r.questions))
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [companyId]);

  if (loading) return <Shell><p className="text-gray-400 text-sm">Loading questionnaire…</p></Shell>;
  if (error) return <Shell><p className="text-red-500 text-sm">{error}</p></Shell>;

  const filtered = questions.filter((q) => {
    if (filter === "all") return true;
    if (filter === "answered") return q.status === "verified_from_documents" || q.status === "confirmed_by_user";
    return q.status === filter;
  });

  const answeredCount = questions.filter(
    (q) => q.status === "verified_from_documents" || q.status === "confirmed_by_user"
  ).length;
  const partialCount = questions.filter((q) => q.status === "partial").length;
  const unknownCount = questions.filter((q) => q.status === "unknown").length;

  return (
    <Shell>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-lg font-semibold text-gray-900">Questionnaire</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {answeredCount} answered · {partialCount} partial · {unknownCount} unknown · {questions.length} total
          </p>
        </div>
        <button
          onClick={() => downloadCSV(questions)}
          className="flex items-center gap-2 rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-600 hover:bg-gray-50 transition-colors"
        >
          ↓ Export CSV
        </button>
      </div>

      <div className="flex gap-1 mb-5 flex-wrap">
        {FILTERS.map((opt) => (
          <button
            key={opt.value}
            onClick={() => setFilter(opt.value)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              filter === opt.value
                ? "bg-gray-900 text-white"
                : "bg-white border border-gray-200 text-gray-600 hover:bg-gray-50"
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {filtered.length === 0 ? (
        <div className="bg-white rounded-xl border border-gray-200 p-12 text-center">
          <p className="text-gray-400 text-sm">No questions match this filter.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map((q) => (
            <QuestionRow key={q.question_id} q={q} companyId={companyId} />
          ))}
        </div>
      )}
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return <div className="p-8 max-w-4xl mx-auto">{children}</div>;
}
