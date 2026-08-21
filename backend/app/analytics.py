import json
import re
import os
import httpx
from typing import List, Dict, Any
from .config import OPENROUTER_API_KEY, MODELS, DEFAULT_MODEL

ANALYSIS_SYSTEM_PROMPT = """You are an expert English language coach analyzing a live conversation between an American tutor (Alex) and a student.

YOUR TASK:
Analyze the student's spoken utterances in the conversation and return a strictly valid JSON object with the following schema:

{
  "fluency_score": <integer from 50 to 98>,
  "summary": "<1-2 encouraging sentences in Russian evaluating the student's performance and confidence>",
  "corrections": [
    {
      "original": "<exact phrase or sentence said by student with mistake>",
      "improved": "<natural, native English alternative>",
      "explanation": "<short 1-sentence explanation of the grammar/vocabulary rule in Russian>"
    }
  ],
  "vocabulary": [
    {
      "word": "<useful English word or idiom from the conversation>",
      "translation": "<Russian translation>",
      "example": "<short natural example sentence>"
    }
  ]
}

RULES:
- If the student made no obvious mistakes, provide 1-2 ways they could make their phrasing sound even more advanced/idiomatic.
- Limit corrections to maximum 3 most impactful items.
- Provide 3-4 useful vocabulary items relevant to the topic discussed.
- Return ONLY the raw JSON object. Do NOT wrap in markdown codeblocks if possible, and do not include any preamble or commentary.
"""

def extract_clean_json(text: str) -> Dict[str, Any]:
    text = text.strip()
    # Remove markdown code block fences if present
    text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*```$', '', text)
    
    # Try direct parse
    try:
        return json.loads(text)
    except Exception:
        pass

    # Try finding first { and last }
    match = re.search(r'(\{.*\})', text, flags=re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass

    return None

async def generate_call_analysis(
    transcripts: List[Dict[str, Any]],
    scenario_id: str,
    duration_seconds: int
) -> Dict[str, Any]:
    # Calculate basic talk-time metrics
    user_turns = [t for t in transcripts if t.get("speaker") == "user"]
    tutor_turns = [t for t in transcripts if t.get("speaker") == "tutor"]
    total_turns = len(user_turns) + len(tutor_turns)
    
    talk_time_pct = round((len(user_turns) / max(1, total_turns)) * 100) if total_turns > 0 else 50
    user_phrases_count = len(user_turns)

    # Fallback if conversation is too short (< 1 user message)
    if not user_turns:
        return {
            "fluency_score": 75,
            "summary": "Короткий звонок! В следующий раз скажите пару фраз, чтобы получить детальный разбор.",
            "talk_time_percentage": talk_time_pct,
            "user_phrases_count": user_phrases_count,
            "duration_seconds": duration_seconds,
            "corrections": [],
            "vocabulary": [
                {
                    "word": "small talk",
                    "translation": "непринужденная светская беседа",
                    "example": "Let's make some small talk before the meeting starts."
                }
            ]
        }

    # Format transcript for LLM
    formatted_chat = "\n".join([
        f"{t.get('speaker', 'user').capitalize()}: {t.get('text', '')}"
        for t in transcripts
    ])

    user_prompt = f"Scenario: {scenario_id}\nConversation Transcript:\n{formatted_chat}\n\nProvide the JSON analysis."

    api_key = os.getenv("OPENROUTER_API_KEY", OPENROUTER_API_KEY)
    models = [os.getenv("DEFAULT_MODEL", DEFAULT_MODEL)] + [m for m in MODELS if m != DEFAULT_MODEL]

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://fluently.ai",
        "X-Title": "FluentlyAI Analytics"
    }

    for model in models:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 800
        }
        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                resp = await client.post("https://openrouter.ai/api/v1/chat/completions", json=payload, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    parsed = extract_clean_json(content)
                    if parsed:
                        parsed["talk_time_percentage"] = talk_time_pct
                        parsed["user_phrases_count"] = user_phrases_count
                        parsed["duration_seconds"] = duration_seconds
                        return parsed
        except Exception as e:
            print(f">>> [Analytics with {model}] Error: {e}")
            continue

    # Fallback if API fails
    return {
        "fluency_score": 80,
        "summary": "Отличная попытка! Вы уверенно поддерживали диалог и отвечали на вопросы репетитора.",
        "talk_time_percentage": talk_time_pct,
        "user_phrases_count": user_phrases_count,
        "duration_seconds": duration_seconds,
        "corrections": [],
        "vocabulary": [
            {
                "word": "fluency",
                "translation": "беглость речи",
                "example": "Daily speaking practice improves your fluency quickly."
            }
        ]
    }
