import os
from pathlib import Path

env_paths = [Path(".env"), Path("../.env"), Path("../../.env")]
for p in env_paths:
    if p.exists():
        try:
            with open(p, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k, v = k.strip(), v.strip().strip("\"'")
                        if k not in os.environ and v:
                            os.environ[k] = v
        except Exception:
            pass

class Settings:
    PORT: int = int(os.getenv("PORT", "8001"))
    MONGODB_URI: str = os.getenv("MONGODB_URI", "")
    MONGODB_DATABASE: str = os.getenv("MONGODB_DATABASE", "barrierx")
    
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    
    ML_SERVICE_URL: str = os.getenv("ML_SERVICE_URL", "http://localhost:8000")

settings = Settings()

