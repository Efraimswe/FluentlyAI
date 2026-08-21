import os
from typing import List
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

MODELS: List[str] = [
    "openrouter/free",
    "openai/gpt-oss-20b:free",
    "liquid/lfm-2.5-2.6b:free",
    "google/gemma-4-26b-a4b-it:free",
    "google/gemma-4-31b-it:free"
]

DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", MODELS[0])
TTS_VOICE = os.getenv("TTS_VOICE", "en-US-JennyNeural")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
