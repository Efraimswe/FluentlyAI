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
    text = re.sub(r'\([^\)]*(?:waits?|pause|smile|laugh|nod|speaks?|reply|ends with)[^\)]*\)', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[[^\]]*(?:waits?|pause|smile|laugh|nod|speaks?|reply)[^\]]*\]', '', text, flags=re.IGNORECASE)

    # 3. If the entire text is wrapped in quotes, strip them first so nested quotes don't invert
    text = text.strip().strip('"\'“”')

    # 4. If there is an explicit "Alex:", "Response:", "Final Answer:", "Reply:", "I'll ask:", take what follows the LAST one!
    marker_matches = list(re.finditer(r'(?:final answer|response|reply|alex|spoken output|i\'ll ask|i will ask|i can say|so i\'ll output):\s*', text, flags=re.IGNORECASE))
    if marker_matches:
        last_match = marker_matches[-1]
        text = text[last_match.end():].strip()

    # 5. Check if text contains teacher/methodology meta analysis
    meta_keywords = [
        "the student", "the user", "this seems like", "they might be", 
        "i should take the lead", "since they're unsure", "we need to", 
        "the tutor should", "thinking process", "thought process", 
        "analysis", "must not break", "permission to start", "initiate the conversation"
    ]
    if any(k in text.lower() for k in meta_keywords):
        # Look for dialogue sentences in quotes that do NOT contain meta keywords
        all_quotes = re.findall(r'["“]([^"”]{6,350})["”]', text)
        clean_quotes = [q for q in all_quotes if not any(k in q.lower() for k in meta_keywords)]
        if clean_quotes:
            text = clean_quotes[-1].strip()
        else:
            # If no clean quotes exist, strip all sentences containing meta keywords
            sentences = re.split(r'(?<=[.!?])\s+', text)
            clean_sentences = [s for s in sentences if not any(k in s.lower() for k in meta_keywords) and len(s.strip()) > 5]
            if clean_sentences:
                text = " ".join(clean_sentences).strip()
            else:
                text = "No worries at all! How about you tell me about what you like to do on weekends, or your favorite hobbies?"

    # 6. Strip preambles
    for _ in range(4):
        text = re.sub(
            r'^(?:I need to|I should|As an AI|As Alex|Let me|Okay,? let me|My response is|The user is asking|Here is my reply|Alex:)\s*[:\.\n\-]?\s*',
            '',
            text,
            flags=re.IGNORECASE
        ).strip()

    # 7. Strip trailing meta-commentary
    text = re.sub(r"(?:That's \d|Now I will|This is a friendly|My response should|So I'll output|Must not break|Actually let's|Since they're unsure).*", '', text, flags=re.DOTALL | re.IGNORECASE).strip()

    # 8. Strip markdown and emojis
    text = re.sub(r'[\*#`_~]', '', text)
    text = re.sub(r'[\U00010000-\U0010ffff]', '', text)

    # 9. Strip bullet point lists
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    spoken_lines = [l for l in lines if not l.startswith(('-', '*', '•', '1.', '2.', '3.', '4.'))]
    if spoken_lines:
        text = ' '.join(spoken_lines)

    # 10. Final strip surrounding quotes
    text = text.strip().strip('"\'“”')

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
                "temperature": 0.85,
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
