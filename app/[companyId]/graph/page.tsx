"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { StateChip } from "@/components/StateChip";
import type { GraphResponse, GraphNode, NodeState } from "@/lib/types";

const IMPORTANCE_DOT: Record<string, string> = {
  high:   "bg-red-400",
  medium: "bg-amber-400",
  low:    "bg-gray-300",
};

const STATE_ORDER: NodeState[] = [
  "conflicted", "vague", "pending_gate", "unknown", "attempted_unknown",
  "verified", "user_confirmed", "not_applicable",
];

function sortNodes(nodes: GraphNode[]): GraphNode[] {
  return [...nodes].sort(
    (a, b) => STATE_ORDER.indexOf(a.state) - STATE_ORDER.indexOf(b.state)
  );
}

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color =
    pct >= 70 ? "bg-emerald-400" : pct >= 40 ? "bg-amber-400" : "bg-red-400";
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 rounded-full bg-gray-100 overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-gray-400 w-7 text-right">{pct}%</span>
    </div>
  );
}

function RubricCard({ node, companyId }: { node: GraphNode; companyId: string }) {
  return (
    <Link
      href={`/${companyId}/node/${node.rubric_id}`}
      className="block bg-white rounded-xl border border-gray-200 p-4 hover:border-blue-300 hover:shadow-sm transition-all"
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <StateChip state={node.state} />
        <span
          className={`w-2 h-2 rounded-full mt-1 shrink-0 ${IMPORTANCE_DOT[node.importance] ?? "bg-gray-300"}`}
          title={`${node.importance} importance`}
        />
      </div>
      <p className="text-sm text-gray-800 leading-snug mb-3">{node.claim}</p>
      <ConfidenceBar value={node.confidence} />
      {node.empty_required_slots.length > 0 && (
        <p className="mt-2 text-xs text-gray-400">
          Missing: {node.empty_required_slots.join(", ")}
        </p>
      )}
    </Link>
  );
}

export default function GraphPage() {
  const params = useParams();
  const companyId = params.companyId as string;
  const [data, setData] = useState<GraphResponse | null>(null);
  const [filter, setFilter] = useState<NodeState | "all">("all");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getGraph(companyId)
      .then(setData)
      .finally(() => setLoading(false));
  }, [companyId]);

  if (loading) return <PageShell><p className="text-gray-400 text-sm">Loading…</p></PageShell>;
  if (!data) return <PageShell><p className="text-red-500 text-sm">Failed to load graph.</p></PageShell>;

  const themeMap = new Map(data.themes.map((t) => [t.key, t]));
  const nodesByTheme = new Map<string, GraphNode[]>();
  for (const node of data.nodes) {
    if (!nodesByTheme.has(node.theme)) nodesByTheme.set(node.theme, []);
    nodesByTheme.get(node.theme)!.push(node);
  }

  const FILTER_OPTIONS: { value: NodeState | "all"; label: string }[] = [
    { value: "all", label: "All" },
    { value: "conflicted", label: "Conflicted" },
    { value: "vague", label: "Vague" },
    { value: "unknown", label: "Unknown" },
    { value: "verified", label: "Verified" },
  ];

  return (
    <PageShell>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-lg font-semibold text-gray-900">Security Graph</h1>
        <div className="flex gap-1">
          {FILTER_OPTIONS.map((opt) => (
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
      </div>

      <div className="space-y-10">
        {data.themes.map((theme) => {
          const nodes = nodesByTheme.get(theme.key) ?? [];
          const filtered = filter === "all"
            ? nodes
            : nodes.filter((n) => n.state === filter);
          if (filtered.length === 0) return null;

          const verifiedCount = nodes.filter(
            (n) => n.state === "verified" || n.state === "user_confirmed"
          ).length;

          return (
            <section key={theme.key}>
              <div className="flex items-center gap-3 mb-3">
                <h2 className="text-sm font-semibold text-gray-700">{theme.display_name}</h2>
                <span className="text-xs text-gray-400">
                  {verifiedCount}/{nodes.length} verified
                </span>
                <div className="flex-1 h-1 rounded-full bg-gray-100 overflow-hidden max-w-24">
                  <div
                    className="h-full bg-emerald-400 rounded-full"
                    style={{ width: `${nodes.length > 0 ? (verifiedCount / nodes.length) * 100 : 0}%` }}
                  />
                </div>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
                {sortNodes(filtered).map((node) => (
                  <RubricCard key={node.rubric_id} node={node} companyId={companyId} />
                ))}
              </div>
            </section>
          );
        })}
      </div>
    </PageShell>
  );
}

function PageShell({ children }: { children: React.ReactNode }) {
  return <div className="p-8 max-w-7xl mx-auto">{children}</div>;
}
