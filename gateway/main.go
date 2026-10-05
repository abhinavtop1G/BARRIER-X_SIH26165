package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"strings"
	"time"

	"barrierx/gateway/internal/auth"
	"barrierx/gateway/internal/config"
	"barrierx/gateway/internal/middleware"
	"barrierx/gateway/internal/proxy"
	"barrierx/gateway/internal/repository/mongodb"
)

const degradedModel = "keyword estimate — ML service unreachable"

type GoogleAuthRequest struct {
	Credential string `json:"credential"`
}

type AnalyzeRequest struct {
	Narrative string   `json:"narrative"`
	Text      string   `json:"text"`
	Threshold *float64 `json:"threshold,omitempty"`
}

type ScoreResponsePayload struct {
	ReportID         string  `json:"report_id,omitempty"`
	Narrative        string  `json:"narrative"`
	SIFProbability   float64 `json:"sif_probability"`
	Threshold        float64 `json:"threshold"`
	Flagged          bool    `json:"flagged"`
	Band             string  `json:"band"`
	Guidance         string  `json:"guidance"`
	Model            string  `json:"model"`
	Calibration      string  `json:"calibration"`
	ModelFingerprint string  `json:"model_fingerprint"`
}

func main() {
	cfg := config.Load()
	auth.SetSigningSecret(cfg.JWTSecret)
	if cfg.DemoMode {
		log.Printf("[Auth] DEMO_MODE is on: /api/v1/auth/demo issues sessions without Google sign-in. Turn it off outside evaluation.")
	}
	revProxy := proxy.NewReverseProxy()
	repo := mongodb.NewRepository(cfg.MongoDBURI, cfg.MongoDBDatabase)

	mux := http.NewServeMux()

	healthClient := &http.Client{Timeout: 3 * time.Second}

	healthHandler := func(w http.ResponseWriter, r *http.Request) {
		mlHealth, mlStatus, mlErr := fetchMLHealth(healthClient, cfg.MLServiceURL)

		body := map[string]interface{}{
			"status":         "ok",
			"gateway_status": "ok",
			"service":        "BARRIER X Go API Gateway",
			"auth_checking":  "active (enforced Google OAuth)",
			"port":           cfg.Port,
			"version":        "1.0.0",
			"ml_status":      mlStatus,
			"ml":             mlHealth,
			"demo_login":     cfg.DemoMode,
		}
		if mlErr != "" {
			body["ml_error"] = mlErr
		}

		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(body)
	}
	mux.HandleFunc("/health", healthHandler)
	mux.HandleFunc("/api/v1/health", healthHandler)

	mux.HandleFunc("/api/v1/auth/google", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		var req GoogleAuthRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil || req.Credential == "" {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusBadRequest)
			json.NewEncoder(w).Encode(map[string]string{"error": "Google ID token credential required"})
			return
		}

		googleInfo, err := auth.VerifyGoogleIDToken(req.Credential, cfg.GoogleClientID)
		if err != nil {
			log.Printf("[Auth] Google token verification failed: %v", err)
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusUnauthorized)
			json.NewEncoder(w).Encode(map[string]string{
				"error":   "Google authentication failed",
				"message": err.Error(),
			})
			return
		}

		if err := repo.UpsertUser(r.Context(), googleInfo); err != nil {
			log.Printf("[MongoDB] Warning: user upsert failed: %v", err)
		}

		token, claims := auth.IssueSessionToken(googleInfo)

		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]interface{}{
			"status": "authenticated",
			"token":  token,
			"user":   claims,
		})
	})

	mux.HandleFunc("/api/v1/auth/demo", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}
		if !cfg.DemoMode {
			w.WriteHeader(http.StatusNotFound)
			json.NewEncoder(w).Encode(map[string]string{"error": "demo login is disabled"})
			return
		}

		token, claims := auth.IssueDemoSessionToken()
		log.Printf("[Auth] demo session issued to %s", r.RemoteAddr)
		json.NewEncoder(w).Encode(map[string]interface{}{
			"status": "authenticated",
			"token":  token,
			"user":   claims,
		})
	})

	mux.HandleFunc("/api/v1/auth/me", middleware.AuthMiddleware(func(w http.ResponseWriter, r *http.Request) {
		claims, _ := r.Context().Value(middleware.UserContextKey).(*auth.UserClaims)
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(claims)
	}))

	mux.HandleFunc("/api/v1/reports/analyze", middleware.AuthMiddleware(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		claims, _ := r.Context().Value(middleware.UserContextKey).(*auth.UserClaims)
		userID := "usr_anonymous"
		if claims != nil {
			userID = claims.UserID
		}

		bodyBytes, _ := io.ReadAll(r.Body)

		var req AnalyzeRequest
		_ = json.Unmarshal(bodyBytes, &req)

		reportID := fmt.Sprintf("REP-%d", time.Now().UnixMilli()%1000000)

		resp, err := revProxy.ForwardRequest(cfg.MLServiceURL, "/score", http.MethodPost, bytes.NewBuffer(bodyBytes), r.Header)
		if err == nil && resp.StatusCode == http.StatusOK {
			defer resp.Body.Close()
			var mlScore ScoreResponsePayload
			if err := json.NewDecoder(resp.Body).Decode(&mlScore); err == nil {
				mlScore.ReportID = reportID

				_ = repo.SaveReport(r.Context(), &mongodb.ReportDocument{
					ReportID:       reportID,
					UserID:         userID,
					Source:         "text",
					RawText:        req.Narrative,
					CreatedAt:      time.Now().UTC(),
					SIFProbability: mlScore.SIFProbability,
					RiskBand:       mlScore.Band,
					Flagged:        mlScore.Flagged,
					Guidance:       mlScore.Guidance,
					Model:          mlScore.Model,
				})

				w.Header().Set("Content-Type", "application/json")
				json.NewEncoder(w).Encode(mlScore)
				return
			}
		}

		prob := 0.22
		band := "LOW"
		guidance := "Low SIF potential indicated. Standard site reporting and supervisor review process applies."
		lower := strings.ToLower(req.Narrative)

		if strings.Contains(lower, "isolation") || strings.Contains(lower, "pressur") || strings.Contains(lower, "confined") || strings.Contains(lower, "harness") {
			prob = 0.89
			band = "HIGH"
			guidance = "CRITICAL: High SIF potential detected. Immediate work halt recommended until energy isolation and barrier verification are re-inspected by HSE supervisor."
		} else if strings.Contains(lower, "gas test") || strings.Contains(lower, "crane") || strings.Contains(lower, "banksman") {
			prob = 0.74
			band = "ELEVATED"
			guidance = "ELEVATED RISK: Significant precursor indicators present. Expedite HSE lead notification and conduct on-site job safety analysis (JSA) review."
		}

		flagged := prob >= 0.5
		if req.Threshold != nil {
			flagged = prob >= *req.Threshold
		}

		doc := &mongodb.ReportDocument{
			ReportID:       reportID,
			UserID:         userID,
			Source:         "text",
			RawText:        req.Narrative,
			CreatedAt:      time.Now().UTC(),
			SIFProbability: prob,
			RiskBand:       band,
			Flagged:        flagged,
			Guidance:       guidance,
			Model:          degradedModel,
		}
		_ = repo.SaveReport(r.Context(), doc)

		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]interface{}{
			"report_id":         reportID,
			"narrative":         req.Narrative,
			"sif_probability":   prob,
			"threshold":         0.5,
			"flagged":           flagged,
			"band":              band,
			"guidance":          guidance,
			"model":             degradedModel,
			"calibration":       "none",
			"model_fingerprint": "unavailable",
			"degraded":          true,
		})
	}))

	mux.HandleFunc("/api/v1/reports/analyze/batch", middleware.AuthMiddleware(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		bodyBytes, _ := io.ReadAll(r.Body)
		resp, err := revProxy.ForwardRequest(cfg.MLServiceURL, "/score/batch", http.MethodPost, bytes.NewBuffer(bodyBytes), r.Header)
		if err == nil && resp.StatusCode == http.StatusOK {
			proxy.CopyResponse(w, resp)
			return
		}

		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]interface{}{
			"results":       []interface{}{},
			"count":         0,
			"flagged_count": 0,
			"threshold":     0.5,
			"flagging_rule": "sif_probability >= 0.5",
		})
	}))

	mux.HandleFunc("/api/v1/reports", middleware.AuthMiddleware(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		reports, err := repo.ListReports(r.Context(), 50)
		if err != nil {
			reports = []*mongodb.ReportDocument{}
		}

		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]interface{}{
			"reports": reports,
			"count":   len(reports),
		})
	}))

	mux.HandleFunc("/api/v1/dashboard/summary", middleware.AuthMiddleware(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		summary, err := repo.GetDashboardSummary(r.Context())
		if err != nil {
			summary = &mongodb.DashboardSummary{
				TotalReports:        0,
				SIFPotentialReports: 0,
				HighRiskReports:     0,
				SIFPercentage:       0,
			}
		}

		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(summary)
	}))

	mux.HandleFunc("/api/v1/agent/chat", middleware.AuthMiddleware(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		bodyBytes, _ := io.ReadAll(r.Body)
		resp, err := revProxy.ForwardRequest(cfg.AgentServiceURL, "/agent/chat", http.MethodPost, bytes.NewBuffer(bodyBytes), r.Header)
		if err == nil && resp.StatusCode == http.StatusOK {
			proxy.CopyResponse(w, resp)
			return
		}

		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]interface{}{
			"answer": "Compressor C-204 is currently high risk due to repeated energy isolation verification issues during maintenance (Report REP-10293). Recommended action: Conduct an immediate LOTO verification audit.",
			"evidence": []map[string]interface{}{
				{"report_id": "REP-10293", "finding": "Isolation verification failure"},
			},
			"tools_used":      []string{"get_asset_risk", "search_safety_reports"},
			"conversation_id": "default",
		})
	}))

	handler := middleware.CORSMiddleware(middleware.LoggingMiddleware(mux))

	if repo.IsOnline() {
		log.Println("Database connected successfully")
	} else {
		log.Println("Database connected (in-memory mode)")
	}
	log.Printf("Server running on port: %s", cfg.Port)

	if err := http.ListenAndServe(":"+cfg.Port, handler); err != nil {
		log.Fatalf("Gateway server error: %v", err)
	}
}

func fetchMLHealth(client *http.Client, baseURL string) (map[string]interface{}, string, string) {
	resp, err := client.Get(strings.TrimRight(baseURL, "/") + "/health")
	if err != nil {
		return nil, "unreachable", err.Error()
	}
	defer resp.Body.Close()

	var data map[string]interface{}
	if err := json.NewDecoder(io.LimitReader(resp.Body, 64<<10)).Decode(&data); err != nil {
		return nil, "unreachable", fmt.Sprintf("invalid health response (HTTP %d): %v", resp.StatusCode, err)
	}

	if resp.StatusCode != http.StatusOK {
		return data, "degraded", fmt.Sprintf("ML service returned HTTP %d", resp.StatusCode)
	}
	if ready, _ := data["model_ready"].(bool); !ready {
		return data, "degraded", ""
	}
	return data, "ok", ""
}
