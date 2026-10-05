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
  status:              'ok' | 'degraded'
  model_backend:       string
  model:               string
  model_fingerprint:   string
  calibration:         string
  default_threshold:   number
  band_margin:         number
  model_ready:         boolean
  auth_enabled:        boolean
  rate_limit_per_min:  number
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
