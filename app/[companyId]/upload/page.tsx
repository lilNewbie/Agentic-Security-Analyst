"use client";

import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import type { IngestionJobStatus } from "@/lib/types";

const SOURCE_TYPES = [
  { value: "", label: "Auto-detect from filename" },
  { value: "policy", label: "Policy document" },
  { value: "assessment", label: "Security assessment" },
  { value: "contract", label: "Contract / agreement" },
  { value: "infra", label: "Infrastructure / internal" },
  { value: "questionnaire", label: "Vendor questionnaire" },
];

function StatusBadge({ status }: { status: IngestionJobStatus["status"] }) {
  const styles: Record<string, string> = {
    pending: "bg-gray-100 text-gray-500",
    running: "bg-blue-100 text-blue-700",
    done: "bg-emerald-100 text-emerald-700",
    failed: "bg-red-100 text-red-700",
  };
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${styles[status] ?? styles.pending}`}>
      {status}
    </span>
  );
}

function JobPanel({
  companyId,
  jobId,
  filename,
}: {
  companyId: string;
  jobId: string;
  filename: string;
}) {
  const [job, setJob] = useState<IngestionJobStatus | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    function poll() {
      api.getIngestionStatus(companyId, jobId).then((j) => {
        setJob(j);
        if (j.status === "done" || j.status === "failed") {
          if (intervalRef.current) clearInterval(intervalRef.current);
        }
      }).catch(() => {});
    }
    poll();
    intervalRef.current = setInterval(poll, 2000);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [companyId, jobId]);

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <div className="flex items-start justify-between gap-3 mb-3">
        <div>
          <p className="text-sm font-medium text-gray-800 truncate max-w-sm">{filename}</p>
          <p className="text-xs text-gray-400 mt-0.5 font-mono">{jobId.slice(0, 8)}…</p>
        </div>
        {job && <StatusBadge status={job.status} />}
      </div>

      {job && (
        <>
          {job.status === "running" && (
            <div className="mt-2">
              <div className="h-1.5 w-full rounded-full bg-gray-100 overflow-hidden">
                <div
                  className="h-full bg-blue-400 rounded-full transition-all duration-500"
                  style={{ width: `${Math.round(job.progress * 100)}%` }}
                />
              </div>
              <p className="text-xs text-gray-400 mt-1">{Math.round(job.progress * 100)}% complete</p>
            </div>
          )}

          {job.status === "done" && job.result && (
            <div className="mt-3 grid grid-cols-3 gap-3">
              <Stat label="Files" value={String(job.result.files_processed ?? 1)} />
              <Stat label="Candidates" value={String(job.result.candidates_extracted ?? "—")} />
              <Stat label="Bound" value={String(job.result.facts_bound ?? "—")} />
            </div>
          )}

          {job.errors.length > 0 && (
            <div className="mt-3 rounded-lg bg-red-50 border border-red-100 px-3 py-2">
              {job.errors.map((e, i) => (
                <p key={i} className="text-xs text-red-600">{e}</p>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-gray-50 px-3 py-2 text-center">
      <p className="text-lg font-semibold text-gray-900">{value}</p>
      <p className="text-xs text-gray-400">{label}</p>
    </div>
  );
}

export default function UploadPage() {
  const params = useParams();
  const companyId = params.companyId as string;
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [file, setFile] = useState<File | null>(null);
  const [sourceType, setSourceType] = useState("");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [jobs, setJobs] = useState<Array<{ jobId: string; filename: string }>>([]);
  const [dragging, setDragging] = useState(false);

  function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    setFile(files[0]);
    setError("");
  }

  async function handleUpload() {
    if (!file) return;
    setUploading(true);
    setError("");
    try {
      const { ingestion_job_id } = await api.uploadDocument(
        companyId,
        file,
        sourceType || undefined
      );
      setJobs((prev) => [{ jobId: ingestion_job_id, filename: file.name }, ...prev]);
      setFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
    } catch (err) {
      setError(String(err));
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="p-8 max-w-3xl mx-auto">
      <div className="mb-8">
        <h1 className="text-lg font-semibold text-gray-900">Upload Document</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          Add a single document to the pipeline. For bulk ingestion use the corpus endpoint.
        </p>
      </div>

      {/* Drop zone */}
      <div
        className={`bg-white rounded-xl border-2 border-dashed p-8 text-center transition-colors mb-6 ${
          dragging ? "border-blue-400 bg-blue-50" : "border-gray-300"
        }`}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          handleFiles(e.dataTransfer.files);
        }}
      >
        {file ? (
          <div>
            <p className="text-sm font-medium text-gray-800">{file.name}</p>
            <p className="text-xs text-gray-400 mt-1">{(file.size / 1024).toFixed(0)} KB</p>
            <button
              onClick={() => { setFile(null); if (fileInputRef.current) fileInputRef.current.value = ""; }}
              className="mt-2 text-xs text-red-400 hover:text-red-600 transition-colors"
            >
              Remove
            </button>
          </div>
        ) : (
          <div>
            <p className="text-sm text-gray-500 mb-3">Drag a file here or</p>
            <button
              onClick={() => fileInputRef.current?.click()}
              className="rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50 transition-colors"
            >
              Browse files
            </button>
            <p className="text-xs text-gray-400 mt-3">Supported: .docx .pdf .xlsx</p>
          </div>
        )}
        <input
          ref={fileInputRef}
          type="file"
          accept=".docx,.pdf,.xlsx,.xls"
          className="hidden"
          onChange={(e) => handleFiles(e.target.files)}
        />
      </div>

      {/* Options */}
      <div className="bg-white rounded-xl border border-gray-200 p-5 mb-6">
        <label className="text-xs font-medium text-gray-500 mb-2 block">Document type</label>
        <select
          value={sourceType}
          onChange={(e) => setSourceType(e.target.value)}
          className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {SOURCE_TYPES.map((s) => (
            <option key={s.value} value={s.value}>{s.label}</option>
          ))}
        </select>
      </div>

      {error && (
        <p className="text-sm text-red-500 mb-4">{error}</p>
      )}

      <button
        onClick={handleUpload}
        disabled={!file || uploading}
        className="w-full rounded-lg bg-blue-600 py-2.5 text-sm font-medium text-white hover:bg-blue-700 transition-colors disabled:opacity-50 mb-8"
      >
        {uploading ? "Uploading…" : "Upload & ingest"}
      </button>

      {/* Job history */}
      {jobs.length > 0 && (
        <div>
          <h2 className="text-sm font-semibold text-gray-700 mb-3">Ingestion jobs</h2>
          <div className="space-y-3">
            {jobs.map((j) => (
              <JobPanel key={j.jobId} companyId={companyId} jobId={j.jobId} filename={j.filename} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
