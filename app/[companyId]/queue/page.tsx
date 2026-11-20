"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { StateChip } from "@/components/StateChip";
import type { QueueItem } from "@/lib/types";

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

export default function QueuePage() {
  const params = useParams();
  const companyId = params.companyId as string;
  const [items, setItems] = useState<QueueItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getQueue(companyId)
      .then(setItems)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [companyId]);

  if (loading) {
    return (
      <div className="p-8">
        <p className="text-gray-400 text-sm">Loading queue…</p>
      </div>
    );
  }

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-lg font-semibold text-gray-900">Work Queue</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {items.length} rubric{items.length !== 1 ? "s" : ""} need attention · sorted by priority
          </p>
        </div>
      </div>

      {items.length === 0 ? (
        <div className="bg-white rounded-xl border border-gray-200 p-12 text-center">
          <p className="text-gray-500 text-sm">Queue is empty — all rubrics are resolved.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {items.map((item) => (
            <QueueRow key={item.rubric_id} item={item} companyId={companyId} />
          ))}
        </div>
      )}
    </div>
  );
}

function QueueRow({ item, companyId }: { item: QueueItem; companyId: string }) {
  return (
    <Link
      href={`/${companyId}/node/${item.rubric_id}`}
      className="flex items-start gap-4 bg-white rounded-xl border border-gray-200 p-4 hover:border-blue-300 hover:shadow-sm transition-all"
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <StateChip state={item.state} />
          <span className="text-xs text-gray-400">
            {THEME_DISPLAY[item.theme] ?? item.theme}
          </span>
        </div>
        <p className="text-sm text-gray-800 leading-snug">{item.claim}</p>
        {item.empty_required_slots.length > 0 && (
          <p className="mt-1 text-xs text-gray-400">
            Missing slots: {item.empty_required_slots.join(", ")}
          </p>
        )}
      </div>
      <div className="shrink-0 text-right">
        <span className="text-xs font-mono text-gray-400">
          {item.priority.toFixed(0)}
        </span>
        <p className="text-xs text-gray-300">priority</p>
      </div>
    </Link>
  );
}
