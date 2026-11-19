import type { NodeState } from "@/lib/types";

const CONFIG: Record<NodeState, { label: string; className: string }> = {
  verified:          { label: "Verified",        className: "bg-emerald-100 text-emerald-700" },
  user_confirmed:    { label: "Confirmed",        className: "bg-emerald-200 text-emerald-800" },
  conflicted:        { label: "Conflicted",       className: "bg-red-100 text-red-700" },
  vague:             { label: "Vague",            className: "bg-amber-100 text-amber-700" },
  unknown:           { label: "Unknown",          className: "bg-gray-100 text-gray-500" },
  not_applicable:    { label: "N/A",              className: "bg-gray-100 text-gray-400" },
  pending_gate:      { label: "Pending gate",     className: "bg-blue-100 text-blue-600" },
  attempted_unknown: { label: "Attempted",        className: "bg-gray-100 text-gray-400" },
};

export function StateChip({ state }: { state: NodeState }) {
  const { label, className } = CONFIG[state] ?? CONFIG.unknown;
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${className}`}>
      {label}
    </span>
  );
}
