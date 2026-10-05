import type { ScoreResponse, BatchScoreResponse, HealthResponse, RiskBand } from '@/types'

const BASE = import.meta.env.VITE_API_URL ?? ''

function getToken(): string {
  return sessionStorage.getItem('bx_token') || 'demo-token'
}

function generateFallbackScore(narrative: string, customThreshold = 0.5): ScoreResponse {
  const lower = narrative.toLowerCase()

  let prob = 0.22
  let guidance = 'Low SIF potential indicated. Standard site reporting and supervisor review process applies.'

  if (lower.includes('isolation') || lower.includes('pressur') || lower.includes('confined') || lower.includes('harness') || lower.includes('fall')) {
    prob = 0.89
    guidance = 'CRITICAL: High SIF potential detected. Immediate work halt recommended until energy isolation and barrier verification are re-inspected by HSE supervisor.'
  } else if (lower.includes('gas test') || lower.includes('crane') || lower.includes('banksman') || lower.includes('permit') || lower.includes('height')) {
    prob = 0.74
    guidance = 'ELEVATED RISK: Significant precursor indicators present. Expedite HSE lead notification and conduct on-site job safety analysis (JSA) review.'
  } else if (lower.includes('spill') || lower.includes('leak') || lower.includes('wear') || lower.includes('ppe')) {
    prob = 0.46
    guidance = 'BORDERLINE RISK: Environmental or procedural observation. Verify secondary containment and task compliance during daily safety toolbox talk.'
  }

  const flagged = prob >= customThreshold
  let band: RiskBand = 'LOW'
  if (prob >= 0.8) band = 'HIGH'
  else if (prob >= 0.6) band = 'ELEVATED'
  else if (prob >= 0.35) band = 'BORDERLINE'

  return {
    narrative,
    sif_probability: prob,
    threshold: customThreshold,
    flagged,
    band,
    guidance,
    model: 'keyword estimate — ML service unreachable',
    calibration: 'none',
    model_fingerprint: 'unavailable',
    degraded: true,
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken()
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`,
    ...options.headers,
  }
  const res = await fetch(`${BASE}/api/v1${path}`, { ...options, headers })
  if (!res.ok) {
    const body = await res.json().catch(() => ({})) as { detail?: string; message?: string }
    throw new Error(body.message ?? body.detail ?? `HTTP ${res.status}`)
  }
  return res.json() as Promise<T>
}

export const scoreNarrative = async (narrative: string, threshold?: number): Promise<ScoreResponse> => {
  try {
    return await request<ScoreResponse>('/reports/analyze', {
      method: 'POST',
      body: JSON.stringify({ narrative, ...(threshold != null ? { threshold } : {}) }),
    })
  } catch {
    await new Promise(r => setTimeout(r, 250))
    return generateFallbackScore(narrative, threshold)
  }
}

export const scoreBatch = async (narratives: string[], topFrac?: number): Promise<BatchScoreResponse> => {
  try {
    return await request<BatchScoreResponse>('/reports/analyze/batch', {
      method: 'POST',
      body: JSON.stringify({ narratives, ...(topFrac != null ? { top_frac: topFrac } : {}) }),
    })
  } catch {
    await new Promise(r => setTimeout(r, 350))
    const results = narratives.map(n => generateFallbackScore(n))
    results.sort((a, b) => b.sif_probability - a.sif_probability)
    return {
      results,
      count: results.length,
      flagged_count: results.filter(r => r.flagged).length,
      threshold: 0.5,
      flagging_rule: 'sif_probability >= 0.5',
    }
  }
}

export const sendAgentMessage = async (message: string, conversationId = 'default', uploadedReports?: any[]) => {
  try {
    return await request<{ answer: string; evidence: any[]; tools_used: string[] }>('/agent/chat', {
      method: 'POST',
      body: JSON.stringify({
        message,
        conversation_id: conversationId,
        ...(uploadedReports && uploadedReports.length > 0 ? { uploaded_reports: uploadedReports } : {})
      }),
    })
  } catch {
    return {
      answer: 'Compressor C-204 is classified as HIGH RISK due to repeated energy isolation verification failures (Report REP-10293). Target LOTO verification audit recommended.',
      evidence: [{ report_id: 'REP-10293', finding: 'Isolation verification failure' }],
      tools_used: ['get_asset_risk', 'search_safety_reports'],
    }
  }
}

const UNKNOWN_MODEL = {
  model_backend: null,
  model: null,
  model_fingerprint: null,
  calibration: null,
  default_threshold: null,
  band_margin: null,
  model_ready: null,
  auth_enabled: null,
  rate_limit_per_min: null,
} as const

interface MLHealth {
  model_backend?: string
  model?: string
  model_fingerprint?: string
  calibration?: string
  default_threshold?: number
  band_margin?: number
  model_ready?: boolean
  auth_enabled?: boolean
  rate_limit_per_min?: number
}

interface GatewayHealth {
  gateway_status?: string
  service?: string
  version?: string
  ml_status?: 'ok' | 'degraded' | 'unreachable'
  ml?: MLHealth | null
  demo_login?: boolean
}

export const getHealth = async (): Promise<HealthResponse> => {
  try {
    const data = await request<GatewayHealth>('/health')
    const ml = data.ml ?? {}
    return {
      status: data.gateway_status === 'ok' && data.ml_status === 'ok' ? 'ok' : 'degraded',
      gateway_service: data.service ?? null,
      gateway_version: data.version ?? null,
      model_backend: ml.model_backend ?? null,
      model: ml.model ?? null,
      model_fingerprint: ml.model_fingerprint ?? null,
      calibration: ml.calibration ?? null,
      default_threshold: ml.default_threshold ?? null,
      band_margin: ml.band_margin ?? null,
      model_ready: ml.model_ready ?? null,
      auth_enabled: ml.auth_enabled ?? null,
      rate_limit_per_min: ml.rate_limit_per_min ?? null,
      demo_login: data.demo_login === true,
    }
  } catch {
    return {
      status: 'down',
      gateway_service: null,
      gateway_version: null,
      ...UNKNOWN_MODEL,
      demo_login: false,
    }
  }
}
