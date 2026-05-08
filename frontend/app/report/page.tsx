'use client'

import { useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import type { FacultySession } from '../../types/lecture'

function formatTimestamp(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
}

function ScoreRing({ score }: { score: number }) {
  const color = score >= 8 ? '#1d9e75' : score >= 6 ? '#5e6ad2' : score >= 4 ? '#ba7517' : '#e53e3e'
  return (
    <div
      className="flex h-12 w-12 items-center justify-center rounded-full border-2 text-sm font-bold"
      style={{ borderColor: color, color }}
    >
      {score}/10
    </div>
  )
}

export default function ReportPage() {
  const router = useRouter()
  const [session, setSession] = useState<FacultySession | null>(null)
  const iframeRef = useRef<HTMLIFrameElement>(null)

  useEffect(() => {
    const stored = window.localStorage.getItem('lecturekit_faculty_session')
    if (!stored) {
      router.push('/app')
      return
    }
    setSession(JSON.parse(stored) as FacultySession)
  }, [router])

  function seekTo(seconds: number) {
    iframeRef.current?.contentWindow?.postMessage(
      JSON.stringify({ event: 'command', func: 'seekTo', args: [seconds, true] }),
      '*'
    )
  }

  if (!session) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#010102]">
        <div className="font-mono text-[#a1a1aa]">Loading report...</div>
      </div>
    )
  }

  const { report, video_id } = session

  return (
    <div className="min-h-screen bg-[#010102] font-['Inter',sans-serif] text-white">
      <div className="flex items-center justify-between border-b border-[#1a1a1a] px-6 py-4">
        <div className="flex items-center gap-3">
          <button
            onClick={() => router.push('/app')}
            className="text-sm text-[#a1a1aa] transition-colors hover:text-white"
          >
            ← Back
          </button>
          <span className="text-[#2a2a2a]">|</span>
          <span className="text-sm font-medium">Faculty Audit Report</span>
          <span className="rounded bg-[#1a1a1a] px-2 py-1 font-mono text-xs text-[#6b7280]">PRIVATE</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-[#6b7280]">Overall</span>
          <ScoreRing score={report.overall_score} />
        </div>
      </div>

      <div className="mx-auto grid max-w-7xl grid-cols-[1fr_400px] gap-8 px-6 py-8">
        <div className="space-y-8">
          <div className="rounded-lg border border-[#ba7517] bg-[#1a1a0a] p-6">
            <div className="mb-3 flex items-center gap-2">
              <span className="font-mono text-xs uppercase tracking-wider text-[#ba7517]">Top Priority Fix</span>
            </div>
            <h2 className="mb-2 text-lg font-semibold">{report.top_priority_fix.title}</h2>
            <p className="mb-4 text-sm text-[#a1a1aa]">{report.top_priority_fix.description}</p>
            <button
              onClick={() => seekTo(report.top_priority_fix.timestamp)}
              className="font-mono text-xs text-[#5e6ad2] transition-colors hover:text-white"
            >
              → {formatTimestamp(report.top_priority_fix.timestamp)}
            </button>
            {report.top_priority_fix.suggested_rewrite ? (
              <div className="mt-4 rounded border border-[#1d9e75] bg-[#0f1a0f] p-3 text-sm text-[#a1a1aa]">
                <span className="mb-1 block font-mono text-xs text-[#1d9e75]">SUGGESTED REWRITE</span>
                {report.top_priority_fix.suggested_rewrite}
              </div>
            ) : null}
          </div>

          {(['pedagogical', 'accessibility', 'equity', 'clarity'] as const).map((cat) => {
            const data = report[cat]
            const labels: Record<string, string> = {
              pedagogical: 'Pedagogical Quality',
              accessibility: 'Accessibility',
              equity: 'Equity & Inclusion',
              clarity: 'Clarity & Delivery',
            }

            return (
              <div key={cat} className="rounded-lg border border-[#1a1a1a] p-6">
                <div className="mb-4 flex items-center justify-between">
                  <h3 className="font-semibold">{labels[cat]}</h3>
                  <ScoreRing score={data.score} />
                </div>
                <p className="mb-4 text-sm text-[#a1a1aa]">{data.summary}</p>

                {data.strengths.length > 0 ? (
                  <div className="mb-4">
                    <span className="font-mono text-xs uppercase tracking-wider text-[#1d9e75]">Strengths</span>
                    <ul className="mt-2 space-y-1">
                      {data.strengths.map((s, i) => (
                        <li key={i} className="flex gap-2 text-sm text-[#a1a1aa]">
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
                        <div key={i} className="rounded bg-[#1a1a1a] p-3">
                          <div className="mb-2 flex items-start justify-between gap-2">
                            <p className="text-sm text-[#a1a1aa]">{issue.description}</p>
                            <button
                              onClick={() => seekTo(issue.timestamp)}
                              className="whitespace-nowrap font-mono text-xs text-[#5e6ad2] transition-colors hover:text-white"
                            >
                              {formatTimestamp(issue.timestamp)}
                            </button>
                          </div>
                          {issue.suggested_rewrite ? (
                            <div className="rounded border border-[#1d9e75] bg-[#0f1a0f] p-2 text-xs text-[#a1a1aa]">
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
            )
          })}

          <div className="rounded-lg border border-[#1a1a1a] p-6">
            <h3 className="mb-4 font-semibold">Prioritized Fix List</h3>
            <div className="space-y-3">
              {report.prioritized_fixes.map((fix, i) => (
                <div key={i} className="flex gap-4 rounded bg-[#1a1a1a] p-3">
                  <div className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-[#5e6ad2] text-xs font-bold">
                    {fix.priority}
                  </div>
                  <div className="flex-1">
                    <div className="mb-1 flex items-center justify-between">
                      <span className="text-sm font-medium">{fix.title}</span>
                      <div className="flex items-center gap-2">
                        <span className="text-xs capitalize text-[#6b7280]">{fix.category}</span>
                        <button
                          onClick={() => seekTo(fix.timestamp)}
                          className="font-mono text-xs text-[#5e6ad2] transition-colors hover:text-white"
                        >
                          {formatTimestamp(fix.timestamp)}
                        </button>
                      </div>
                    </div>
                    <p className="text-xs text-[#a1a1aa]">{fix.description}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="sticky top-8 h-fit space-y-4">
          <div className="font-mono text-xs uppercase tracking-wider text-[#6b7280]">Lecture Video</div>
          <div className="aspect-video overflow-hidden rounded-lg border border-[#1a1a1a]">
            <iframe
              ref={iframeRef}
              src={`https://www.youtube.com/embed/${video_id}?enablejsapi=1`}
              className="h-full w-full"
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
              allowFullScreen
            />
          </div>
          <p className="text-xs text-[#6b7280]">Click any timestamp in the report to jump to that moment in the video.</p>
          <div className="rounded border border-[#1a1a1a] p-3">
            <div className="mb-1 font-mono text-xs text-[#6b7280]">VIDEO ID</div>
            <div className="font-mono text-xs text-[#a1a1aa]">{video_id}</div>
          </div>
        </div>
      </div>
    </div>
  )
}

