import json
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from .prompts import GREETING_MESSAGE
from .llm_client import llm_client
from .tts_service import tts_service

router = APIRouter()

@router.websocket("/ws/call")
async def websocket_call_endpoint(websocket: WebSocket):
    await websocket.accept()
    print(">>> New WebSocket client connected to /ws/call")
    conversation_history = []
    active_generation_task = None

    async def send_json(data: dict):
        try:
            await websocket.send_text(json.dumps(data))
        except Exception as e:
            print(f"Error sending WS message: {e}")

    async def speak_response(text: str):
        nonlocal active_generation_task
        try:
            print(f">>> Tutor responding: {text}")
            await send_json({"type": "status", "state": "speaking"})
            await send_json({"type": "transcript", "speaker": "tutor", "text": text})
            
            # Generate Audio via Edge TTS
            audio_b64 = await tts_service.text_to_base64_audio(text)
            await send_json({
                "type": "audio_packet",
                "format": "mp3",
                "audio_base64": audio_b64,
                "text": text
            })
        except asyncio.CancelledError:
            print(">>> Speech generation cancelled due to barge-in.")
        except Exception as e:
            print(f">>> Error generating speech: {e}")
            await send_json({"type": "status", "state": "listening"})

    try:
        while True:
            raw_message = await websocket.receive_text()
            message = json.loads(raw_message)
            msg_type = message.get("type")
            print(f">>> Received WS message: {msg_type}")

            if msg_type == "start_call":
                conversation_history.clear()
                conversation_history.append({"role": "assistant", "content": GREETING_MESSAGE})
                active_generation_task = asyncio.create_task(speak_response(GREETING_MESSAGE))

            elif msg_type == "user_speech":
                user_text = message.get("text", "").strip()
                if not user_text:
                    continue

                print(f">>> User said: {user_text}")

                # Cancel active speech if any (barge-in)
                if active_generation_task and not active_generation_task.done():
                    active_generation_task.cancel()

                conversation_history.append({"role": "user", "content": user_text})
                await send_json({"type": "status", "state": "thinking"})
                await send_json({"type": "transcript", "speaker": "user", "text": user_text})

                async def handle_ai_turn():
                    reply = await llm_client.get_response(conversation_history)
                    conversation_history.append({"role": "assistant", "content": reply})
                    await speak_response(reply)

                active_generation_task = asyncio.create_task(handle_ai_turn())

            elif msg_type == "user_interrupted":
                print(">>> User interrupted (barge-in)")
                if active_generation_task and not active_generation_task.done():
                    active_generation_task.cancel()
                await send_json({"type": "interrupted"})
                await send_json({"type": "status", "state": "listening"})

            elif msg_type == "stop_call":
                print(">>> Stop call received")
                if active_generation_task and not active_generation_task.done():
                    active_generation_task.cancel()
                conversation_history.clear()
                await send_json({"type": "call_ended"})
                break

    except WebSocketDisconnect:
        print(">>> WebSocket client disconnected.")
    except Exception as e:
        print(f">>> WebSocket error: {e}")
    finally:
        if active_generation_task and not active_generation_task.done():
            active_generation_task.cancel()