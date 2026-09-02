import sys
import time
import statistics
import httpx

BASE_URL = "http://127.0.0.1:8000"
NORMAL_TEXT = "I just got promoted at work, dude!"


def run_turn(client: httpx.Client, call_id: str, text: str):
    """Run one turn, streaming SSE, and return timing dict (ms) or error string."""
    payload = {"text": text, "call_id": call_id}
    result = {
        "t_emotion": None,
        "t_first_audio": None,
        "t_done": None,
        "chunks": 0,
        "error": None,
    }

    t_start = time.monotonic()
    try:
        with client.stream("POST", f"{BASE_URL}/api/turn", json=payload) as resp:
            resp.raise_for_status()
            current_event = None
            for line in resp.iter_lines():
                if line is None:
                    continue
                line = line.strip()
                if not line:
                    current_event = None
                    continue
                if line.startswith("event:"):
                    current_event = line[len("event:"):].strip()
                    now = time.monotonic()
                    elapsed_ms = (now - t_start) * 1000
                    if current_event == "emotion" and result["t_emotion"] is None:
                        result["t_emotion"] = elapsed_ms
                    elif current_event == "audio":
                        if result["t_first_audio"] is None:
                            result["t_first_audio"] = elapsed_ms
                        result["chunks"] += 1
                    elif current_event == "done" and result["t_done"] is None:
                        result["t_done"] = elapsed_ms
                elif line.startswith("data:"):
                    # data lines belong to current_event; nothing extra to record
                    pass
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"

    return result


def fmt_ms(v):
    return f"{v:.0f}" if v is not None else "N/A"


def mark(v):
    if v is None:
        return "❌"
    return "✅" if v <= 1500 else "❌"


def main():
    n = 5
    if len(sys.argv) > 1:
        try:
            n = int(sys.argv[1])
        except ValueError:
            print(f"Invalid N argument: {sys.argv[1]!r}, using default 5")
            n = 5

    rows = []  # (turn_num, kind, result)

    with httpx.Client(timeout=60) as client:
        for i in range(1, n + 1):
            call_id = f"lat-{i}"

            greeting_result = run_turn(client, call_id, "")
            rows.append((i, "greeting", greeting_result))
            if greeting_result["error"]:
                print(f"Turn {i} (greeting) ERROR: {greeting_result['error']}")

            time.sleep(0.5)

            normal_result = run_turn(client, call_id, NORMAL_TEXT)
            rows.append((i, "normal", normal_result))
            if normal_result["error"]:
                print(f"Turn {i} (normal) ERROR: {normal_result['error']}")

            time.sleep(0.5)

    # Print table
    header = f"{'#':<3} {'kind':<9} {'emotion_ms':>11} {'first_audio_ms':>16} {'done_ms':>9} {'chunks':>7}"
    print()
    print(header)
    print("-" * len(header))
    for i, kind, r in rows:
        fa = r["t_first_audio"]
        fa_str = f"{fmt_ms(fa)} {mark(fa)}" if not r["error"] else "ERROR"
        print(
            f"{i:<3} {kind:<9} {fmt_ms(r['t_emotion']):>11} {fa_str:>16} "
            f"{fmt_ms(r['t_done']):>9} {r['chunks']:>7}"
        )

    # Summary
    greet_fa = [r["t_first_audio"] for _, k, r in rows if k == "greeting" and r["t_first_audio"] is not None]
    normal_fa = [r["t_first_audio"] for _, k, r in rows if k == "normal" and r["t_first_audio"] is not None]
    all_fa = greet_fa + normal_fa

    print()
    print("Summary (first_audio_ms):")
    if greet_fa:
        print(f"  greeting: median={statistics.median(greet_fa):.0f}  max={max(greet_fa):.0f}  (n={len(greet_fa)})")
    else:
        print("  greeting: no successful samples")
    if normal_fa:
        print(f"  normal:   median={statistics.median(normal_fa):.0f}  max={max(normal_fa):.0f}  (n={len(normal_fa)})")
    else:
        print("  normal:   no successful samples")
    if all_fa:
        print(f"  overall:  median={statistics.median(all_fa):.0f}")
    else:
        print("  overall:  no successful samples")


if __name__ == "__main__":
    main()
