export interface GoogleUser {
  sub:     string
  email:   string
  name:    string
  picture: string
}

export interface ScoreResponse {
  narrative:         string
  sif_probability:   number
  threshold:         number
  flagged:           boolean
  band:              RiskBand
  guidance:          string
  model:             string
  calibration:       string
  model_fingerprint: string
  degraded?:         boolean
}

export interface BatchScoreResponse {
  results:        ScoreResponse[]
  count:          number
  flagged_count:  number
  threshold:      number
  flagging_rule:  string
}

export interface HealthResponse {
  status:              'ok' | 'degraded' | 'down'
  gateway_service:     string | null
  gateway_version:     string | null
  model_backend:       string | null
  model:               string | null
  model_fingerprint:   string | null
  calibration:         string | null
  default_threshold:   number | null
  band_margin:         number | null
  model_ready:         boolean | null
  auth_enabled:        boolean | null
  rate_limit_per_min:  number | null
  demo_login:          boolean
}

export type RiskBand = 'HIGH' | 'ELEVATED' | 'BORDERLINE' | 'LOW'

export interface Report {
  id:       string
  excerpt:  string
  date:     string
  band:     RiskBand
  prob:     number
  status:   'Pending' | 'Reviewed' | 'Escalated' | 'Closed'
}
