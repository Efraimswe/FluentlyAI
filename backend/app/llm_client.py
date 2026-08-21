import json
import re
import httpx
from typing import List, Dict
from .config import OPENROUTER_API_KEY, MODELS
from .prompts import SYSTEM_PROMPT

def clean_speech_text(text: str) -> str:
    """Aggressively strip any meta-talk, thinking tags, or preamble."""
    if not text:
        return ""
    
    # 1. Strip <think> tags
    text = re.sub(r'<(think|thought|reasoning)>.*?</\1>', '', text, flags=re.DOTALL)
    
    # 2. Strip thinking process text blocks
    if re.search(r'thinking process|analyze user|identify context', text, re.IGNORECASE):
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        clean_lines = [
            l for l in lines
            if not re.search(r'^(okay,? the user|let me check|rule \d|thinking|analyze|identify|\d+\.|\*|-|#)', l, re.IGNORECASE)
            and len(l) > 3
        ]
        if clean_lines:
            text = " ".join(clean_lines)

    # 3. Strip preambles like "I need to answer...", "I should say...", "As Alex...", "Response:"
    for _ in range(4):
        text = re.sub(
            r'^(I need to|I should|As an AI|As Alex|Let me|Okay,? let me|My response is|The user is asking|Here is my reply|Response:|Alex:).*?[:\.\n]\s*',
            '',
            text,
            flags=re.IGNORECASE
        ).strip()

    # 4. Strip markdown symbols and emojis
    text = text.replace("*", "").replace("#", "").replace("`", "").replace("😊", "").replace("👋", "").replace("🌟", "").strip()
    
    # 5. Strip surrounding quotes
    if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        text = text[1:-1].strip()
        
    return text.strip()

class LLMClient:
    def __init__(self):
        self.api_key = OPENROUTER_API_KEY
        self.url = "https://openrouter.ai/api/v1/chat/completions"
        self.models = MODELS

    async def get_response(self, conversation_history: List[Dict[str, str]]) -> str:
        # Keep sliding context of last 6 messages to keep context ultra-fresh and fast
        recent_history = conversation_history[-6:]
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + recent_history

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://fluently.ai",
            "X-Title": "FluentlyAI Tutor"
        }

        for model in self.models:
            payload = {
                "model": model,
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 250
            }
            try:
                async with httpx.AsyncClient(timeout=9.0) as client:
                    resp = await client.post(self.url, json=payload, headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        raw_reply = data["choices"][0]["message"]["content"]
                        if raw_reply:
                            clean_reply = clean_speech_text(raw_reply)
                            if clean_reply and len(clean_reply) > 2:
                                print(f">>> [Model: {model}] Spoke: {clean_reply}")
                                return clean_reply
                    elif resp.status_code == 429:
                        print(f">>> [Model: {model}] Rate limit (429), trying next...")
                        continue
                    else:
                        print(f">>> [Model: {model}] Status: {resp.status_code}")
                        continue
            except Exception as e:
                print(f">>> [Model: {model}] Error: {e}")
                continue

        return "That sounds really interesting! Could you tell me more about that?"

llm_client = LLMClient()