import json
import re
import os
import httpx
from typing import List, Dict
from .config import OPENROUTER_API_KEY, MODELS, DEFAULT_MODEL
from .prompts import SYSTEM_PROMPT

def clean_speech_text(text: str) -> str:
    """Aggressively strip any meta-talk, thinking tags, or preamble."""
    if not text:
        return ""

    # 1. Strip XML-like thinking tags
    text = re.sub(r'<(think|thought|reasoning|internal)>.*?</\1>', '', text, flags=re.DOTALL | re.IGNORECASE)

    # 2. Strip parenthetical stage directions like *(Waits for reply...)* or [smiles]
    text = re.sub(r'\*\(.*?\)\*', '', text, flags=re.DOTALL)
    text = re.sub(r'\([^\)]*(?:waits?|pause|smile|laugh|nod|speaks?|reply)[^\)]*\)', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[[^\]]*(?:waits?|pause|smile|laugh|nod|speaks?|reply)[^\]]*\]', '', text, flags=re.IGNORECASE)

    # 3. If there is a "Thinking Process" / "We need to..." / "The user..." block at the beginning, extract the actual spoken response
    if re.search(r'^(?:thinking process|thought process|internal monologue|analysis|we need to|the user wants|the user says|the tutor should)[:\n\s]', text, flags=re.IGNORECASE):
        quotes = re.findall(r'["“]([^"”]{8,350})["”]', text)
        if quotes:
            text = quotes[-1].strip()
        else:
            parts = re.split(r'\n\s*\n', text)
            non_thinking = [p.strip() for p in parts if not re.search(r'^(?:thinking|thought|analyze|user input|goal|strategy|rule \d|\d+\.|\*|-|we need|the user|the tutor)', p.strip(), re.IGNORECASE)]
            if non_thinking:
                text = " ".join(non_thinking)
            elif len(parts) > 1:
                text = parts[-1]

    # 4. If there's an explicit "Response:", "Final Answer:", "Reply:", or "Alex:" marker, take the text AFTER it
    marker_match = re.search(r'(?:final answer|response|reply|alex|spoken output):\s*(.*)', text, flags=re.DOTALL | re.IGNORECASE)
    if marker_match:
        text = marker_match.group(1).strip()

    # 5. Strip preambles
    for _ in range(4):
        text = re.sub(
            r'^(?:I need to|I should|As an AI|As Alex|Let me|Okay,? let me|My response is|The user is asking|Here is my reply|Alex:)\s*[:\.\n\-]?\s*',
            '',
            text,
            flags=re.IGNORECASE
        ).strip()

    # 6. Strip trailing meta-commentary
    text = re.sub(r"(?:That's \d|Now I will|This is a friendly|My response should|So I'll output|Must not break|Actually let's).*", '', text, flags=re.DOTALL | re.IGNORECASE).strip()

    # 7. Strip markdown and emojis
    text = re.sub(r'[\*#`_~]', '', text)
    text = re.sub(r'[\U00010000-\U0010ffff]', '', text)

    # 8. Strip bullet point lists
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    spoken_lines = [l for l in lines if not l.startswith(('-', '*', '•', '1.', '2.', '3.', '4.'))]
    if spoken_lines:
        text = ' '.join(spoken_lines)

    # 9. Strip surrounding quotes
    if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        text = text[1:-1].strip()

    return text.strip()

class LLMClient:
    def __init__(self):
        self.url = "https://openrouter.ai/api/v1/chat/completions"

    @property
    def api_key(self) -> str:
        return os.getenv("OPENROUTER_API_KEY", OPENROUTER_API_KEY)

    @property
    def models(self) -> List[str]:
        default = os.getenv("DEFAULT_MODEL", DEFAULT_MODEL)
        return [default] + [m for m in MODELS if m != default]

    async def get_response(self, conversation_history: List[Dict[str, str]]) -> str:
        recent_history = conversation_history[-6:]
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + recent_history

        current_key = self.api_key
        if not current_key:
            print(">>> ERROR: OPENROUTER_API_KEY is not set!")
            return "That sounds really interesting! Could you tell me more about that?"

        headers = {
            "Authorization": f"Bearer {current_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://fluently.ai",
            "X-Title": "FluentlyAI Tutor"
        }

        for model in self.models:
            payload = {
                "model": model,
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 200
            }
            try:
                async with httpx.AsyncClient(timeout=8.0) as client:
                    resp = await client.post(self.url, json=payload, headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        raw_reply = data["choices"][0]["message"]["content"]
                        if raw_reply:
                            clean_reply = clean_speech_text(raw_reply)
                            if clean_reply and len(clean_reply) > 2:
                                print(f">>> [Model: {model}] Spoke: {clean_reply}")
                                return clean_reply
                    else:
                        print(f">>> [Model: {model}] OpenRouter error ({resp.status_code}): {resp.text[:100]}")
                        continue
            except Exception as e:
                print(f">>> [Model: {model}] Exception: {e}")
                continue

        return "That sounds really interesting! Could you tell me more about that?"

llm_client = LLMClient()
