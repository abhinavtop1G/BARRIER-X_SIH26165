package config

import (
	"os"
	"strings"
)

type Config struct {
	Port            string
	MLServiceURL    string
	AgentServiceURL string
	JWTSecret       string
	MongoDBURI      string
	MongoDBDatabase string
	GoogleClientID  string
}

func loadDotEnv(paths ...string) {
	for _, path := range paths {
		data, err := os.ReadFile(path)
		if err != nil {
			continue
		}
		content := strings.ReplaceAll(string(data), "\r\n", "\n")
		content = strings.ReplaceAll(content, "\r", "\n")
		lines := strings.Split(content, "\n")
		for _, line := range lines {
			line = strings.TrimSpace(line)
			if line == "" || strings.HasPrefix(line, "#") {
				continue
			}
			parts := strings.SplitN(line, "=", 2)
			if len(parts) == 2 {
				k := strings.TrimSpace(parts[0])
				v := strings.TrimSpace(parts[1])
				v = strings.Trim(v, `"'`)
				if os.Getenv(k) == "" && v != "" {
					os.Setenv(k, v)
				}
			}
		}
	}
}

func Load() *Config {
	loadDotEnv(".env", "../.env", "../../.env")

	port := os.Getenv("PORT")
	if port == "" {
		port = os.Getenv("GATEWAY_PORT")
	}
	if port == "" {
		port = "9000"
	}

	mlURL := os.Getenv("ML_SERVICE_URL")
	if mlURL == "" {
		mlURL = "http://localhost:8000"
	}

	agentURL := os.Getenv("AGENT_SERVICE_URL")
	if agentURL == "" {
		agentURL = "http://localhost:8001"
	}

	jwtSecret := os.Getenv("JWT_SECRET")

	mongoURI := os.Getenv("MONGODB_URI")
	if mongoURI == "" {
		mongoURI = "mongodb://localhost:27017"
	}

	mongoDB := os.Getenv("MONGODB_DATABASE")
	if mongoDB == "" {
		mongoDB = "barrierx"
	}

	googleClientID := os.Getenv("GOOGLE_CLIENT_ID")

	return &Config{
		Port:            port,
		MLServiceURL:    mlURL,
		AgentServiceURL: agentURL,
		JWTSecret:       jwtSecret,
		MongoDBURI:      mongoURI,
		MongoDBDatabase: mongoDB,
		GoogleClientID:  googleClientID,
	}
}
