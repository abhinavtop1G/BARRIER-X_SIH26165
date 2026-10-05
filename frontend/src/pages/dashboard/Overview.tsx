import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'

function KpiCard({ label, value, sub, gold = false }: { label: string; value: string | number; sub?: string; gold?: boolean }) {
  return (
    <div className="card">
      <p className="mono-label mb-3">{label}</p>
      <p className={`font-display text-3xl font-bold mb-1 ${gold ? 'text-bx-gold' : 'text-bx-text'}`}>{value}</p>
      {sub && <p className="text-xs text-bx-muted">{sub}</p>}
    </div>
  )
}

export default function Overview() {
  const navigate = useNavigate()

  const { data: summary } = useQuery({
    queryKey: ['summary'],
    queryFn: async () => {
      const base = import.meta.env.VITE_API_URL ?? ''
      const res = await fetch(`${base}/api/v1/dashboard/summary`, {
        headers: { Authorization: `Bearer ${sessionStorage.getItem('bx_token') || 'demo-token'}` },
      })
      if (!res.ok) return { total_reports: 0, sif_potential_reports: 0, high_risk_reports: 0, sif_percentage: 0 }
      return res.json()
    },
  })

  const total     = summary?.total_reports ?? 0
  const sifCount  = summary?.sif_potential_reports ?? 0
  const highCount = summary?.high_risk_reports ?? 0
  const pct       = Number(summary?.sif_percentage ?? 0).toFixed(1)

  return (
    <div className="flex flex-col gap-8">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h2 className="font-display text-3xl font-bold text-bx-text mb-1">Overview</h2>
          <p className="text-sm text-bx-secondary">Safety intelligence summary for active reporting period.</p>
        </div>
        <button onClick={() => navigate('/dashboard/sif-analysis')} className="btn-gold px-5 py-2.5 text-sm">
          Analyze Report
        </button>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard label="Total Reports"    value={total} sub="Active safety records" />
        <KpiCard label="SIF-Potential"    value={sifCount} sub={`${pct}% of total reports`} gold />
        <KpiCard label="High Risk"        value={highCount} sub="Band: HIGH" gold />
        <KpiCard label="Analyzed"         value={total} sub="All processed" />
      </div>

      <div className="card flex items-center justify-between gap-4 p-6 bg-bx-gold/[0.03] border-bx-gold/20">
        <div>
          <h3 className="font-display text-lg font-bold text-bx-text mb-1">Run New Incident Analysis</h3>
          <p className="text-sm text-bx-secondary">Submit observation text to score for Serious Injury or Fatality potential.</p>
        </div>
        <button onClick={() => navigate('/dashboard/sif-analysis')} className="btn-gold text-sm whitespace-nowrap">
          Launch Analysis
        </button>
      </div>

      <div>
        <h3 className="font-display text-lg font-semibold mb-4">Platform Capabilities</h3>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {['Life-Saving Rule Mapping', 'Precursor Pattern Detection', 'Image Report Capture', '3D Safety Digital Twin', 'AI HSE Agent'].map(label => (
            <div key={label}
                 onClick={() => {
                   if (label.includes('3D')) navigate('/dashboard/3d-view')
                   else if (label.includes('Agent')) navigate('/dashboard/agent')
                   else if (label.includes('Life-Saving')) navigate('/dashboard/life-saving')
                   else navigate('/dashboard/precursors')
                 }}
                 className="flex items-center justify-between gap-3 p-4 bg-bx-card border border-bx-border rounded-xl cursor-pointer hover:border-bx-gold/30 transition-colors">
              <span className="text-sm text-bx-secondary font-medium">{label}</span>
              <span className="font-mono text-xs text-bx-gold">View →</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
