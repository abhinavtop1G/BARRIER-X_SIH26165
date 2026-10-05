from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from app.agent import function_process_query
from app.config import settings
from app import tools

app = FastAPI(
    title="BARRIER X AI HSE Agent Service",
    description="RAG-powered AI HSE Safety Agent for Oil India Limited",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AgentChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = "default"
    uploaded_reports: Optional[List[Dict[str, Any]]] = None

class AgentChatResponse(BaseModel):
    answer: str
    evidence: List[Dict[str, Any]]
    tools_used: List[str]
    conversation_id: str

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "agent-service",
        "llm_configured": bool(settings.OPENAI_API_KEY or settings.GROQ_API_KEY or settings.GEMINI_API_KEY)
    }

@app.post("/agent/upload-dataset")
async def upload_dataset(data: Dict[str, Any]):
    conv_id = data.get("conversation_id", "default")
    reports = data.get("reports", [])
    if reports:
        tools.add_uploaded_reports(reports, conv_id)
    return {"status": "ok", "ingested": len(reports), "conversation_id": conv_id}

@app.post("/agent/chat", response_model=AgentChatResponse)
async def chat(req: AgentChatRequest):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    
    if req.uploaded_reports:
        tools.add_uploaded_reports(req.uploaded_reports, req.conversation_id or "default")
    
    result = await function_process_query(req.message, req.conversation_id or "default", req.uploaded_reports)
    return AgentChatResponse(**result)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.PORT, reload=True)

