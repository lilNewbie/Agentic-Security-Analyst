"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { StateChip } from "@/components/StateChip";
import type { NodeDetail, Entry, Conflict } from "@/lib/types";

export default function NodePage() {
  const params = useParams();
  const router = useRouter();
  const companyId = params.companyId as string;
  const rubricId = params.rubricId as string;

  const [detail, setDetail] = useState<NodeDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  function reload() {
    setLoading(true);
    api.getNode(companyId, rubricId)
      .then(setDetail)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }

  useEffect(reload, [companyId, rubricId]);

  if (loading) return <Shell><p className="text-gray-400 text-sm">Loading…</p></Shell>;
  if (error) return <Shell><p className="text-red-500 text-sm">{error}</p></Shell>;
  if (!detail) return null;

  const { rubric, node_state, entries, conflicts } = detail;
  const slotMap = new Map(entries.map((e) => [e.slot, e]));

  return (
    <Shell>
      <button
        onClick={() => router.back()}
        className="mb-6 text-sm text-gray-500 hover:text-gray-700 transition-colors"
      >
        ← Back
      </button>

      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-3 mb-2">
          {node_state && <StateChip state={node_state.state} />}
          <span className="text-xs text-gray-400 uppercase tracking-wider">{rubric.theme}</span>
          <span className="text-xs text-gray-400">·</span>
          <span className="text-xs text-gray-400">{rubric.importance} importance</span>
        </div>
        <h1 className="text-lg font-semibold text-gray-900">{rubric.claim}</h1>
        {node_state && (
          <div className="mt-2 flex items-center gap-2">
            <div className="h-1.5 w-24 rounded-full bg-gray-100 overflow-hidden">
              <div
                className="h-full bg-emerald-400 rounded-full"
                style={{ width: `${Math.round(node_state.confidence * 100)}%` }}
              />
            </div>
            <span className="text-xs text-gray-400">{Math.round(node_state.confidence * 100)}% confidence</span>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Slots */}
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h2 className="text-sm font-semibold text-gray-700 mb-4">Slots</h2>
          <div className="space-y-4">
            {rubric.slots.map((slot) => {
              const entry = slotMap.get(slot.name);
              return (
                <div key={slot.name} className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-medium text-gray-600">{slot.name}</span>
                    {slot.required && (
                      <span className="text-xs text-red-400">required</span>
                    )}
                    {entry ? (
                      <span className="ml-auto text-xs text-emerald-600">✓ filled</span>
                    ) : (
                      <span className="ml-auto text-xs text-gray-300">empty</span>
                    )}
                  </div>
                  {entry ? (
                    <div className="rounded-lg bg-gray-50 px-3 py-2">
                      <p className="text-sm font-medium text-gray-900">
                        {String(entry.value ?? "")}
                      </p>
                      {entry.source_span && (
                        <p className="mt-1 text-xs text-gray-400 italic">
                          &ldquo;{entry.source_span.slice(0, 120)}{entry.source_span.length > 120 ? "…" : ""}&rdquo;
                        </p>
                      )}
                      <p className="mt-1 text-xs text-gray-300">
                        {entry.source_kind} · {entry.source_type ?? "unknown"}
                        {entry.source_authored_at && ` · ${entry.source_authored_at.slice(0, 10)}`}
                      </p>
                    </div>
                  ) : (
                    <p className="text-xs text-gray-400 px-3">{slot.prompt}</p>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Right column: conflicts + correction */}
        <div className="space-y-5">
          {conflicts.length > 0 && (
            <ConflictsPanel
              conflicts={conflicts}
              entries={entries}
              companyId={companyId}
              onResolved={reload}
            />
          )}
          <CorrectionForm
            companyId={companyId}
            rubricId={rubricId}
            slots={rubric.slots}
            onSaved={reload}
          />
        </div>
      </div>
    </Shell>
  );
}

function ConflictsPanel({
  conflicts,
  entries,
  companyId,
  onResolved,
}: {
  conflicts: Conflict[];
  entries: Entry[];
  companyId: string;
  onResolved: () => void;
}) {
  const [resolving, setResolving] = useState<string | null>(null);
  const entryMap = new Map(entries.map((e) => [e.entry_id, e]));

  async function resolve(conflictId: string, winningEntryId: string) {
    setResolving(conflictId);
    try {
      await api.resolveConflict(conflictId, winningEntryId);
      onResolved();
    } finally {
      setResolving(null);
    }
  }

  return (
    <div className="bg-white rounded-xl border border-red-200 p-5">
      <h2 className="text-sm font-semibold text-red-700 mb-4">
        {conflicts.length} Open Conflict{conflicts.length !== 1 ? "s" : ""}
      </h2>
      <div className="space-y-5">
        {conflicts.map((c) => {
          const a = entryMap.get(c.entry_a);
          const b = entryMap.get(c.entry_b);
          return (
            <div key={c.conflict_id} className="space-y-3">
              <p className="text-xs text-gray-500 font-medium">{c.summary}</p>
              <p className="text-xs text-gray-400 italic">{c.resolution_question}</p>
              <div className="grid grid-cols-2 gap-2">
                {[{ entry: a, id: c.entry_a, label: "Option A" }, { entry: b, id: c.entry_b, label: "Option B" }].map(
                  ({ entry, id, label }) => (
                    <button
                      key={id}
                      disabled={resolving === c.conflict_id}
                      onClick={() => resolve(c.conflict_id, id)}
                      className="text-left rounded-lg border border-gray-200 p-3 hover:border-blue-400 hover:bg-blue-50 transition-all disabled:opacity-50"
                    >
                      <p className="text-xs font-medium text-gray-500 mb-1">{label}</p>
                      <p className="text-sm text-gray-900">
                        {String(entry?.value ?? "—")}
                      </p>
                      <p className="text-xs text-gray-400 mt-1">
                        {entry?.source_type ?? "unknown"}
                        {entry?.source_authored_at && ` · ${entry.source_authored_at.slice(0, 10)}`}
                      </p>
                    </button>
                  )
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function CorrectionForm({
  companyId,
  rubricId,
  slots,
  onSaved,
}: {
  companyId: string;
  rubricId: string;
  slots: NodeDetail["rubric"]["slots"];
  onSaved: () => void;
}) {
  const [slot, setSlot] = useState(slots[0]?.name ?? "");
  const [value, setValue] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  const slotDef = slots.find((s) => s.name === slot);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!value.trim()) return;
    setSaving(true);
    setError("");
    try {
      let parsed: unknown = value.trim();
      if (slotDef?.type === "bool") parsed = value === "true";
      else if (slotDef?.type === "enum") parsed = value;
      await api.postCorrection(companyId, rubricId, slot, parsed);
      setSaved(true);
      setValue("");
      setTimeout(() => setSaved(false), 2000);
      onSaved();
    } catch (err) {
      setError(String(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <h2 className="text-sm font-semibold text-gray-700 mb-4">Submit correction</h2>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <label className="text-xs text-gray-500 mb-1 block">Slot</label>
          <select
            value={slot}
            onChange={(e) => setSlot(e.target.value)}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            {slots.map((s) => (
              <option key={s.name} value={s.name}>{s.name}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="text-xs text-gray-500 mb-1 block">Value</label>
          {slotDef?.type === "bool" ? (
            <select
              value={value}
              onChange={(e) => setValue(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">Select…</option>
              <option value="true">Yes / True</option>
              <option value="false">No / False</option>
            </select>
          ) : slotDef?.enum ? (
            <select
              value={value}
              onChange={(e) => setValue(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">Select…</option>
              {slotDef.enum.map((opt) => (
                <option key={opt} value={opt}>{opt}</option>
              ))}
            </select>
          ) : (
            <input
              type="text"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder={slotDef?.prompt || "Enter value"}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          )}
        </div>

        {error && <p className="text-xs text-red-500">{error}</p>}

        <button
          type="submit"
          disabled={saving || !value}
          className="w-full rounded-lg bg-blue-600 py-2 text-sm font-medium text-white hover:bg-blue-700 transition-colors disabled:opacity-50"
        >
          {saving ? "Saving…" : saved ? "Saved ✓" : "Submit correction"}
        </button>
      </form>
    </div>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return <div className="p-8 max-w-5xl mx-auto">{children}</div>;
}
