// Live Deepgram streaming test — no browser required.
//
// Run with:
//   node scripts/test_deepgram.mjs

const PCM_PATH =
  "/tmp/claude-1000/-home-skaylet/c613694d-ff1d-46c9-9903-297bd60b46e4/scratchpad/speech16k.pcm";
const API_BASE = "http://127.0.0.1:8000";
const CHUNK_BYTES = 3200;
const CHUNK_INTERVAL_MS = 100;

const DEEPGRAM_WS_URL =
  "wss://api.deepgram.com/v1/listen?model=nova-3&encoding=linear16&sample_rate=16000&channels=1&interim_results=true&smart_format=true&punctuate=true&language=en&endpointing=false";

async function main() {
  const startRes = await fetch(`${API_BASE}/api/call/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });

  if (startRes.status === 502) {
    const body = await startRes.json().catch(() => ({}));
    if (body.detail === "deepgram_grant_forbidden") {
      console.log("SKIP: key lacks Member permissions");
      process.exit(0);
    }
  }

  if (!startRes.ok) {
    console.error(`call/start failed: HTTP ${startRes.status}`);
    process.exit(1);
  }

  const { deepgram_token: token, deepgram_auth } = await startRes.json();
  const auth = deepgram_auth ?? "bearer";

  const fs = await import("node:fs");
  const pcm = fs.readFileSync(PCM_PATH);

  const ws = new WebSocket(DEEPGRAM_WS_URL, [auth, token]);
  ws.binaryType = "arraybuffer";

  let gotNonEmptyFinal = false;

  const closed = new Promise((resolve) => {
    ws.addEventListener("close", (ev) => {
      console.log(`close: code=${ev.code} reason=${ev.reason || "(none)"}`);
      if (ev.code === 401 || ev.code === 403 || !ev.wasClean) {
        console.error(`handshake/auth error, URL (no token): ${DEEPGRAM_WS_URL}`);
      }
      resolve();
    });
  });

  ws.addEventListener("error", (ev) => {
    console.error("ws error:", ev.message ?? ev);
  });

  ws.addEventListener("message", (ev) => {
    let msg;
    try {
      msg = JSON.parse(ev.data);
    } catch {
      return;
    }
    if (msg.type === "Metadata") {
      console.log("Metadata received");
      return;
    }
    if (msg.type !== "Results") return;

    const t = msg.channel?.alternatives?.[0]?.transcript ?? "";
    if (!t) return;

    if (msg.is_final) {
      console.log(`FINAL: ${t} (from_finalize=${msg.from_finalize === true})`);
      gotNonEmptyFinal = true;
    } else {
      console.log(`interim: ${t}`);
    }
  });

  try {
    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("connect timeout")), 10000);
      ws.addEventListener("open", () => {
        clearTimeout(timer);
        resolve();
      });
      ws.addEventListener("error", () => {
        clearTimeout(timer);
        reject(new Error("connect error"));
      });
      ws.addEventListener("close", (ev) => {
        clearTimeout(timer);
        reject(new Error(`closed before open: code=${ev.code} reason=${ev.reason || "(none)"}`));
      });
    });
  } catch (err) {
    console.error(err.message);
    console.error(`URL (no token): ${DEEPGRAM_WS_URL}`);
    process.exit(1);
  }

  console.log("connected, streaming audio...");

  for (let offset = 0; offset < pcm.length; offset += CHUNK_BYTES) {
    const chunk = pcm.subarray(offset, offset + CHUNK_BYTES);
    ws.send(chunk);
    await new Promise((r) => setTimeout(r, CHUNK_INTERVAL_MS));
  }

  console.log("finished streaming, sending Finalize...");
  ws.send(JSON.stringify({ type: "Finalize" }));
  await new Promise((r) => setTimeout(r, 1000));

  console.log("sending CloseStream...");
  ws.send(JSON.stringify({ type: "CloseStream" }));

  await closed;

  if (gotNonEmptyFinal) {
    process.exit(0);
  } else {
    console.error("no non-empty final transcript received");
    process.exit(1);
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
