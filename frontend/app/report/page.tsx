"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { AppSubpageHeader } from "../components/app/AppSubpageHeader";
import { MarketingScrollReveal } from "../components/marketing/MarketingScrollReveal";
import type { FacultySession } from "../../types/lecture";

function formatTimestamp(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}

function ScoreRing({ score }: { score: number }) {
  const color = score >= 8 ? "#1d9e75" : score >= 5 ? "#ba7517" : "#e53e3e";
  return (
    <div
      className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full border-2 text-xs font-bold"
      style={{ borderColor: color, color }}
    >
      {score}/10
    </div>
  );
}

export default function ReportPage() {
  const router = useRouter();
  const [session, setSession] = useState<FacultySession | null>(null);
  const iframeRef = useRef<HTMLIFrameElement>(null);

  useEffect(() => {
    const stored = window.localStorage.getItem("lecturekit_faculty_session");
    if (!stored) {
      router.push("/app");
      return;
    }
    setSession(JSON.parse(stored) as FacultySession);
  }, [router]);

  function seekTo(seconds: number) {
    iframeRef.current?.contentWindow?.postMessage(
      JSON.stringify({ event: "command", func: "seekTo", args: [seconds, true] }),
      "*"
    );
  }

  if (!session) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-950">
        <div className="font-mono text-sm text-zinc-500">Loading report...</div>
      </div>
    );
  }

  const { report, video_id } = session;

  const headerRight = (
    <div className="flex items-center gap-3">
      <span className="rounded-full border border-[#ba7517] bg-[#1a1200] px-3 py-1 text-xs font-medium text-[#ba7517]">
        PRIVATE
      </span>
      <div className="hidden items-baseline gap-1 sm:flex">
        <span className="font-lk-serif text-3xl text-[#5e6ad2]">{report.overall_score}</span>
        <span className="text-sm text-zinc-500">/10</span>
      </div>
      <ScoreRing score={report.overall_score} />
    </div>
  );

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-200">
      <AppSubpageHeader title="Faculty Audit Report" right={headerRight} />

      <div className="mx-auto grid max-w-7xl grid-cols-1 gap-8 px-6 py-8 lg:grid-cols-[1fr_400px]">
        <div className="space-y-8">
          <MarketingScrollReveal>
            <div className="rounded-2xl border border-[#ba7517] bg-[#1a1200] p-6">
              <div className="mb-3 flex items-center gap-2">
                <span className="font-mono text-xs uppercase tracking-wider text-[#ba7517]">Top Priority Fix</span>
              </div>
              <h2 className="mb-2 text-lg font-semibold text-white">{report.top_priority_fix.title}</h2>
              <p className="mb-4 text-sm text-zinc-400">{report.top_priority_fix.description}</p>
              <button
                type="button"
                onClick={() => seekTo(report.top_priority_fix.timestamp)}
                className="cursor-pointer font-mono text-xs tabular-nums text-zinc-400 underline-offset-2 transition-colors hover:text-white hover:underline"
              >
                → {formatTimestamp(report.top_priority_fix.timestamp)}
              </button>
              {report.top_priority_fix.suggested_rewrite ? (
                <div className="mt-4 rounded-xl border border-[#1d9e75] bg-[#0f2a1a] p-3 text-sm text-zinc-300">
                  <span className="mb-1 block font-mono text-xs text-[#1d9e75]">SUGGESTED REWRITE</span>
                  {report.top_priority_fix.suggested_rewrite}
                </div>
              ) : null}
            </div>
          </MarketingScrollReveal>

          {(["pedagogical", "accessibility", "equity", "clarity"] as const).map((cat) => {
            const data = report[cat];
            const labels: Record<string, string> = {
              pedagogical: "Pedagogical Quality",
              accessibility: "Accessibility",
              equity: "Equity & Inclusion",
              clarity: "Clarity & Delivery",
            };

            return (
              <MarketingScrollReveal key={cat}>
                <div className="rounded-2xl border border-white/5 bg-zinc-900/50 p-6 transition-colors hover:border-white/10">
                  <div className="mb-4 flex items-center justify-between gap-4">
                    <h3 className="font-lk-serif text-xl text-white">{labels[cat]}</h3>
                    <ScoreRing score={data.score} />
                  </div>
                  <p className="mb-4 text-sm text-zinc-400">{data.summary}</p>

                  {data.strengths.length > 0 ? (
                    <div className="mb-4">
                      <span className="font-mono text-xs uppercase tracking-wider text-[#1d9e75]">Strengths</span>
                      <ul className="mt-2 space-y-1">
                        {data.strengths.map((s, i) => (
                          <li key={i} className="flex gap-2 text-sm text-zinc-400">
                            <span className="text-[#1d9e75]">+</span> {s}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}

                  {data.issues.length > 0 ? (
                    <div>
                      <span className="font-mono text-xs uppercase tracking-wider text-[#e53e3e]">Issues</span>
                      <div className="mt-2 space-y-3">
                        {data.issues.map((issue, i) => (
                          <div key={i} className="rounded-xl border border-white/5 bg-zinc-950/50 p-3">
                            <div className="mb-2 flex items-start justify-between gap-2">
                              <p className="text-sm text-zinc-400">{issue.description}</p>
                              <button
                                type="button"
                                onClick={() => seekTo(issue.timestamp)}
                                className="whitespace-nowrap font-mono text-xs tabular-nums text-zinc-400 underline-offset-2 transition-colors hover:text-white hover:underline"
                              >
                                {formatTimestamp(issue.timestamp)}
                              </button>
                            </div>
                            {issue.suggested_rewrite ? (
                              <div className="rounded-lg border border-[#1d9e75] bg-[#0f2a1a] p-2 text-xs text-zinc-300">
                                <span className="mb-1 block text-[#1d9e75]">Suggested rewrite:</span>
                                {issue.suggested_rewrite}
                              </div>
                            ) : null}
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </div>
              </MarketingScrollReveal>
            );
          })}

          <MarketingScrollReveal>
            <div className="rounded-2xl border border-white/5 bg-zinc-900/50 p-6 transition-colors hover:border-white/10">
              <h3 className="mb-4 font-lk-serif text-xl text-white">Prioritized Fix List</h3>
              <div className="space-y-3">
                {report.prioritized_fixes.map((fix, i) => (
                  <div key={i} className="flex gap-4 rounded-xl border border-white/5 bg-zinc-950/40 p-3">
                    <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-zinc-700 bg-zinc-800 text-xs font-bold text-white">
                      {fix.priority}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
                        <span className="text-sm font-medium text-white">{fix.title}</span>
                        <div className="flex items-center gap-2">
                          <span className="text-xs capitalize text-zinc-500">{fix.category}</span>
                          <button
                            type="button"
                            onClick={() => seekTo(fix.timestamp)}
                            className="font-mono text-xs tabular-nums text-zinc-400 underline-offset-2 transition-colors hover:text-white hover:underline"
                          >
                            {formatTimestamp(fix.timestamp)}
                          </button>
                        </div>
                      </div>
                      <p className="text-xs text-zinc-400">{fix.description}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </MarketingScrollReveal>
        </div>

        <div className="h-fit space-y-4 lg:sticky lg:top-8">
          <div className="font-mono text-xs uppercase tracking-wider text-zinc-500">Lecture Video</div>
          <div className="aspect-video overflow-hidden rounded-xl border border-white/5">
            <iframe
              ref={iframeRef}
              src={`https://www.youtube.com/embed/${video_id}?enablejsapi=1`}
              className="h-full w-full"
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
              allowFullScreen
              title="Lecture video"
            />
          </div>
          <p className="text-xs text-zinc-500">Click any timestamp in the report to jump to that moment in the video.</p>
          <div className="rounded-xl border border-white/5 bg-zinc-900/50 p-4 transition-colors hover:border-white/10">
            <div className="mb-1 font-mono text-xs text-zinc-500">VIDEO ID</div>
            <div className="font-mono text-xs text-zinc-400">{video_id}</div>
          </div>
        </div>
      </div>
    </div>
  );
}
