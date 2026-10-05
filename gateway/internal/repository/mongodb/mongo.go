package mongodb

import (
	"context"
	"fmt"
	"strings"
	"sync"
	"time"

	"barrierx/gateway/internal/auth"

	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/bson/primitive"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
)

type UserDocument struct {
	ID          primitive.ObjectID `bson:"_id,omitempty" json:"id"`
	GoogleID    string             `bson:"google_id" json:"google_id"`
	Email       string             `bson:"email" json:"email"`
	Name        string             `bson:"name" json:"name"`
	Picture     string             `bson:"picture" json:"picture"`
	Role        string             `bson:"role" json:"role"`
	CreatedAt   time.Time          `bson:"created_at" json:"created_at"`
	LastLoginAt time.Time          `bson:"last_login_at" json:"last_login_at"`
}

type ReportDocument struct {
	ID             primitive.ObjectID `bson:"_id,omitempty" json:"id"`
	ReportID       string             `bson:"report_id" json:"report_id"`
	UserID         string             `bson:"user_id" json:"user_id"`
	Source         string             `bson:"source" json:"source"`
	RawText        string             `bson:"raw_text" json:"raw_text"`
	CreatedAt      time.Time          `bson:"created_at" json:"created_at"`
	SIFProbability float64            `bson:"sif_probability" json:"sif_probability"`
	RiskBand       string             `bson:"risk_band" json:"risk_band"`
	Flagged        bool               `bson:"flagged" json:"flagged"`
	Guidance       string             `bson:"guidance" json:"guidance"`
	Model          string             `bson:"model" json:"model"`
	Site           string             `bson:"site,omitempty" json:"site,omitempty"`
	Activity       string             `bson:"activity,omitempty" json:"activity,omitempty"`
}

type DashboardSummary struct {
	TotalReports        int64   `json:"total_reports"`
	SIFPotentialReports int64   `json:"sif_potential_reports"`
	HighRiskReports     int64   `json:"high_risk_reports"`
	SIFPercentage       float64 `json:"sif_percentage"`
}

type Repository struct {
	client     *mongo.Client
	db         *mongo.Database
	users      *mongo.Collection
	reports    *mongo.Collection
	isOnline   bool
	mu         sync.RWMutex
	memReports []*ReportDocument
}

func NewRepository(uri string, dbName string) *Repository {
	repo := &Repository{
		isOnline:   false,
		memReports: seedDefaultReports(),
	}

	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()

	clientOptions := options.Client().ApplyURI(uri).SetServerSelectionTimeout(3 * time.Second)
	client, err := mongo.Connect(ctx, clientOptions)
	if err != nil {
		return repo
	}

	if err := client.Ping(ctx, nil); err != nil {
		return repo
	}

	db := client.Database(dbName)
	repo.client = client
	repo.db = db
	repo.users = db.Collection("users")
	repo.reports = db.Collection("reports")
	repo.isOnline = true

	go func() {
		bgCtx, bgCancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer bgCancel()
		_, _ = repo.users.Indexes().CreateOne(bgCtx, mongo.IndexModel{
			Keys:    bson.D{{Key: "google_id", Value: 1}},
			Options: options.Index().SetUnique(true),
		})
		_, _ = repo.reports.Indexes().CreateOne(bgCtx, mongo.IndexModel{
			Keys: bson.D{{Key: "report_id", Value: 1}},
		})
	}()

	return repo
}

func MaskURI(rawURI string) string {
	if atIdx := strings.Index(rawURI, "@"); atIdx != -1 {
		schemeIdx := strings.Index(rawURI, "://")
		if schemeIdx != -1 {
			scheme := rawURI[:schemeIdx+3]
			hostPart := rawURI[atIdx+1:]
			return scheme + "****:****@" + hostPart
		}
	}
	return rawURI
}

func GetClusterHost(rawURI string) string {
	if atIdx := strings.Index(rawURI, "@"); atIdx != -1 {
		host := rawURI[atIdx+1:]
		if slashIdx := strings.Index(host, "/"); slashIdx != -1 {
			return host[:slashIdx]
		}
		if qIdx := strings.Index(host, "?"); qIdx != -1 {
			return host[:qIdx]
		}
		return host
	}
	if schemeIdx := strings.Index(rawURI, "://"); schemeIdx != -1 {
		host := rawURI[schemeIdx+3:]
		if slashIdx := strings.Index(host, "/"); slashIdx != -1 {
			return host[:slashIdx]
		}
		return host
	}
	return "localhost:27017"
}

func (r *Repository) IsOnline() bool {
	return r.isOnline
}

func (r *Repository) UpsertUser(ctx context.Context, info *auth.GoogleTokenInfo) error {
	r.mu.Lock()
	defer r.mu.Unlock()

	if !r.isOnline || r.users == nil {
		return nil
	}

	now := time.Now().UTC()
	filter := bson.M{"google_id": info.Sub}
	update := bson.M{
		"$set": bson.M{
			"email":         info.Email,
			"name":          info.Name,
			"picture":       info.Picture,
			"last_login_at": now,
		},
		"$setOnInsert": bson.M{
			"google_id":  info.Sub,
			"role":       "hse_administrator",
			"created_at": now,
		},
	}
	opts := options.Update().SetUpsert(true)
	_, err := r.users.UpdateOne(ctx, filter, update, opts)
	return err
}

func (r *Repository) SaveReport(ctx context.Context, report *ReportDocument) error {
	r.mu.Lock()
	defer r.mu.Unlock()

	if report.ReportID == "" {
		report.ReportID = fmt.Sprintf("REP-%d", time.Now().UnixMilli()%1000000)
	}
	if report.CreatedAt.IsZero() {
		report.CreatedAt = time.Now().UTC()
	}

	r.memReports = append([]*ReportDocument{report}, r.memReports...)

	if !r.isOnline || r.reports == nil {
		return nil
	}

	_, err := r.reports.InsertOne(ctx, report)
	return err
}

func (r *Repository) ListReports(ctx context.Context, limit int64) ([]*ReportDocument, error) {
	r.mu.RLock()
	defer r.mu.RUnlock()

	if !r.isOnline || r.reports == nil {
		if limit <= 0 || limit > int64(len(r.memReports)) {
			limit = int64(len(r.memReports))
		}
		return r.memReports[:limit], nil
	}

	findOpts := options.Find().SetSort(bson.D{{Key: "created_at", Value: -1}}).SetLimit(limit)
	cursor, err := r.reports.Find(ctx, bson.M{}, findOpts)
	if err != nil {
		return r.memReports[:min(limit, int64(len(r.memReports)))], nil
	}
	defer cursor.Close(ctx)

	var reports []*ReportDocument
	if err := cursor.All(ctx, &reports); err != nil {
		return r.memReports[:min(limit, int64(len(r.memReports)))], nil
	}

	if len(reports) == 0 {
		return r.memReports[:min(limit, int64(len(r.memReports)))], nil
	}

	return reports, nil
}

func (r *Repository) GetDashboardSummary(ctx context.Context) (*DashboardSummary, error) {
	r.mu.RLock()
	defer r.mu.RUnlock()

	reports, _ := r.ListReports(ctx, 500)

	total := int64(len(reports))
	var sifCount int64 = 0
	var highRiskCount int64 = 0

	for _, rep := range reports {
		if rep.SIFProbability >= 0.5 || rep.Flagged {
			sifCount++
		}
		if rep.RiskBand == "HIGH" {
			highRiskCount++
		}
	}

	percentage := 0.0
	if total > 0 {
		percentage = float64(sifCount) / float64(total) * 100.0
	}

	return &DashboardSummary{
		TotalReports:        total,
		SIFPotentialReports: sifCount,
		HighRiskReports:     highRiskCount,
		SIFPercentage:       percentage,
	}, nil
}

func min(a, b int64) int64 {
	if a < b {
		return a
	}
	return b
}

func seedDefaultReports() []*ReportDocument {
	now := time.Now().UTC()
	return []*ReportDocument{
		{
			ReportID:       "REP-10293",
			UserID:         "usr_system",
			Source:         "text",
			RawText:        "During maintenance of compressor C-204, isolation was not verified before opening pressurised line. Residual pressure observed.",
			CreatedAt:      now.Add(-2 * time.Hour),
			SIFProbability: 0.91,
			RiskBand:       "HIGH",
			Flagged:        true,
			Guidance:       "Critical SIF potential. Immediate work halt recommended until energy isolation verified by supervisor.",
			Model:          "deberta-v3-small-sif",
			Site:           "Digboi Facility A",
			Activity:       "Compressor Maintenance",
		},
		{
			ReportID:       "REP-10381",
			UserID:         "usr_system",
			Source:         "text",
			RawText:        "Worker entered confined space at Tank T-12 without completing atmospheric gas test procedure. No injury occurred.",
			CreatedAt:      now.Add(-5 * time.Hour),
			SIFProbability: 0.74,
			RiskBand:       "ELEVATED",
			Flagged:        true,
			Guidance:       "Elevated risk: Confined space entry without atmospheric gas test. Re-brief permit-to-work requirements.",
			Model:          "deberta-v3-small-sif",
			Site:           "Dulianjan Tank Farm",
			Activity:       "Tank Cleaning",
		},
		{
			ReportID:       "REP-10422",
			UserID:         "usr_system",
			Source:         "text",
			RawText:        "Crane slewing during lifting operation — banksman lost visual contact for 3 minutes. Load was 4.2 tonnes.",
			CreatedAt:      now.Add(-24 * time.Hour),
			SIFProbability: 0.68,
			RiskBand:       "ELEVATED",
			Flagged:        true,
			Guidance:       "Elevated risk: Line-of-sight communication loss during heavy crane lift.",
			Model:          "deberta-v3-small-sif",
			Site:           "Moran Drilling Rig 4",
			Activity:       "Lifting Operations",
		},
		{
			ReportID:       "REP-10519",
			UserID:         "usr_system",
			Source:         "text",
			RawText:        "Worker not wearing fall arrest harness while working at height of 6m on C-204 scaffold structure.",
			CreatedAt:      now.Add(-48 * time.Hour),
			SIFProbability: 0.87,
			RiskBand:       "HIGH",
			Flagged:        true,
			Guidance:       "High SIF potential: Fall from height without fall protection system.",
			Model:          "deberta-v3-small-sif",
			Site:           "Digboi Facility A",
			Activity:       "Scaffold Maintenance",
		},
		{
			ReportID:       "REP-10602",
			UserID:         "usr_system",
			Source:         "text",
			RawText:        "Minor oil spill during pump P-204 seal maintenance. Spill contained within secondary bund wall.",
			CreatedAt:      now.Add(-72 * time.Hour),
			SIFProbability: 0.18,
			RiskBand:       "LOW",
			Flagged:        false,
			Guidance:       "Low SIF potential: Contained environmental observation. Standard housekeeping applies.",
			Model:          "deberta-v3-small-sif",
			Site:           "Dulianjan Pump Station",
			Activity:       "Pump Maintenance",
		},
	}
}
