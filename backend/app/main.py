from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .websocket_router import router as websocket_router
from .config import HOST, PORT

app = FastAPI(title="FluentlyAI MVP API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(websocket_router)

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "FluentlyAI Backend"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=True)