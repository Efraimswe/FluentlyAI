import edge_tts
import base64
import asyncio
from .config import TTS_VOICE

class TTSService:
    def __init__(self, voice: str = TTS_VOICE):
        self.voice = voice

    async def text_to_base64_audio(self, text: str) -> str:
        """Convert text into base64 encoded MP3 audio."""
        communicate = edge_tts.Communicate(text, self.voice, rate="+5%")
        audio_chunks = []
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_chunks.append(chunk["data"])
        
        full_audio = b"".join(audio_chunks)
        return base64.b64encode(full_audio).decode("utf-8")

tts_service = TTSService()