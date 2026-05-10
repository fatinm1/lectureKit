"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { AppSubpageHeader } from "../components/app/AppSubpageHeader";
import { MarketingScrollReveal } from "../components/marketing/MarketingScrollReveal";
import type { ObjectiveAnalysis, ProvostSession } from "../../types/lecture";

function CoverageBar({ score }: { score: number }) {
  const color = score >= 8 ? "#1d9e75" : score >= 5 ? "#ba7517" : "#e53e3e";
  return (
    <div className="flex items-center gap-3">
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-zinc-800">
        <div className="h-full rounded-full transition-all" style={{ width: `${score * 10}%`, backgroundColor: color }} />
      </div>
      <span className="font-mono text-xs" style={{ color }}>
        {score}/10
      </span>
    </div>
  );
}

function StatusBadge({ status }: { status: "covered" | "partial" | "missing" }) {
  const styles: Record<string, string> = {
    covered: "bg-[#0f2a1a] text-[#1d9e75] border-[#1d9e75]",
    partial: "bg-[#1a1200] text-[#ba7517] border-[#ba7517]",
    missing: "bg-[#1a0a0a] text-[#e53e3e] border-[#e53e3e]",
  };
  const labels: Record<string, string> = {
    covered: "Covered",
    partial: "Partial",
    missing: "Missing",
  };
  return (
    <span className={`rounded-full border px-2.5 py-1 font-mono text-xs ${styles[status]}`}>{labels[status]}</span>
  );
}

export default function CurriculumPage() {
  const router = useRouter();
  const [session, setSession] = useState<ProvostSession | null>(null);

  useEffect(() => {
    const stored = window.localStorage.getItem("lecturekit_provost_session");
    if (!stored) {
      router.push("/app");
      return;
    }
    setSession(JSON.parse(stored) as ProvostSession);
  }, [router]);

  if (!session) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-950">
        <div className="font-mono text-sm text-zinc-500">Loading curriculum map...</div>
      </div>
    );
  }

  const { curriculum_map, lecture_count, video_ids } = session;
  const { coverage_distribution } = curriculum_map;

  const headerRight = (
    <div className="flex flex-wrap items-center justify-end gap-3">
      <span className="rounded-full border border-white/10 bg-zinc-900/50 px-3 py-1 font-mono text-xs text-zinc-400">
        {lecture_count} LECTURES
      </span>
      <div className="flex items-center gap-2 text-xs">
        <span className="font-mono text-[#1d9e75]">{coverage_distribution.fully_covered} covered</span>
        <span className="font-mono text-[#ba7517]">{coverage_distribution.partially_covered} partial</span>
        <span className="font-mono text-[#e53e3e]">{coverage_distribution.not_covered} missing</span>
      </div>
      <div className="font-lk-serif text-xl text-[#5e6ad2]">{curriculum_map.overall_coverage_score}/10</div>
    </div>
  );

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-200">
      <AppSubpageHeader title="Curriculum Coverage Map" right={headerRight} />

      <div className="mx-auto max-w-6xl space-y-8 px-6 py-8">
        <MarketingScrollReveal>
          <div className="rounded-2xl border border-white/5 bg-zinc-900/50 p-6 transition-colors hover:border-white/10">
            <h2 className="mb-3 font-mono text-xs font-semibold uppercase tracking-widest text-zinc-500">Executive Summary</h2>
            <p className="leading-relaxed text-zinc-400">{curriculum_map.executive_summary}</p>
          </div>
        </MarketingScrollReveal>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          {[
            { label: "Fully Covered", count: coverage_distribution.fully_covered, color: "#1d9e75", border: "border-[#1d9e75]/30" },
            { label: "Partially Covered", count: coverage_distribution.partially_covered, color: "#ba7517", border: "border-[#ba7517]/30" },
            { label: "Not Covered", count: coverage_distribution.not_covered, color: "#e53e3e", border: "border-[#e53e3e]/30" },
          ].map((item) => (
            <div
              key={item.label}
              className={`rounded-2xl border bg-zinc-900/50 p-4 text-center transition-colors hover:border-white/10 ${item.border}`}
            >
              <div className="mb-1 text-3xl font-bold" style={{ color: item.color }}>
                {item.count}
              </div>
              <div className="text-xs text-zinc-500">{item.label}</div>
            </div>
          ))}
        </div>

        <div>
          <h2 className="mb-4 font-mono text-xs font-semibold uppercase tracking-widest text-zinc-500">Learning Objectives</h2>
          <div className="space-y-4">
            {curriculum_map.objectives_analysis.map((obj: ObjectiveAnalysis, i: number) => (
              <MarketingScrollReveal key={i}>
                <div className="rounded-xl border border-white/5 bg-zinc-900/50 p-5 transition-colors hover:border-white/10">
                  <div className="mb-3 flex flex-wrap items-start justify-between gap-4">
                    <div className="flex min-w-0 items-start gap-3">
                      <span className="mt-1 shrink-0 font-mono text-xs text-zinc-500">#{i + 1}</span>
                      <p className="text-sm font-medium text-white">{obj.objective}</p>
                    </div>
                    <StatusBadge status={obj.coverage_status} />
                  </div>
                  <CoverageBar score={obj.coverage_score} />
                  {obj.evidence ? (
                    <p className="mt-3 text-xs text-zinc-500">
                      <span className="text-[#5e6ad2]">Evidence: </span>
                      {obj.evidence}
                    </p>
                  ) : null}
                  {obj.gaps && obj.coverage_status !== "covered" ? (
                    <p className="mt-2 text-xs text-[#e53e3e]">
                      <span className="font-mono">Gap: </span>
                      {obj.gaps}
                    </p>
                  ) : null}
                  {obj.lectures_covering.length > 0 ? (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {obj.lectures_covering.map((l) => (
                        <span key={l} className="rounded-full bg-zinc-950 px-2 py-0.5 font-mono text-xs text-zinc-400">
                          Lecture {l}
                        </span>
                      ))}
                    </div>
                  ) : null}
                </div>
              </MarketingScrollReveal>
            ))}
          </div>
        </div>

        <MarketingScrollReveal>
          <div className="rounded-xl border border-[#1d9e75] bg-[#0f2a1a] p-6">
            <h2 className="mb-4 font-mono text-xs font-semibold uppercase tracking-wider text-[#1d9e75]">Curriculum Strengths</h2>
            <ul className="space-y-2">
              {curriculum_map.curriculum_strengths.map((s, i) => (
                <li key={i} className="flex gap-2 text-sm text-zinc-300">
                  <span className="text-[#1d9e75]">+</span> {s}
                </li>
              ))}
            </ul>
          </div>
        </MarketingScrollReveal>

        <div>
          <h2 className="mb-4 font-mono text-xs font-semibold uppercase tracking-widest text-zinc-500">Critical Gaps</h2>
          <div className="space-y-3">
            {curriculum_map.critical_gaps.map((gap, i) => (
              <MarketingScrollReveal key={i}>
                <div className="rounded-xl border border-[#e53e3e] bg-[#1a0a0a] p-4">
                  <p className="mb-1 text-sm font-medium text-[#e53e3e]">{gap.gap}</p>
                  <p className="mb-2 text-xs text-zinc-400">{gap.impact}</p>
                  <p className="text-xs text-[#5e6ad2]">→ {gap.recommendation}</p>
                </div>
              </MarketingScrollReveal>
            ))}
          </div>
        </div>

        <div>
          <h2 className="mb-4 font-mono text-xs font-semibold uppercase tracking-widest text-zinc-500">Prioritized Recommendations</h2>
          <div className="space-y-3">
            {curriculum_map.recommendations.map((rec, i) => (
              <MarketingScrollReveal key={i}>
                <div className="flex gap-4 rounded-xl border border-white/5 bg-zinc-900/50 p-4 transition-colors hover:border-white/10">
                  <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[#5e6ad2] text-xs font-bold text-white">
                    {rec.priority}
                  </div>
                  <div className="min-w-0">
                    <p className="mb-1 text-sm font-medium text-white">{rec.recommendation}</p>
                    <p className="text-xs text-zinc-500">{rec.rationale}</p>
                  </div>
                </div>
              </MarketingScrollReveal>
            ))}
          </div>
        </div>

        <MarketingScrollReveal>
          <div className="rounded-xl border border-white/5 bg-zinc-900/50 p-4 transition-colors hover:border-white/10">
            <h2 className="mb-3 font-mono text-xs font-semibold uppercase tracking-wider text-zinc-500">Lectures Analyzed</h2>
            <div className="flex flex-wrap gap-2">
              {video_ids.map((id, i) => (
                <a
                  key={id}
                  href={`https://www.youtube.com/watch?v=${id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="rounded-full bg-zinc-950 px-2 py-1 font-mono text-xs text-[#5e6ad2] transition-colors hover:text-white"
                >
                  Lecture {i + 1}: {id}
                </a>
              ))}
            </div>
          </div>
        </MarketingScrollReveal>
      </div>
    </div>
  );
}
