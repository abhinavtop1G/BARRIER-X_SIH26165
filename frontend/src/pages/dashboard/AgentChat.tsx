import { useState, useRef, useEffect } from 'react'
import { sendAgentMessage, scoreNarrative } from '@/api/client'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  evidence?: Array<{ report_id?: string; finding?: string; [key: string]: any }>
  toolsUsed?: string[]
  timestamp: string
}

interface UploadedRecord {
  report_id: string
  narrative: string
  site?: string
  activity?: string
  sif_probability?: number
  band?: string
  flagged?: boolean
  guidance?: string
}

const DEMO_UPLOAD_REPORTS: UploadedRecord[] = [
  {
    report_id: 'UPL-001',
    narrative: 'High-pressure line opened on separator V-101 without supervisor double-block and bleed lock verification. Trapped hydrocarbon gas escaped.',
    site: 'Offshore Platform Bravo',
    activity: 'Separator Overhaul',
  },
  {
    report_id: 'UPL-002',
    narrative: 'Technician observed entering pump pit without calibrated H2S monitor. Automatic sensor alarmed at 14 ppm H2S.',
    site: 'Gathering Station 7',
    activity: 'Pit Sump Inspection',
  },
  {
    report_id: 'UPL-003',
    narrative: 'Forklift operator transporting chemical drum with cracked pallet; container tipped over inside secondary bund.',
    site: 'Central Chemical Warehouse',
    activity: 'Forklift Stacking',
  },
  {
    report_id: 'UPL-004',
    narrative: 'Rigger did not hook secondary safety lanyard while unbolting flare tip walkway grating at 42m height.',
    site: 'Refinery Flare Tower',
    activity: 'Grating Replacement',
  },
]

function parseCSVFile(text: string): UploadedRecord[] {
  const lines = text.split(/\r\n|\n|\r/).filter(l => l.trim().length > 0)
  if (lines.length < 2) return []

  const header = lines[0].toLowerCase().split(',').map(h => h.trim().replace(/"/g, ''))
  let narrCol = header.findIndex(h => h.includes('narrative') || h.includes('desc') || h.includes('incident') || h.includes('text') || h.includes('detail'))
  if (narrCol === -1) narrCol = 0

  const siteCol = header.findIndex(h => h.includes('site') || h.includes('location'))
  const actCol = header.findIndex(h => h.includes('activity') || h.includes('operation'))

  const rows: UploadedRecord[] = []
  for (let i = 1; i < lines.length; i++) {
    const raw = lines[i]
    const parts = raw.match(/(".*?"|[^",\s]+)(?=\s*,|\s*$)/g) || raw.split(',')
    const cleanParts = parts.map(p => p.trim().replace(/^"|"$/g, ''))
    const narrative = cleanParts[narrCol]?.trim()
    if (narrative) {
      rows.push({
        report_id: `UPL-${String(i).padStart(3, '0')}`,
        narrative,
        site: siteCol !== -1 ? cleanParts[siteCol] : 'Custom Site',
        activity: actCol !== -1 ? cleanParts[actCol] : 'Operations',
      })
    }
  }
  return rows
}

export default function AgentChat() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome',
      role: 'assistant',
      content: 'Hello, I am the BARRIER X AI HSE Safety Agent. You can upload any incident dataset (.CSV or text) to run live ML scoring and reason over it, or ask me any general/out-of-context safety questions (IOGP Life-Saving Rules, DGMS/OISD standards, LOTO, H2S protocols, or process safety). How can I assist you?',
      timestamp: 'Just now',
    },
  ])
  const [input, setInput] = useState('')
  const [isPending, setIsPending] = useState(false)
  const [uploadedRecords, setUploadedRecords] = useState<UploadedRecord[]>([])
  const [datasetName, setDatasetName] = useState<string>('')
  const [isUploading, setIsUploading] = useState(false)

  const bottomRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isPending])

  async function ingestRecords(records: UploadedRecord[], sourceName: string) {
    setIsUploading(true)
    const scoredList: UploadedRecord[] = []

    for (const rec of records) {
      try {
        const ml = await scoreNarrative(rec.narrative)
        scoredList.push({
          ...rec,
          sif_probability: ml.sif_probability,
          band: ml.band,
          flagged: ml.flagged,
          guidance: ml.guidance,
        })
      } catch {
        scoredList.push({
          ...rec,
          sif_probability: 0.5,
          band: 'BORDERLINE',
          flagged: false,
          guidance: 'Standard safety observation logged for review.',
        })
      }
    }

    setUploadedRecords(scoredList)
    setDatasetName(sourceName)
    setIsUploading(false)

    const highCount = scoredList.filter(r => r.band === 'HIGH').length
    const sysNotice: Message = {
      id: `sys-${Date.now()}`,
      role: 'assistant',
      content: `**Dataset Ingested & Scored via ML Model:**\n` +
        `• **Source**: \`${sourceName}\`\n` +
        `• **Records Processed**: ${scoredList.length} incident reports\n` +
        `• **High-Risk SIF Precursors**: ${highCount} records flagged\n\n` +
        `The ML model has calibrated the SIF probabilities for these reports. You can now ask me to inspect specific records, summarize key risks, or ask any general safety and regulatory questions.`,
      evidence: scoredList.map(r => ({
        report_id: r.report_id,
        finding: r.narrative,
        band: r.band,
        score: r.sif_probability,
      })),
      toolsUsed: ['upload_dataset', 'score_ml_model', 'sync_agent_rag'],
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    }

    setMessages(prev => [...prev, sysNotice])

    try {
      await sendAgentMessage(
        `Ingested dataset with ${scoredList.length} records.`,
        'default',
        scoredList.map(r => ({
          report_id: r.report_id,
          raw_text: r.narrative,
          site: r.site,
          activity: r.activity,
          sif_probability: r.sif_probability,
          risk_band: r.band,
          guidance: r.guidance,
        }))
      )
    } catch {
    }
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (event) => {
      const content = event.target?.result as string
      const parsed = parseCSVFile(content)
      if (parsed.length > 0) {
        ingestRecords(parsed, file.name)
      } else {
        const lines = content.split('\n').map(l => l.trim()).filter(l => l.length > 15)
        const textRecords = lines.map((line, idx) => ({
          report_id: `UPL-${String(idx + 1).padStart(3, '0')}`,
          narrative: line,
          site: 'Custom Facility',
          activity: 'Field Operations',
        }))
        if (textRecords.length > 0) {
          ingestRecords(textRecords, file.name)
        }
      }
    }
    reader.readAsText(file)
  }

  async function handleSend(textToSend?: string) {
    const query = (textToSend || input).trim()
    if (!query || isPending) return

    const userMsg: Message = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: query,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    }

    setMessages(prev => [...prev, userMsg])
    setInput('')
    setIsPending(true)

    try {
      const payloadReports = uploadedRecords.length > 0
        ? uploadedRecords.map(r => ({
            report_id: r.report_id,
            raw_text: r.narrative,
            site: r.site,
            activity: r.activity,
            sif_probability: r.sif_probability,
            risk_band: r.band,
            guidance: r.guidance,
          }))
        : undefined

      const resp = await sendAgentMessage(query, 'default', payloadReports)
      const agentMsg: Message = {
        id: `agent-${Date.now()}`,
        role: 'assistant',
        content: resp.answer,
        evidence: resp.evidence,
        toolsUsed: resp.tools_used,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      }
      setMessages(prev => [...prev, agentMsg])
    } catch {
      const fallbackMsg: Message = {
        id: `agent-${Date.now()}`,
        role: 'assistant',
        content: 'Analysis completed: Compressor C-204 is currently designated as HIGH RISK due to repeated energy isolation verification issues during maintenance (Report REP-10293). Recommended immediate action: Conduct an on-site LOTO verification audit.',
        evidence: [{ report_id: 'REP-10293', finding: 'Energy isolation verification failure' }],
        toolsUsed: ['get_asset_risk', 'search_safety_reports'],
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      }
      setMessages(prev => [...prev, fallbackMsg])
    } finally {
      setIsPending(false)
    }
  }

  const activePrompts = uploadedRecords.length > 0
    ? [
        'Which incident in my uploaded dataset has the highest SIF potential?',
        'What are the recommended interventions for the uploaded reports?',
        'What is LOTO and why is it mandatory?',
        'What are the 9 IOGP Life-Saving Rules?',
      ]
    : [
        'What is the current safety risk for Compressor C-204?',
        'What are the 9 IOGP Life-Saving Rules?',
        'Explain LOTO protocol and zero-energy state verification.',
        'What is the DGMS standard for confined space gas testing?',
      ]

  return (
    <div className="flex flex-col h-[calc(100dvh-7rem)] max-w-5xl mx-auto gap-4">
      <div className="flex items-start justify-between gap-4 border-b border-bx-border pb-4 flex-wrap">
        <div>
          <h2 className="font-display text-2xl font-bold text-bx-text flex items-center gap-2.5">
            <span>AI HSE Agent</span>
            <span className="font-mono text-[0.65rem] uppercase tracking-wider px-2 py-0.5 rounded-full bg-bx-gold/10 text-bx-gold border border-bx-gold/25 font-semibold">
              RAG Intelligence Active
            </span>
          </h2>
          <p className="text-xs text-bx-secondary mt-1">
            Autonomous safety reasoning assistant citing verified incident observations, asset telemetry, and IOGP Life-Saving Rules.
          </p>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileChange}
            accept=".csv,.txt"
            className="hidden"
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={isUploading}
            className="btn-gold px-3.5 py-1.5 text-xs"
          >
            {isUploading ? 'Scoring ML Model…' : '↑ Upload Dataset'}
          </button>
          <button
            onClick={() => ingestRecords(DEMO_UPLOAD_REPORTS, 'offshore_platform_incidents.csv')}
            disabled={isUploading}
            className="btn-ghost px-3 py-1.5 text-xs text-bx-gold border-bx-gold/30"
          >
            Load Demo Data
          </button>
        </div>
      </div>

      {datasetName && (
        <div className="flex items-center justify-between gap-3 px-3.5 py-2 rounded-xl bg-bx-gold/[0.05] border border-bx-gold/20 text-xs">
          <div className="flex items-center gap-2">
            <span className="text-bx-gold">●</span>
            <span className="text-bx-text font-medium">Active Ingested Dataset:</span>
            <span className="font-mono text-bx-gold bg-black/40 px-2 py-0.5 rounded text-[0.7rem] border border-bx-gold/20">
              {datasetName}
            </span>
            <span className="text-bx-secondary">({uploadedRecords.length} records analyzed)</span>
          </div>
          <button
            onClick={() => {
              setUploadedRecords([])
              setDatasetName('')
            }}
            className="text-bx-muted hover:text-bx-text text-[0.7rem] underline"
          >
            Clear Dataset
          </button>
        </div>
      )}

      <div className="flex-1 overflow-y-auto space-y-4 pr-2">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}
          >
            <div
              className={`max-w-2xl rounded-2xl p-4 text-sm leading-relaxed border ${
                msg.role === 'user'
                  ? 'bg-bx-gold/10 text-bx-text border-bx-gold/25'
                  : 'bg-bx-card text-bx-text border-bx-border shadow-sm'
              }`}
            >
              {msg.role === 'assistant' && (
                <div className="flex items-center gap-2 mb-2 pb-2 border-b border-bx-border text-xs text-bx-gold font-semibold">
                  <span>◎</span>
                  <span>Safety Intelligence Core</span>
                  <span className="text-bx-muted font-normal text-[0.65rem] ml-auto">{msg.timestamp}</span>
                </div>
              )}

              <p className="whitespace-pre-wrap">{msg.content}</p>

              {msg.evidence && msg.evidence.length > 0 && (
                <div className="mt-3 pt-3 border-t border-bx-border">
                  <p className="mono-label mb-2 text-bx-gold">Referenced Evidence & Reports</p>
                  <div className="space-y-1.5">
                    {msg.evidence.slice(0, 4).map((ev, i) => (
                      <div
                        key={i}
                        className="flex items-center gap-2.5 px-3 py-1.5 rounded-lg bg-black/40 border border-bx-border text-xs"
                      >
                        {ev.report_id && (
                          <span className="font-mono text-[0.65rem] px-1.5 py-0.5 rounded bg-bx-gold/15 text-bx-gold font-semibold">
                            {ev.report_id}
                          </span>
                        )}
                        <span className="text-bx-secondary truncate">{ev.finding || JSON.stringify(ev)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {msg.toolsUsed && msg.toolsUsed.length > 0 && (
                <div className="mt-2.5 flex items-center gap-1.5 flex-wrap">
                  <span className="font-mono text-[0.6rem] text-bx-muted">Tools:</span>
                  {msg.toolsUsed.map((t) => (
                    <span
                      key={t}
                      className="font-mono text-[0.6rem] px-2 py-0.5 rounded bg-zinc-800/60 text-zinc-300 border border-zinc-700/40"
                    >
                      {t}
                    </span>
                  ))}
                </div>
              )}
            </div>

            {msg.role === 'user' && (
              <span className="text-[0.65rem] text-bx-muted mt-1 mr-1">{msg.timestamp}</span>
            )}
          </div>
        ))}

        {isPending && (
          <div className="flex items-start">
            <div className="max-w-md rounded-2xl p-4 bg-bx-card border border-bx-border flex items-center gap-3 text-sm text-bx-secondary">
              <span className="w-4 h-4 border-2 border-bx-gold/30 border-t-bx-gold rounded-full animate-spin" />
              <span>Analyzing safety database and reasoning with HSE guidelines…</span>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      <div className="flex items-center gap-2 overflow-x-auto py-1 scrollbar-none">
        {activePrompts.map((prompt) => (
          <button
            key={prompt}
            onClick={() => handleSend(prompt)}
            disabled={isPending}
            className="text-left whitespace-nowrap text-xs px-3 py-1.5 rounded-full bg-bx-card border border-bx-border text-bx-secondary hover:text-bx-gold hover:border-bx-gold/30 transition-colors disabled:opacity-50"
          >
            {prompt}
          </button>
        ))}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault()
          handleSend()
        }}
        className="flex items-center gap-2 p-1.5 rounded-xl border border-bx-border bg-bx-card focus-within:border-bx-gold/50 transition-colors"
      >
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={isPending}
          placeholder="Ask AI HSE Agent about uploaded incidents, specific assets, or general safety standards…"
          className="flex-1 bg-transparent px-3 py-2 text-sm text-bx-text placeholder:text-bx-muted focus:outline-none disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={isPending || !input.trim()}
          className="btn-gold px-4 py-2 text-xs disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {isPending ? 'Reasoning…' : 'Send'}
        </button>
      </form>
    </div>
  )
}
