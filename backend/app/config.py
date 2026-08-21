import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

MODELS = [
    "nvidia/nemotron-3-nano-30b-a3b:free",
    "nvidia/nemotron-nano-9b-v2:free",
    "cohere/north-mini-code:free"
]

DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", MODELS[0])
TTS_VOICE = os.getenv("TTS_VOICE", "en-US-JennyNeural")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
