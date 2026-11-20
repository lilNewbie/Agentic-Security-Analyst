"use client";

"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { StateChip } from "@/components/StateChip";
import type { AnalystReport, ReportThemeScore, ReportRisk } from "@/lib/types";

const THEME_DISPLAY: Record<string, string> = {
  data_security: "Data Security",
  asset_management: "Asset Management",
  incident_response: "Incident Response",
  vulnerability_mgmt: "Vulnerability Mgmt",
  network_endpoint: "Network & Endpoint",
  web_app_security: "Web App Security",
  bcdr: "BC/DR",
  risk_assessment: "Risk Assessment",
  privacy: "Privacy",
  governance: "Governance",
  secure_coding: "Secure Coding",
  third_party_risk: "Third Party Risk",
  training: "Training",
  physical_security: "Physical Security",
};

function scoreColor(score: number) {
  if (score >= 0.7) return { ring: "text-emerald-500", bg: "bg-emerald-50", bar: "bg-emerald-400" };
  if (score >= 0.4) return { ring: "text-amber-500", bg: "bg-amber-50", bar: "bg-amber-400" };
  return { ring: "text-red-500", bg: "bg-red-50", bar: "bg-red-400" };
}

function PostureGauge({ score, answered, applicable }: { score: number; answered: number; applicable: number }) {
  const pct = Math.round(score * 100);
  const c = scoreColor(score);
  const circumference = 2 * Math.PI * 40;
  const offset = circumference * (1 - score);

  return (
    <div className={`rounded-2xl border border-gray-200 p-8 flex flex-col items-center ${c.bg} print:border-gray-300`}>
      <svg width="120" height="120" className="mb-4" style={{ transform: "rotate(-90deg)" }}>
        <circle cx="60" cy="60" r="40" fill="none" stroke="#e5e7eb" strokeWidth="10" />
        <circle
          cx="60" cy="60" r="40" fill="none"
          stroke="currentColor"
          strokeWidth="10"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          className={c.ring}
          style={{ transition: "stroke-dashoffset 0.6s ease" }}
        />
      </svg>
      <p className={`text-4xl font-bold ${c.ring} -mt-2`}>{pct}%</p>
      <p className="text-sm text-gray-600 mt-1 font-medium">Security Posture</p>
      <p className="text-xs text-gray-400 mt-1">{answered} of {applicable} rubrics answered</p>
    </div>
  );
}

function ThemeRow({ t }: { t: ReportThemeScore }) {
  const pct = Math.round(t.score * 100);
  const c = scoreColor(t.score);
  return (
    <div className="py-3 border-b border-gray-100 last:border-0">
      <div className="flex items-center gap-3 mb-1.5">
        <span className="text-sm text-gray-700 w-44 shrink-0">
          {THEME_DISPLAY[t.theme] ?? t.display_name}
        </span>
        <div className="flex-1 h-2 rounded-full bg-gray-100 overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-500 ${c.bar}`}
            style={{ width: `${pct}%` }}
          />
        </div>
        <span className="text-xs font-medium text-gray-500 w-10 text-right tabular-nums">{pct}%</span>
        <span className="text-xs text-gray-400 w-16 text-right tabular-nums">
          {t.answered}/{t.applicable}
        </span>
      </div>
      {t.top_gaps.length > 0 && (
        <div className="ml-44 pl-3 space-y-0.5">
          {t.top_gaps.map((g) => (
            <p key={g.rubric_id} className="text-xs text-gray-400">
              ↳ {g.claim}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}

function RiskRow({ r, companyId }: { r: ReportRisk; companyId: string }) {
  return (
    <Link
      href={`/${companyId}/node/${r.rubric_id}`}
      className="flex items-start gap-3 py-3 border-b border-gray-100 last:border-0 hover:bg-gray-50 px-2 -mx-2 rounded transition-colors print:hover:bg-transparent"
    >
      <StateChip state={r.state} />
      <div className="flex-1 min-w-0">
        <p className="text-sm text-gray-800 leading-snug">{r.claim}</p>
        <p className="text-xs text-gray-400 mt-0.5">
          {THEME_DISPLAY[r.theme] ?? r.theme}
        </p>
      </div>
      <span className={`text-xs font-medium shrink-0 ${r.importance === "high" ? "text-red-500" : "text-amber-500"}`}>
        {r.importance}
      </span>
    </Link>
  );
}

export default function ReportPage() {
  const params = useParams();
  const companyId = params.companyId as string;
  const [report, setReport] = useState<AnalystReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [refreshMsg, setRefreshMsg] = useState("");

  useEffect(() => {
    api.getReport(companyId)
      .then(setReport)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [companyId]);

  async function handleRefresh() {
    setRefreshing(true);
    setRefreshMsg("");
    try {
      const result = await api.refreshGraph(companyId);
      setRefreshMsg(`Graph refreshed — ${result.changes.length} state change${result.changes.length !== 1 ? "s" : ""}`);
      const updated = await api.getReport(companyId);
      setReport(updated);
    } catch (e) {
      setRefreshMsg(`Refresh failed: ${String(e)}`);
    } finally {
      setRefreshing(false);
    }
  }

  if (loading) return <Shell><p className="text-gray-400 text-sm">Generating report…</p></Shell>;
  if (error) return <Shell><p className="text-red-500 text-sm">{error}</p></Shell>;
  if (!report) return null;

  const generatedDate = new Date(report.generated_at).toLocaleDateString("en-GB", {
    day: "numeric", month: "long", year: "numeric",
  });

  return (
    <Shell>
      {/* Header — hidden on print */}
      <div className="flex items-start justify-between mb-8 print:hidden">
        <div>
          <h1 className="text-lg font-semibold text-gray-900">Security Assessment Report</h1>
          <p className="text-sm text-gray-400 mt-0.5">Generated {generatedDate}</p>
          {refreshMsg && (
            <p className="text-xs text-emerald-600 mt-1">{refreshMsg}</p>
          )}
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="flex items-center gap-2 rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50 transition-colors disabled:opacity-50"
          >
            {refreshing ? "Refreshing…" : "↻ Refresh graph"}
          </button>
          <button
            onClick={() => window.print()}
            className="flex items-center gap-2 rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50 transition-colors"
          >
            ⎙ Print / Save PDF
          </button>
        </div>
      </div>

      {/* Print header — only visible on print */}
      <div className="hidden print:block mb-8">
        <h1 className="text-2xl font-bold text-gray-900">{report.company.name}</h1>
        <p className="text-sm text-gray-500 mt-1">Vendor Security Assessment — {generatedDate}</p>
        <div className="mt-2 border-b border-gray-300" />
      </div>

      {/* Top section: posture + summary stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <PostureGauge
          score={report.posture_score}
          answered={report.answered}
          applicable={report.applicable}
        />
        <div className="md:col-span-2 grid grid-cols-2 gap-4 content-start">
          <SummaryCard label="Rubrics answered" value={String(report.answered)} sub={`of ${report.applicable} applicable`} color="text-emerald-600" />
          <SummaryCard label="Open conflicts" value={String(report.open_conflicts_count)} sub="need resolution" color={report.open_conflicts_count > 0 ? "text-red-600" : "text-gray-500"} />
          <SummaryCard label="Not applicable" value={String(report.total - report.applicable)} sub="rubrics" color="text-gray-400" />
          <SummaryCard label="Total rubrics" value={String(report.total)} sub="in scope" color="text-gray-600" />
        </div>
      </div>

      {/* Theme breakdown */}
      <div className="bg-white rounded-2xl border border-gray-200 p-6 mb-6">
        <h2 className="text-sm font-semibold text-gray-700 mb-4">Coverage by theme</h2>
        <div>
          {report.theme_scores
            .filter((t) => t.applicable > 0)
            .sort((a, b) => a.score - b.score)
            .map((t) => (
              <ThemeRow key={t.theme} t={t} />
            ))}
        </div>
      </div>

      {/* Top risks */}
      {report.top_risks.length > 0 && (
        <div className="bg-white rounded-2xl border border-gray-200 p-6 mb-6">
          <h2 className="text-sm font-semibold text-gray-700 mb-1">
            Top risks
          </h2>
          <p className="text-xs text-gray-400 mb-4">
            High and medium importance rubrics that are unresolved
          </p>
          <div>
            {report.top_risks.map((r) => (
              <RiskRow key={r.rubric_id} r={r} companyId={companyId} />
            ))}
          </div>
        </div>
      )}

      {report.open_conflicts_count > 0 && (
        <div className="rounded-2xl border border-red-200 bg-red-50 p-5 flex items-start gap-3">
          <span className="text-red-400 text-lg shrink-0">⚠</span>
          <div>
            <p className="text-sm font-medium text-red-700">
              {report.open_conflicts_count} open conflict{report.open_conflicts_count !== 1 ? "s" : ""} require resolution
            </p>
            <p className="text-xs text-red-500 mt-0.5">
              Conflicted rubrics are excluded from the posture score until resolved.{" "}
              <Link href={`/${companyId}/graph`} className="underline print:hidden">
                Review in graph →
              </Link>
            </p>
          </div>
        </div>
      )}
    </Shell>
  );
}

function SummaryCard({ label, value, sub, color }: { label: string; value: string; sub: string; color: string }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4">
      <p className={`text-2xl font-bold ${color}`}>{value}</p>
      <p className="text-xs font-medium text-gray-600 mt-0.5">{label}</p>
      <p className="text-xs text-gray-400">{sub}</p>
    </div>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return <div className="p-8 max-w-4xl mx-auto">{children}</div>;
}
