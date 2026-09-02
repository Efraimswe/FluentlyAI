from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import HOST, PORT
from .turn import router as turn_router
from .deepgram_token import router as deepgram_router

app = FastAPI(title="FluentlyAI API", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(turn_router)
app.include_router(deepgram_router)

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "FluentlyAI Backend", "version": "3.0.0"}

@app.get("/api/warmup")
async def warmup():
    return {"ok": True}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=True)
