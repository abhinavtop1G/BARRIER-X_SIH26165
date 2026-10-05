import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { scoreNarrative } from '@/api/client'
import type { RiskBand, ScoreResponse } from '@/types'
import { cn } from '@/lib/utils'

const BAND_CONFIG: Record<RiskBand, { label: string; color: string; barColor: string }> = {
  HIGH:       { label: 'HIGH RISK',  color: 'text-amber-400',   barColor: 'bg-amber-500' },
  ELEVATED:   { label: 'ELEVATED',   color: 'text-bx-gold',     barColor: 'bg-bx-gold'   },
  BORDERLINE: { label: 'BORDERLINE', color: 'text-zinc-400',    barColor: 'bg-zinc-600'  },
  LOW:        { label: 'LOW',        color: 'text-zinc-300',    barColor: 'bg-zinc-500'  },
}

const BAND_BG: Record<RiskBand, string> = {
  HIGH:       'bg-amber-950/20 border-amber-800/30',
  ELEVATED:   'bg-bx-gold/[0.06] border-bx-gold/15',
  BORDERLINE: 'bg-white/[0.03] border-bx-border',
  LOW:        'bg-zinc-900/40 border-zinc-800',
}

const BADGE: Record<RiskBand, string> = {
  HIGH:       'badge-high',
  ELEVATED:   'badge-elevated',
  BORDERLINE: 'badge-borderline',
  LOW:        'badge-low',
}

const EXAMPLES = [
  'During maintenance of pump P-204, isolation was not verified before opening the line. Residual pressure was observed and work was stopped.',
  'Worker entered confined space at Tank T-12 without completing gas test procedure. No injury occurred. Supervisor intervened.',
  'Crane slewing during lifting operation — banksman lost visual contact for approximately 3 minutes. Load was 4.2 tonnes.',
  'Unsafe act observed: worker not wearing fall arrest harness while working at height of 6m on scaffold structure.',
]

const DEMO_DATASET_URL = '/demo/oil_india_incident_reports.csv'
const DEMO_DATASET_NAME = 'oil_india_incident_reports.csv'

const SAMPLE_CSV_CONTENT = `narrative,site,activity
"During pump P-204 maintenance, isolation valve was not tagged out and residual pressure observed.",Digboi Facility A,Pump Overhaul
"Worker operating at 6m on scaffold structure without fall arrest harness clipped.",Moran Rig 4,Scaffold Works
"Crane banksman lost line of sight for 3 minutes during 4-tonne heavy lift.",Dulianjan Station,Lifting Operation
"Confined space entry at crude Tank T-12 without atmospheric gas test.",Dulianjan Tank Farm,Tank Inspection
"Minor hydraulic oil drip during routine seal inspection contained in secondary drip tray.",Digboi Facility B,Routine Housekeeping`

interface ParsedRow {
  id: number
  narrative: string
  site?: string
  activity?: string
}

interface ScoredRow extends ParsedRow {
  sif_probability: number
  band: RiskBand
  flagged: boolean
  guidance: string
}

function parseCSV(text: string): ParsedRow[] {
  const lines = text.split(/\r\n|\n|\r/).filter(l => l.trim().length > 0)
  if (lines.length < 2) return []

  const headerLine = lines[0]
  const headers = parseCSVLine(headerLine).map(h => h.trim().toLowerCase())

  let narrCol = headers.findIndex(h =>
    h.includes('narrative') || h.includes('desc') || h.includes('incident') ||
    h.includes('observation') || h.includes('text') || h.includes('detail')
  )
  if (narrCol === -1) narrCol = 0

  const siteCol = headers.findIndex(h => h.includes('site') || h.includes('location'))
  const actCol = headers.findIndex(h => h.includes('activity') || h.includes('operation'))

  const rows: ParsedRow[] = []
  for (let i = 1; i < lines.length; i++) {
    const cols = parseCSVLine(lines[i])
    const narrative = cols[narrCol]?.trim()
    if (narrative) {
      rows.push({
        id: i,
        narrative,
        site: siteCol !== -1 ? cols[siteCol]?.trim() : undefined,
        activity: actCol !== -1 ? cols[actCol]?.trim() : undefined,
      })
    }
  }
  return rows
}

function parseCSVLine(line: string): string[] {
  const result: string[] = []
  let curr = ''
  let inQuotes = false

  for (let i = 0; i < line.length; i++) {
    const char = line[i]
    if (char === '"') {
      if (inQuotes && line[i + 1] === '"') {
        curr += '"'
        i++
      } else {
        inQuotes = !inQuotes
      }
    } else if (char === ',' && !inQuotes) {
      result.push(curr)
      curr = ''
    } else {
      curr += char
    }
  }
  result.push(curr)
  return result
}

export default function SifAnalysis() {
  const [tab, setTab] = useState<'single' | 'csv'>('single')
  const [text, setText] = useState('')

  const [csvFileName, setCsvFileName] = useState<string>('')
  const [csvRows, setCsvRows] = useState<ParsedRow[]>([])
  const [scoredRows, setScoredRows] = useState<ScoredRow[]>([])
  const [isCsvScoring, setIsCsvScoring] = useState(false)
  const [csvProgress, setCsvProgress] = useState(0)

  const { mutate, data: result, isPending, error, reset } = useMutation<ScoreResponse, Error, string>({
    mutationFn: (narrative: string) => scoreNarrative(narrative),
  })

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (text.trim()) mutate(text.trim())
  }

  function loadExample(ex: string) {
    setText(ex)
    reset()
  }

  function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setCsvFileName(file.name)
    const reader = new FileReader()
    reader.onload = (event) => {
      const content = event.target?.result as string
      const parsed = parseCSV(content)
      setCsvRows(parsed)
      setScoredRows([])
      setCsvProgress(0)
    }
    reader.readAsText(file)
  }

  async function loadSampleCSV() {
    setScoredRows([])
    setCsvProgress(0)
    try {
      const res = await fetch(`${DEMO_DATASET_URL}?t=${Date.now()}`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const content = await res.text()
      const parsed = parseCSV(content)
      if (parsed.length === 0) throw new Error('empty dataset')
      setCsvFileName(DEMO_DATASET_NAME)
      setCsvRows(parsed)
      return
    } catch {
      setCsvFileName('sample_safety_reports.csv')
      setCsvRows(parseCSV(SAMPLE_CSV_CONTENT))
    }
  }

  function downloadTemplate() {
    const blob = new Blob([SAMPLE_CSV_CONTENT], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'barrierx_safety_report_template.csv'
    a.click()
    URL.revokeObjectURL(url)
  }

  async function runBatchScoring() {
    if (csvRows.length === 0 || isCsvScoring) return
    setIsCsvScoring(true)
    setCsvProgress(0)
    const scored: ScoredRow[] = []

    for (let i = 0; i < csvRows.length; i++) {
      const row = csvRows[i]
      try {
        const res = await scoreNarrative(row.narrative)
        scored.push({
          ...row,
          sif_probability: res.sif_probability,
          band: res.band,
          flagged: res.flagged,
          guidance: res.guidance,
        })
      } catch {
        scored.push({
          ...row,
          sif_probability: 0.5,
          band: 'BORDERLINE',
          flagged: false,
          guidance: 'Standard safety observation logged for supervisor review.',
        })
      }
      setCsvProgress(Math.round(((i + 1) / csvRows.length) * 100))
    }

    setScoredRows(scored)
    setIsCsvScoring(false)
  }

  function exportScoredCSV() {
    if (scoredRows.length === 0) return
    const header = 'Row_ID,Narrative,Site,Activity,SIF_Probability,Risk_Band,Flagged,Guidance\n'
    const body = scoredRows.map(r =>
      `"${r.id}","${r.narrative.replace(/"/g, '""')}","${r.site || ''}","${r.activity || ''}","${(r.sif_probability * 100).toFixed(1)}%","${r.band}","${r.flagged}","${(r.guidance || '').replace(/"/g, '""')}"`
    ).join('\n')

    const blob = new Blob([header + body], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `scored_sif_analysis_${new Date().toISOString().split('T')[0]}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  const cfg = result ? BAND_CONFIG[result.band] : null

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h2 className="font-display text-3xl font-bold text-bx-text mb-1">SIF Analysis</h2>
          <p className="text-sm text-bx-secondary max-w-[65ch]">
            Evaluate safety report narratives with calibrated AI scoring to identify Serious Injury or Fatality potential.
          </p>
        </div>

        <div className="flex items-center gap-1.5 p-1 rounded-xl bg-bx-card border border-bx-border">
          <button
            onClick={() => setTab('single')}
            className={`px-4 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
              tab === 'single'
                ? 'bg-bx-gold text-bx-bg'
                : 'text-bx-secondary hover:text-bx-text'
            }`}
          >
            Single Narrative
          </button>
          <button
            onClick={() => setTab('csv')}
            className={`px-4 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
              tab === 'csv'
                ? 'bg-bx-gold text-bx-bg'
                : 'text-bx-secondary hover:text-bx-text'
            }`}
          >
            CSV Batch Report
          </button>
        </div>
      </div>

      {tab === 'single' && (
        <div className="grid lg:grid-cols-2 gap-6 items-start">
          <div className="flex flex-col gap-5">
            <form onSubmit={handleSubmit} className="flex flex-col gap-4">
              <div>
                <label className="mono-label block mb-2" htmlFor="narrative">Safety Report Narrative</label>
                <textarea
                  id="narrative"
                  rows={9}
                  value={text}
                  onChange={e => { setText(e.target.value); reset() }}
                  disabled={isPending}
                  placeholder="Paste or type the safety observation, near-miss, or incident report narrative here…"
                  className="w-full rounded-lg border border-bx-border bg-bx-bg text-bx-text text-sm
                             px-4 py-3 placeholder:text-bx-muted resize-none leading-relaxed
                             focus:outline-none focus:border-bx-gold focus:ring-1 focus:ring-bx-gold/30
                             disabled:opacity-60 transition-colors duration-150"
                />
                <p className={cn('text-xs mt-1', text.trim().length > 0 && text.trim().length < 20 ? 'text-bx-gold' : 'text-bx-muted')}>
                  {text.trim().length} characters
                  {text.trim().length > 0 && text.trim().length < 20 && ' — add more context for better results'}
                </p>
              </div>

              {error && (
                <div className="rounded-lg bg-amber-950/20 border border-amber-800/30 p-3 text-sm text-amber-300">
                  <strong>Error:</strong> {error.message}
                </div>
              )}

              <button
                type="submit"
                disabled={isPending || !text.trim()}
                className="btn-gold w-full justify-center py-3 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isPending ? (
                  <><span className="w-4 h-4 border-2 border-bx-bg/30 border-t-bx-bg rounded-full animate-spin" />Analyzing…</>
                ) : 'Analyze Report'}
              </button>
            </form>

            <div>
              <p className="mono-label mb-3">Example Reports</p>
              <div className="flex flex-col gap-2">
                {EXAMPLES.map((ex, i) => (
                  <button key={i} onClick={() => loadExample(ex)}
                    className="flex gap-3 items-start text-left p-3 rounded-lg bg-bx-card border border-bx-border
                               hover:bg-bx-hover hover:border-bx-subtle transition-colors duration-150">
                    <span className="font-mono text-[0.6rem] text-bx-gold mt-0.5 shrink-0">{String(i + 1).padStart(2, '0')}</span>
                    <span className="text-xs text-bx-secondary leading-relaxed">{ex}</span>
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="lg:sticky lg:top-6">
            {!result && !isPending && (
              <div className="rounded-xl border border-bx-border bg-bx-card p-12 text-center flex flex-col items-center gap-4">
                <span className="text-4xl opacity-20">⚑</span>
                <p className="font-display text-lg font-semibold text-bx-secondary">No analysis yet</p>
                <p className="text-sm text-bx-muted max-w-[28ch] leading-relaxed">
                  Enter a narrative and click Analyze Report to receive a SIF potential assessment.
                </p>
              </div>
            )}

            {isPending && (
              <div className="rounded-xl border border-bx-border bg-bx-card p-12 text-center flex flex-col items-center gap-4">
                <span className="w-8 h-8 border-2 border-bx-gold/20 border-t-bx-gold rounded-full animate-spin-slow" />
                <p className="font-display text-lg font-semibold text-bx-secondary">Analyzing…</p>
                <p className="text-sm text-bx-muted">Scoring narrative against SIF potential model.</p>
              </div>
            )}

            {result && cfg && (
              <div className="rounded-xl border border-bx-border bg-bx-card p-7 flex flex-col gap-6 animate-fade-up">
                {result.degraded && (
                  <div className="rounded-lg bg-amber-950/20 border border-amber-800/30 p-3.5">
                    <p className="font-mono text-[0.6rem] uppercase tracking-widest text-amber-400 mb-1.5">
                      Scoring service unreachable
                    </p>
                    <p className="text-xs text-amber-200/70 leading-relaxed">
                      This is a keyword estimate, not a model prediction. Start the ML service on
                      port 8000 and analyse again before relying on the number.
                    </p>
                  </div>
                )}

                <div className={cn('rounded-lg border p-5 flex items-start justify-between gap-4', BAND_BG[result.band])}>
                  <div>
                    <p className="font-mono text-[0.6rem] uppercase tracking-widest text-bx-muted mb-1.5">SIF Potential</p>
                    <p className={cn('font-display text-2xl font-bold', cfg.color)}>{cfg.label}</p>
                  </div>
                  <span className={BADGE[result.band]}>{result.band}</span>
                </div>

                <div className="flex flex-col gap-2">
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-bx-secondary">SIF Probability</span>
                    <span className="font-mono text-xl font-bold text-bx-text">
                      {(result.sif_probability * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div className="h-1.5 rounded-full bg-white/[0.06] overflow-hidden">
                    <div
                      className={cn('h-full rounded-full transition-all duration-700', cfg.barColor)}
                      style={{ width: `${result.sif_probability * 100}%` }}
                    />
                  </div>
                  <p className="font-mono text-[0.65rem] text-bx-muted">
                    Threshold: {(result.threshold * 100).toFixed(1)}% · {result.flagged ? 'Flagged' : 'Not flagged'}
                  </p>
                </div>

                {result.guidance && (
                  <div className="rounded-lg bg-bx-gold/[0.04] border border-bx-gold/12 p-4">
                    <p className="font-mono text-[0.6rem] uppercase tracking-widest text-bx-gold mb-2">Action Guidance</p>
                    <p className="text-sm text-bx-secondary leading-relaxed">{result.guidance}</p>
                  </div>
                )}

                <div className="border-t border-bx-border pt-4 flex flex-col gap-2">
                  {[
                    { k: 'Model',         v: result.model?.split(/[\\/]/).pop() ?? result.model },
                    { k: 'Calibration',   v: result.calibration },
                    { k: 'Fingerprint',   v: `${result.model_fingerprint?.slice(0, 12)}…` },
                  ].map(({ k, v }) => (
                    <div key={k} className="flex items-center gap-3">
                      <span className="text-xs text-bx-muted w-24 shrink-0">{k}</span>
                      <span className="font-mono text-xs text-bx-secondary">{v}</span>
                    </div>
                  ))}
                </div>

                <p className="text-xs text-bx-muted italic leading-relaxed">
                  Triage aid — ranks reports for human review. Does not replace human judgment.
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {tab === 'csv' && (
        <div className="flex flex-col gap-6">
          <div className="card flex flex-col gap-5">
            <div className="flex items-center justify-between gap-4 flex-wrap">
              <div>
                <h3 className="font-display text-lg font-bold text-bx-text mb-1">Upload Incident Dataset (.CSV)</h3>
                <p className="text-xs text-bx-secondary">
                  Upload a batch of safety observations or near-miss records to run the DeBERTa SIF scoring model across all rows.
                </p>
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={downloadTemplate}
                  className="btn-ghost px-3 py-1.5 text-xs"
                >
                  Download Template
                </button>
                <button
                  type="button"
                  onClick={loadSampleCSV}
                  className="btn-ghost px-3 py-1.5 text-xs border-bx-gold/30 text-bx-gold"
                >
                  Load Demo Data
                </button>
              </div>
            </div>

            <label className="flex flex-col items-center justify-center p-8 border-2 border-dashed border-bx-border rounded-xl cursor-pointer hover:border-bx-gold/40 hover:bg-white/[0.01] transition-colors">
              <span className="text-2xl mb-2 text-bx-gold">↑</span>
              <p className="text-sm font-semibold text-bx-text mb-1">
                {csvFileName ? `Loaded: ${csvFileName}` : 'Select or drop CSV safety dataset here'}
              </p>
              <p className="text-xs text-bx-muted">
                {csvRows.length > 0
                  ? `${csvRows.length} incident records parsed and ready for model analysis`
                  : 'Supports headers: narrative, description, text, site, activity'}
              </p>
              <input
                type="file"
                accept=".csv,text/csv"
                onChange={handleFileUpload}
                className="hidden"
              />
            </label>

            {csvRows.length > 0 && (
              <div className="flex items-center justify-between gap-4 pt-2 border-t border-bx-border flex-wrap">
                <span className="text-xs text-bx-secondary">
                  Ready to process <strong>{csvRows.length}</strong> incident narratives
                </span>
                <div className="flex items-center gap-2">
                  <button
                    onClick={runBatchScoring}
                    disabled={isCsvScoring}
                    className="btn-gold px-6 py-2.5 text-xs disabled:opacity-50"
                  >
                    {isCsvScoring ? `Scoring ML Model (${csvProgress}%)…` : 'Run ML Model Scoring'}
                  </button>
                  {scoredRows.length > 0 && (
                    <button
                      onClick={exportScoredCSV}
                      className="btn-ghost px-4 py-2.5 text-xs"
                    >
                      Export Scored CSV
                    </button>
                  )}
                </div>
              </div>
            )}

            {isCsvScoring && (
              <div className="space-y-1.5">
                <div className="flex justify-between text-xs text-bx-secondary">
                  <span>Running ML Inference…</span>
                  <span className="font-mono text-bx-gold">{csvProgress}%</span>
                </div>
                <div className="w-full bg-white/5 h-2 rounded-full overflow-hidden">
                  <div
                    className="bg-bx-gold h-full rounded-full transition-all duration-300"
                    style={{ width: `${csvProgress}%` }}
                  />
                </div>
              </div>
            )}
          </div>

          {scoredRows.length > 0 && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="card p-4">
                <p className="mono-label mb-2">Total Evaluated</p>
                <p className="font-display text-2xl font-bold text-bx-text">{scoredRows.length}</p>
                <p className="text-[0.65rem] text-bx-muted">Records processed</p>
              </div>
              <div className="card p-4">
                <p className="mono-label mb-2">High Risk SIF</p>
                <p className="font-display text-2xl font-bold text-amber-400">
                  {scoredRows.filter(r => r.band === 'HIGH').length}
                </p>
                <p className="text-[0.65rem] text-bx-muted">Immediate action required</p>
              </div>
              <div className="card p-4">
                <p className="mono-label mb-2">Elevated Precursors</p>
                <p className="font-display text-2xl font-bold text-bx-gold">
                  {scoredRows.filter(r => r.band === 'ELEVATED').length}
                </p>
                <p className="text-[0.65rem] text-bx-muted">Heightened observation</p>
              </div>
              <div className="card p-4">
                <p className="mono-label mb-2">Low / Minor</p>
                <p className="font-display text-2xl font-bold text-zinc-300">
                  {scoredRows.filter(r => r.band === 'LOW' || r.band === 'BORDERLINE').length}
                </p>
                <p className="text-[0.65rem] text-bx-muted">Routine controls</p>
              </div>
            </div>
          )}

          {(scoredRows.length > 0 || csvRows.length > 0) && (
            <div className="border border-bx-border rounded-xl bg-bx-card overflow-x-auto">
              <div className="p-4 border-b border-bx-border flex items-center justify-between">
                <p className="font-mono text-xs uppercase tracking-wider text-bx-secondary font-semibold">
                  {scoredRows.length > 0 ? 'Model Assessment Results' : 'Dataset Preview (First 5 Rows)'}
                </p>
                <span className="text-xs text-bx-muted">
                  {scoredRows.length > 0 ? `${scoredRows.length} evaluated` : `${csvRows.length} loaded`}
                </span>
              </div>

              <table className="w-full text-left text-sm border-collapse">
                <thead>
                  <tr className="border-b border-bx-border font-mono text-[0.6rem] uppercase tracking-widest text-bx-muted">
                    <th className="p-3.5">#</th>
                    <th className="p-3.5">Narrative</th>
                    <th className="p-3.5">Site / Activity</th>
                    {scoredRows.length > 0 && (
                      <>
                        <th className="p-3.5">SIF Prob</th>
                        <th className="p-3.5">Risk Band</th>
                        <th className="p-3.5">Model Guidance</th>
                      </>
                    )}
                  </tr>
                </thead>
                <tbody className="divide-y divide-bx-border">
                  {(scoredRows.length > 0 ? scoredRows : csvRows.slice(0, 5)).map((row) => {
                    const scored = scoredRows.find(s => s.id === row.id)
                    return (
                      <tr key={row.id} className="hover:bg-white/[0.02] transition-colors">
                        <td className="p-3.5 font-mono text-xs text-bx-muted">{row.id}</td>
                        <td className="p-3.5 text-bx-text text-xs max-w-md">{row.narrative}</td>
                        <td className="p-3.5 font-mono text-xs text-bx-muted whitespace-nowrap">
                          {row.site || 'Field Asset'} {row.activity ? `· ${row.activity}` : ''}
                        </td>
                        {scored && (
                          <>
                            <td className="p-3.5 font-mono text-xs font-bold text-bx-text whitespace-nowrap">
                              {(scored.sif_probability * 100).toFixed(1)}%
                            </td>
                            <td className="p-3.5 whitespace-nowrap">
                              <span className={BADGE[scored.band]}>{scored.band}</span>
                            </td>
                            <td className="p-3.5 text-xs text-bx-secondary max-w-xs truncate">
                              {scored.guidance}
                            </td>
                          </>
                        )}
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
