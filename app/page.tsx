"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

export default function Home() {
  const router = useRouter();
  const [companyId, setCompanyId] = useState("");
  const [newName, setNewName] = useState("");
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);

  async function handleOpen(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    const id = companyId.trim();
    if (!id) return;
    try {
      await api.getCompany(id);
      router.push(`/${id}/graph`);
    } catch {
      setError("Company not found. Check the ID.");
    }
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    const name = newName.trim();
    if (!name) return;
    setCreating(true);
    try {
      const { company_id } = await api.createCompany(name);
      router.push(`/${company_id}/graph`);
    } catch (err) {
      setError(String(err));
      setCreating(false);
    }
  }

  return (
    <div className="min-h-full flex items-center justify-center p-8">
      <div className="w-full max-w-md space-y-8">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">AI Security Analyst</h1>
          <p className="mt-1 text-sm text-gray-500">
            Vendor security questionnaire analysis
          </p>
        </div>

        {error && (
          <div className="rounded-md bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
          <h2 className="text-sm font-medium text-gray-700">Open existing company</h2>
          <form onSubmit={handleOpen} className="flex gap-2">
            <input
              type="text"
              placeholder="Company ID (UUID)"
              value={companyId}
              onChange={(e) => setCompanyId(e.target.value)}
              className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono"
            />
            <button
              type="submit"
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
            >
              Open
            </button>
          </form>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
          <h2 className="text-sm font-medium text-gray-700">Create new company</h2>
          <form onSubmit={handleCreate} className="flex gap-2">
            <input
              type="text"
              placeholder="Company name"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <button
              type="submit"
              disabled={creating}
              className="rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-700 transition-colors disabled:opacity-50"
            >
              {creating ? "Creating…" : "Create"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
