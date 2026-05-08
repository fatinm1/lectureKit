'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import type { ObjectiveAnalysis, ProvostSession } from '../../types/lecture'

function CoverageBar({ score }: { score: number }) {
  const color = score >= 8 ? '#1d9e75' : score >= 5 ? '#ba7517' : '#e53e3e'
  return (
    <div className="flex items-center gap-3">
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-[#1a1a1a]">
        <div className="h-full rounded-full transition-all" style={{ width: `${score * 10}%`, backgroundColor: color }} />
      </div>
      <span className="font-mono text-xs" style={{ color }}>
        {score}/10
      </span>
    </div>
  )
}

function StatusBadge({ status }: { status: 'covered' | 'partial' | 'missing' }) {
  const styles: Record<string, string> = {
    covered: 'bg-[#0f2a1a] text-[#1d9e75] border-[#1d9e75]',
    partial: 'bg-[#1a1a0a] text-[#ba7517] border-[#ba7517]',
    missing: 'bg-[#2a0a0a] text-[#e53e3e] border-[#e53e3e]',
  }
  const labels: Record<string, string> = {
    covered: 'Covered',
    partial: 'Partial',
    missing: 'Missing',
  }
  return <span className={`rounded border px-2 py-1 font-mono text-xs ${styles[status]}`}>{labels[status]}</span>
}

export default function CurriculumPage() {
  const router = useRouter()
  const [session, setSession] = useState<ProvostSession | null>(null)

  useEffect(() => {
    const stored = window.localStorage.getItem('lecturekit_provost_session')
    if (!stored) {
      router.push('/app')
      return
    }
    setSession(JSON.parse(stored) as ProvostSession)
  }, [router])

  if (!session) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#010102]">
        <div className="font-mono text-[#a1a1aa]">Loading curriculum map...</div>
      </div>
    )
  }

  const { curriculum_map, lecture_count, video_ids } = session
  const { coverage_distribution } = curriculum_map

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
          <span className="text-sm font-medium">Curriculum Coverage Map</span>
          <span className="rounded bg-[#1a1a1a] px-2 py-1 font-mono text-xs text-[#6b7280]">{lecture_count} LECTURES</span>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <span className="font-mono text-xs text-[#1d9e75]">{coverage_distribution.fully_covered} covered</span>
            <span className="font-mono text-xs text-[#ba7517]">{coverage_distribution.partially_covered} partial</span>
            <span className="font-mono text-xs text-[#e53e3e]">{coverage_distribution.not_covered} missing</span>
          </div>
          <div className="font-mono text-sm text-[#5e6ad2]">{curriculum_map.overall_coverage_score}/10</div>
        </div>
      </div>

      <div className="mx-auto max-w-6xl space-y-8 px-6 py-8">
        <div className="rounded-lg border border-[#1a1a1a] p-6">
          <h2 className="mb-3 font-mono text-sm uppercase tracking-wider text-[#6b7280]">Executive Summary</h2>
          <p className="leading-relaxed text-[#a1a1aa]">{curriculum_map.executive_summary}</p>
        </div>

        <div className="grid grid-cols-3 gap-4">
          {[
            { label: 'Fully Covered', count: coverage_distribution.fully_covered, color: '#1d9e75' },
            { label: 'Partially Covered', count: coverage_distribution.partially_covered, color: '#ba7517' },
            { label: 'Not Covered', count: coverage_distribution.not_covered, color: '#e53e3e' },
          ].map((item) => (
            <div key={item.label} className="rounded-lg border border-[#1a1a1a] p-4 text-center">
              <div className="mb-1 text-3xl font-bold" style={{ color: item.color }}>
                {item.count}
              </div>
              <div className="text-xs text-[#6b7280]">{item.label}</div>
            </div>
          ))}
        </div>

        <div>
          <h2 className="mb-4 font-mono text-sm uppercase tracking-wider text-[#6b7280]">Learning Objectives</h2>
          <div className="space-y-4">
            {curriculum_map.objectives_analysis.map((obj: ObjectiveAnalysis, i: number) => (
              <div key={i} className="rounded-lg border border-[#1a1a1a] p-5">
                <div className="mb-3 flex items-start justify-between gap-4">
                  <div className="flex items-start gap-3">
                    <span className="mt-1 font-mono text-xs text-[#6b7280]">#{i + 1}</span>
                    <p className="text-sm font-medium">{obj.objective}</p>
                  </div>
                  <StatusBadge status={obj.coverage_status} />
                </div>
                <CoverageBar score={obj.coverage_score} />
                {obj.evidence ? (
                  <p className="mt-3 text-xs text-[#6b7280]">
                    <span className="text-[#5e6ad2]">Evidence: </span>
                    {obj.evidence}
                  </p>
                ) : null}
                {obj.gaps && obj.coverage_status !== 'covered' ? (
                  <p className="mt-2 text-xs text-[#e53e3e]">
                    <span className="font-mono">Gap: </span>
                    {obj.gaps}
                  </p>
                ) : null}
                {obj.lectures_covering.length > 0 ? (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {obj.lectures_covering.map((l) => (
                      <span key={l} className="rounded bg-[#1a1a1a] px-2 py-0.5 font-mono text-xs text-[#a1a1aa]">
                        Lecture {l}
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-lg border border-[#0f2a1a] bg-[#0a1a0a] p-6">
          <h2 className="mb-4 font-mono text-sm uppercase tracking-wider text-[#1d9e75]">Curriculum Strengths</h2>
          <ul className="space-y-2">
            {curriculum_map.curriculum_strengths.map((s, i) => (
              <li key={i} className="flex gap-2 text-sm text-[#a1a1aa]">
                <span className="text-[#1d9e75]">+</span> {s}
              </li>
            ))}
          </ul>
        </div>

        <div>
          <h2 className="mb-4 font-mono text-sm uppercase tracking-wider text-[#6b7280]">Critical Gaps</h2>
          <div className="space-y-3">
            {curriculum_map.critical_gaps.map((gap, i) => (
              <div key={i} className="rounded-lg border border-[#2a0a0a] bg-[#1a0a0a] p-4">
                <p className="mb-1 text-sm font-medium text-[#e53e3e]">{gap.gap}</p>
                <p className="mb-2 text-xs text-[#a1a1aa]">{gap.impact}</p>
                <p className="text-xs text-[#5e6ad2]">→ {gap.recommendation}</p>
              </div>
            ))}
          </div>
        </div>

        <div>
          <h2 className="mb-4 font-mono text-sm uppercase tracking-wider text-[#6b7280]">Prioritized Recommendations</h2>
          <div className="space-y-3">
            {curriculum_map.recommendations.map((rec, i) => (
              <div key={i} className="flex gap-4 rounded-lg border border-[#1a1a1a] p-4">
                <div className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-[#5e6ad2] text-xs font-bold">
                  {rec.priority}
                </div>
                <div>
                  <p className="mb-1 text-sm font-medium">{rec.recommendation}</p>
                  <p className="text-xs text-[#6b7280]">{rec.rationale}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-lg border border-[#1a1a1a] p-4">
          <h2 className="mb-3 font-mono text-xs uppercase tracking-wider text-[#6b7280]">Lectures Analyzed</h2>
          <div className="flex flex-wrap gap-2">
            {video_ids.map((id, i) => (
              <a
                key={id}
                href={`https://www.youtube.com/watch?v=${id}`}
                target="_blank"
                rel="noopener noreferrer"
                className="rounded bg-[#1a1a1a] px-2 py-1 font-mono text-xs text-[#5e6ad2] transition-colors hover:text-white"
              >
                Lecture {i + 1}: {id}
              </a>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

