"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import type { Document } from "@/lib/types";

const SOURCE_TYPE_LABEL: Record<string, string> = {
  policy: "Policy",
  assessment: "Assessment",
  contract: "Contract",
  infra: "Infrastructure",
  questionnaire: "Questionnaire",
};

function DocRow({ doc }: { doc: Document }) {
  const uploadedDate = new Date(doc.uploaded_at).toLocaleDateString("en-GB", {
    day: "numeric", month: "short", year: "numeric",
  });
  const authoredDate = doc.authored_at
    ? doc.authored_at.slice(0, 10)
    : null;

  return (
    <div className="flex items-center gap-4 py-3.5 border-b border-gray-100 last:border-0">
      <div className="shrink-0 w-7 h-7 rounded-lg bg-gray-100 flex items-center justify-center">
        <FileIcon ext={doc.filename.split(".").pop() ?? ""} />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm text-gray-800 truncate font-medium">{doc.filename}</p>
        <p className="text-xs text-gray-400 mt-0.5">
          Uploaded {uploadedDate}
          {authoredDate && ` · Authored ${authoredDate}`}
          {doc.page_count > 0 && ` · ${doc.page_count} pages`}
        </p>
      </div>
      <span className="shrink-0 text-xs font-medium text-gray-500 bg-gray-100 rounded-full px-2.5 py-0.5">
        {SOURCE_TYPE_LABEL[doc.source_type] ?? doc.source_type}
      </span>
    </div>
  );
}

function FileIcon({ ext }: { ext: string }) {
  const colors: Record<string, string> = {
    pdf: "text-red-400",
    docx: "text-blue-400",
    xlsx: "text-emerald-400",
    xls: "text-emerald-400",
  };
  return (
    <span className={`text-xs font-bold uppercase ${colors[ext.toLowerCase()] ?? "text-gray-400"}`}>
      {ext.slice(0, 3)}
    </span>
  );
}

const SOURCE_TYPE_GROUPS: Array<{ key: string; label: string }> = [
  { key: "all", label: "All" },
  { key: "policy", label: "Policies" },
  { key: "assessment", label: "Assessments" },
  { key: "contract", label: "Contracts" },
  { key: "infra", label: "Infrastructure" },
  { key: "questionnaire", label: "Questionnaire" },
];

export default function DocumentsPage() {
  const params = useParams();
  const companyId = params.companyId as string;
  const [docs, setDocs] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("all");

  useEffect(() => {
    api.listDocuments(companyId)
      .then(setDocs)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [companyId]);

  const filtered = filter === "all" ? docs : docs.filter((d) => d.source_type === filter);

  const countBy = (key: string) =>
    key === "all" ? docs.length : docs.filter((d) => d.source_type === key).length;

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-lg font-semibold text-gray-900">Documents</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {docs.length} document{docs.length !== 1 ? "s" : ""} ingested
          </p>
        </div>
        <Link
          href={`/${companyId}/upload`}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
        >
          + Upload
        </Link>
      </div>

      <div className="flex gap-1 mb-5 flex-wrap">
        {SOURCE_TYPE_GROUPS.map((g) => {
          const count = countBy(g.key);
          if (g.key !== "all" && count === 0) return null;
          return (
            <button
              key={g.key}
              onClick={() => setFilter(g.key)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                filter === g.key
                  ? "bg-gray-900 text-white"
                  : "bg-white border border-gray-200 text-gray-600 hover:bg-gray-50"
              }`}
            >
              {g.label} {count > 0 && <span className="opacity-60">{count}</span>}
            </button>
          );
        })}
      </div>

      {loading ? (
        <p className="text-gray-400 text-sm">Loading…</p>
      ) : filtered.length === 0 ? (
        <div className="bg-white rounded-xl border border-gray-200 p-12 text-center">
          <p className="text-gray-400 text-sm">No documents yet.</p>
          <Link
            href={`/${companyId}/upload`}
            className="mt-3 inline-block text-sm text-blue-500 hover:text-blue-700 transition-colors"
          >
            Upload your first document →
          </Link>
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 px-5">
          {filtered.map((doc) => (
            <DocRow key={doc.id} doc={doc} />
          ))}
        </div>
      )}
    </div>
  );
}
