import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import type { Report, RiskBand } from '@/types'

const BAND_CLS: Record<RiskBand, string> = {
  HIGH:       'badge-high',
  ELEVATED:   'badge-elevated',
  BORDERLINE: 'badge-borderline',
  LOW:        'badge-low',
}

const STATUS_CLS: Record<string, string> = {
  Pending:   'bg-bx-gold/10 text-bx-gold border border-bx-gold/20',
  Reviewed:  'bg-white/5 text-bx-muted border border-bx-border',
  Escalated: 'bg-amber-500/10 text-amber-400 border border-amber-500/25',
  Closed:    'bg-zinc-800/40 text-zinc-300 border border-zinc-700/40',
}

export default function Reports() {
  const navigate = useNavigate()
  const [filter, setFilter] = useState<string>('All')

  const { data: reports = [] } = useQuery<Report[]>({
    queryKey: ['reports'],
    queryFn: async () => {
      const base = import.meta.env.VITE_API_URL ?? ''
      const res = await fetch(`${base}/api/v1/reports`, {
        headers: { Authorization: `Bearer ${sessionStorage.getItem('bx_token') || 'demo-token'}` },
      })
      if (!res.ok) return []
      const data = await res.json()
      const rawList = Array.isArray(data) ? data : (data.reports || [])
      return rawList.map((r: any) => ({
        id: r.report_id || r.id || 'REP-000',
        excerpt: r.raw_text || r.excerpt || r.narrative || '',
        date: r.created_at ? new Date(r.created_at).toISOString().split('T')[0] : (r.date || '2026-09-10'),
        prob: r.sif_probability ?? r.prob ?? 0.5,
        band: (r.risk_band || r.band || 'LOW') as RiskBand,
        status: r.status || (r.flagged ? 'Escalated' : 'Reviewed'),
      }))
    },
  })

  const bands = ['All', 'HIGH', 'ELEVATED', 'BORDERLINE', 'LOW']
  const visible = filter === 'All'
    ? reports
    : reports.filter((r) => r.band === filter)

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h2 className="font-display text-3xl font-bold text-bx-text mb-1">Reports</h2>
          <p className="text-sm text-bx-secondary">
            Synchronized enterprise safety observations and incident records.
          </p>
        </div>
        <button
          onClick={() => navigate('/dashboard/sif-analysis')}
          className="btn-gold px-5 py-2.5 text-sm"
        >
          + New Analysis
        </button>
      </div>

      <div className="flex items-center gap-2 flex-wrap">
        {bands.map((b) => {
          const count = b === 'All' ? reports.length : reports.filter((r) => r.band === b).length
          const active = filter === b
          return (
            <button
              key={b}
              onClick={() => setFilter(b)}
              className={`flex items-center gap-2 px-3.5 py-1.5 rounded-full text-xs font-medium transition-all ${
                active
                  ? 'bg-bx-gold/10 border border-bx-gold/30 text-bx-gold'
                  : 'bg-bx-card border border-bx-border text-bx-secondary hover:text-bx-text hover:border-bx-subtle'
              }`}
            >
              <span>{b}</span>
              <span className="font-mono text-[0.6rem] text-bx-muted bg-white/5 px-1.5 py-0.2 rounded-full">{count}</span>
            </button>
          )
        })}
      </div>

      <div className="border border-bx-border rounded-xl bg-bx-card overflow-x-auto">
        <table className="w-full text-left text-sm border-collapse">
          <thead>
            <tr className="border-b border-bx-border font-mono text-[0.6rem] uppercase tracking-widest text-bx-muted">
              <th className="p-4">ID</th>
              <th className="p-4">Report Narrative</th>
              <th className="p-4">Date</th>
              <th className="p-4">SIF Prob</th>
              <th className="p-4">Risk Band</th>
              <th className="p-4">Status</th>
              <th className="p-4" />
            </tr>
          </thead>
          <tbody className="divide-y divide-bx-border">
            {visible.map((r) => (
              <tr key={r.id} className="hover:bg-white/[0.02] transition-colors">
                <td className="p-4 font-mono text-xs text-bx-muted whitespace-nowrap">{r.id}</td>
                <td className="p-4 text-bx-text max-w-sm truncate">{r.excerpt}</td>
                <td className="p-4 font-mono text-xs text-bx-muted whitespace-nowrap">{r.date}</td>
                <td className="p-4 font-mono text-xs font-semibold text-bx-text">{(r.prob * 100).toFixed(0)}%</td>
                <td className="p-4 whitespace-nowrap">
                  <span className={BAND_CLS[r.band]}>{r.band}</span>
                </td>
                <td className="p-4 whitespace-nowrap">
                  <span className={`font-mono text-[0.65rem] uppercase tracking-wider px-2 py-0.5 rounded font-semibold ${STATUS_CLS[r.status] || STATUS_CLS['Pending']}`}>
                    {r.status || 'Pending'}
                  </span>
                </td>
                <td className="p-4 text-right whitespace-nowrap">
                  <button
                    onClick={() => navigate('/dashboard/sif-analysis')}
                    className="btn-ghost px-3 py-1 text-xs"
                  >
                    Analyze
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {visible.length === 0 && (
          <div className="p-12 text-center flex flex-col items-center gap-3">
            <p className="font-display text-base text-bx-secondary font-semibold">No reports found</p>
            <p className="text-xs text-bx-muted max-w-[34ch] leading-relaxed">
              Use SIF Analysis to submit safety narratives. New observations will automatically sync to your safety database.
            </p>
            <button onClick={() => navigate('/dashboard/sif-analysis')} className="btn-gold text-xs px-4 py-2 mt-2">
              + Analyze First Report
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
