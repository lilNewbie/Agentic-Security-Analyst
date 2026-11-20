"use client";

import Link from "next/link";
import { usePathname, useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Stats } from "@/lib/types";

function NavLink({ href, label }: { href: string; label: string }) {
  const pathname = usePathname();
  const active = pathname.startsWith(href);
  return (
    <Link
      href={href}
      className={`block rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
        active
          ? "bg-white/10 text-white"
          : "text-gray-300 hover:bg-white/5 hover:text-white"
      }`}
    >
      {label}
    </Link>
  );
}

export default function CompanyLayout({ children }: { children: React.ReactNode }) {
  const params = useParams();
  const companyId = params.companyId as string;
  const [stats, setStats] = useState<Stats | null>(null);
  const [companyName, setCompanyName] = useState("");

  useEffect(() => {
    api.getCompany(companyId).then((c) => setCompanyName(c.name)).catch(() => {});
    api.getStats(companyId).then(setStats).catch(() => {});
  }, [companyId]);

  return (
    <div className="flex h-full min-h-screen">
      {/* Sidebar */}
      <aside className="w-56 shrink-0 bg-gray-900 flex flex-col">
        <div className="px-4 py-5 border-b border-white/10">
          <p className="text-xs font-medium text-gray-400 uppercase tracking-wider">Company</p>
          <p className="mt-1 text-sm font-semibold text-white truncate">
            {companyName || companyId.slice(0, 8) + "…"}
          </p>
        </div>

        <nav className="flex-1 p-3 space-y-1">
          <NavLink href={`/${companyId}/graph`} label="Graph" />
          <NavLink href={`/${companyId}/queue`} label="Work Queue" />
          <NavLink href={`/${companyId}/questionnaire`} label="Questionnaire" />
          <NavLink href={`/${companyId}/report`} label="Report" />
          <NavLink href={`/${companyId}/documents`} label="Documents" />
          <NavLink href={`/${companyId}/upload`} label="Upload" />
        </nav>

        {stats && (
          <div className="p-4 border-t border-white/10 space-y-2">
            <StatRow label="Verified" value={stats.verified + stats.user_confirmed} color="text-emerald-400" />
            <StatRow label="Conflicted" value={stats.conflicted} color="text-red-400" />
            <StatRow label="Vague" value={stats.vague} color="text-amber-400" />
            <StatRow label="Unknown" value={stats.unknown + stats.attempted_unknown} color="text-gray-400" />
          </div>
        )}

        <div className="p-4 border-t border-white/10">
          <Link href="/" className="text-xs text-gray-500 hover:text-gray-300 transition-colors">
            ← Switch company
          </Link>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 overflow-auto">{children}</main>
    </div>
  );
}

function StatRow({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-xs text-gray-400">{label}</span>
      <span className={`text-xs font-semibold ${color}`}>{value}</span>
    </div>
  );
}
