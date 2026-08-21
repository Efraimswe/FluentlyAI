from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from .websocket_router import router as websocket_router
from .analytics import generate_call_analysis
from .config import HOST, PORT

app = FastAPI(title="FluentlyAI API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(websocket_router)

class TranscriptItemModel(BaseModel):
    speaker: str
    text: str
    timestamp: Optional[Any] = None

class AnalyzeCallRequest(BaseModel):
    scenario_id: str = "casual"
    transcripts: List[TranscriptItemModel]
    duration_seconds: int = 0

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "FluentlyAI Backend", "version": "2.0.0"}

@app.post("/api/analyze-call")
async def analyze_call_endpoint(req: AnalyzeCallRequest):
    transcripts_dicts = [t.model_dump() for t in req.transcripts]
    analysis = await generate_call_analysis(
        transcripts=transcripts_dicts,
        scenario_id=req.scenario_id,
        duration_seconds=req.duration_seconds
    )
    return analysis

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=True)
