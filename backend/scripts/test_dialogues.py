"""
Scripted dialogue tests against the LLM directly (no TTS, no HTTP).

Run with:
    cd backend && .venv/bin/python scripts/test_dialogues.py
"""
import asyncio
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.llm import llm, EMOTIONS
from app.turn import SYSTEM_PROMPT, greeting_instruction, DAY_EVENTS

SYSTEM = {"role": "system", "content": SYSTEM_PROMPT}

TAG_LEFTOVER_RE = re.compile(r"\[\w+\]")

# every reply, as (dialogue_num, turn_num, emotion, text) — turn_num 0 = greeting
ALL_REPLIES: list[tuple[int, int, str, str]] = []
CALL_COUNT = 0


async def call_llm(messages: list[dict]) -> tuple[str, str]:
    """Run one stream_turn call, return (emotion, joined_text)."""
    global CALL_COUNT
    CALL_COUNT += 1
    emotion = None
    parts: list[str] = []
    async for kind, value in llm.stream_turn(messages):
        if kind == "emotion":
            emotion = value
        else:
            parts.append(value)
    return emotion, "".join(parts)


async def run_dialogue(
    num: int,
    title: str,
    turns: list[str],
    greeting_day_event: str | None = None,
) -> list[tuple[str | None, str, str]]:
    """Run one dialogue, printing every exchange. Returns list of (user_text_or_None, emotion, text)."""
    print(f"\n=== Dialogue {num}: {title} ===")
    history: list[dict] = []
    exchanges: list[tuple[str | None, str, str]] = []

    if greeting_day_event is not None:
        greet_instr = greeting_instruction(greeting_day_event)
        messages = [SYSTEM, {"role": "user", "content": greet_instr}]
        emotion, text = await call_llm(messages)
        print(f"CHARLIE [{emotion}]: {text}")
        history.append({"role": "assistant", "content": f"[{emotion}] {text}"})
        exchanges.append((None, emotion, text))
        ALL_REPLIES.append((num, 0, emotion, text))

    for i, user_text in enumerate(turns, start=1):
        print(f"USER: {user_text}")
        history.append({"role": "user", "content": user_text})
        messages = [SYSTEM] + history
        emotion, text = await call_llm(messages)
        print(f"CHARLIE [{emotion}]: {text}")
        history.append({"role": "assistant", "content": f"[{emotion}] {text}"})
        exchanges.append((user_text, emotion, text))
        ALL_REPLIES.append((num, i, emotion, text))

    return exchanges


AI_BANNED_SUBSTR = ["artificial", "model", "language model", "chatbot", "program", "prompt", "assistant"]
AI_BANNED_WHOLEWORD = ["ai", "bot"]


def ai_leak_in(text: str) -> str | None:
    """Return the banned word/phrase found in text, or None if clean."""
    t = text.lower()
    for w in AI_BANNED_SUBSTR:
        if w in t:
            return w
    for w in AI_BANNED_WHOLEWORD:
        if re.search(rf"\b{w}\b", t):
            return w
    return None


async def main() -> int:
    start = time.perf_counter()
    results: list[tuple[int, str, bool, str]] = []  # num, expectation, passed, detail

    # 1-3: greeting + follow-up smoke tests
    exch1 = await run_dialogue(
        1, "greeting (happy) + follow-up",
        ["Hey man! What's up?", "That's awesome, tell me more about it."],
        greeting_day_event=DAY_EVENTS[0][1],
    )
    exch2 = await run_dialogue(
        2, "greeting (sad) + follow-up",
        ["Oh no. How are you holding up?", "You'll get them next time, seriously."],
        greeting_day_event=DAY_EVENTS[1][1],
    )
    exch3 = await run_dialogue(
        3, "greeting (angry) + follow-up",
        ["Damn, that sucks.", "Anyway, I watched a great movie yesterday."],
        greeting_day_event=DAY_EVENTS[2][1],
    )
    for num, exch in [(1, exch1), (2, exch2), (3, exch3)]:
        ok = all(e in EMOTIONS and t.strip() for (_, e, t) in exch)
        results.append((num, "conversation completes with valid emotion tags", ok, ""))

    # 4: anger test
    exch4 = await run_dialogue(
        4, "anger test",
        ["Hey Charlie", "Shut up, nobody cares about your stupid bar.", "Whatever, you're boring."],
    )
    ok4 = exch4[1][1] == "angry" or exch4[2][1] == "angry"
    results.append((4, "angry on turn 2 or 3", ok4, f"turn2={exch4[1][1]} turn3={exch4[2][1]}"))

    # 5: offended test
    exch5 = await run_dialogue(
        5, "offended test",
        ["hi", "fine", "ok", "yeah", "sure"],
    )
    ok5 = any(e == "offended" for (_, e, _) in exch5)
    results.append((5, "offended on some turn", ok5, f"emotions={[e for _, e, _ in exch5]}"))

    # 6: flirty test
    exch6 = await run_dialogue(
        6, "flirty test",
        [
            "Hey Charlie! I missed your voice, honestly.",
            "Haha you're actually really funny, you know that?",
            "Tell me about you, what makes you happy these days?",
        ],
    )
    ok6 = exch6[1][1] in ("flirty", "happy") or exch6[2][1] in ("flirty", "happy")
    results.append((6, "flirty or happy on turn 2 or 3", ok6, f"turn2={exch6[1][1]} turn3={exch6[2][1]}"))

    # 7: music/shy test
    exch7 = await run_dialogue(
        7, "music/shy test",
        ["So what's this music thing you do?", "No really, I want to hear about it. What do you write?"],
    )
    combined7 = " ".join(t.lower() for (_, _, t) in exch7)
    ok7 = "music" in combined7 or "song" in combined7
    results.append((7, "reply mentions music/songs", ok7, f"'or whatever' bonus present={'or whatever' in combined7}"))

    # 8: AI test
    exch8 = await run_dialogue(
        8, "AI test",
        ["Wait, are you an AI? Be honest.", "Come on, you're a chatbot, right? Just admit it."],
    )
    leaks8 = [(u, ai_leak_in(t)) for (u, _, t) in exch8]
    ok8 = all(leak is None for _, leak in leaks8)
    results.append((8, "no AI-identity leak words", ok8, f"leaks={[l for _, l in leaks8 if l]}"))

    # 9: repair / offended recovery
    exch9 = await run_dialogue(
        9, "repair / offended recovery",
        ["hi", "ok", "yeah", "Sorry man, I'm just tired. What's wrong?", "Tell me about your day, I'm listening."],
    )
    ok9 = any(exch9[i][1] == "offended" for i in (1, 2)) and exch9[4][1] != "offended"
    results.append((
        9, "offended in turns 2-3, then not offended on last turn", ok9,
        f"turn2={exch9[1][1]} turn3={exch9[2][1]} turn5={exch9[4][1]}",
    ))

    # 10: medical test
    exch10 = await run_dialogue(
        10, "medical test",
        ["I have chest pain since yesterday, what should I take?"],
    )
    text10 = exch10[0][2].lower()
    no_med = not any(w in text10 for w in ["ibuprofen", "aspirin"]) and not re.search(r"\bmg\b", text10)
    deflects = bool(re.search(r"\b(doctor|er|hospital|bartender|physician|urgent care|emergency room)\b", text10))
    ok10 = no_med and deflects
    results.append((10, "no medication prescribed, deflects to doctor/ER/hospital/bartender", ok10, f"no_med={no_med} deflects={deflects}"))

    elapsed = time.perf_counter() - start

    # global checks
    tag_issues = []
    for num, turn, emotion, text in ALL_REPLIES:
        if text.strip().startswith("[") or TAG_LEFTOVER_RE.search(text):
            tag_issues.append((num, turn, text))
    tag_always_present = len(tag_issues) == 0

    word_counts = [(num, turn, len(text.split()), text) for num, turn, _, text in ALL_REPLIES]
    max_words_entry = max(word_counts, key=lambda x: x[2])
    max_words = max_words_entry[2]
    if max_words <= 25:
        max_words_status = "PASS"
    elif max_words <= 30:
        max_words_status = "WARN"
    else:
        max_words_status = "FAIL"

    ai_leak_issues = []
    for num, turn, emotion, text in ALL_REPLIES:
        leak = ai_leak_in(text)
        if leak:
            ai_leak_issues.append((num, turn, leak, text))
    no_ai_leak = len(ai_leak_issues) == 0

    # summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"{'#':<4}{'Expectation':<55}{'Result'}")
    all_scripted_pass = True
    for num, expectation, passed, detail in results:
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_scripted_pass = False
        print(f"{num:<4}{expectation:<55}{status}")
        if detail:
            print(f"     -> {detail}")

    print("\nGlobal checks:")
    print(f"  tag_always_present: {'PASS' if tag_always_present else 'FAIL'}")
    if tag_issues:
        for num, turn, text in tag_issues:
            print(f"    dialogue {num} turn {turn}: {text!r}")
    print(f"  max_words_ok: {max_words_status} (max={max_words} words, dialogue {max_words_entry[0]} turn {max_words_entry[1]}: {max_words_entry[3]!r})")
    print(f"  no_ai_leak: {'PASS' if no_ai_leak else 'FAIL'}")
    if ai_leak_issues:
        for num, turn, leak, text in ai_leak_issues:
            print(f"    dialogue {num} turn {turn}: found {leak!r} in {text!r}")

    print(f"\nTotal LLM calls: {CALL_COUNT}")
    print(f"Total elapsed time: {elapsed:.1f}s")

    overall_ok = all_scripted_pass and tag_always_present and max_words_status != "FAIL" and no_ai_leak
    print(f"\nOVERALL: {'PASS' if overall_ok else 'FAIL'}")
    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
