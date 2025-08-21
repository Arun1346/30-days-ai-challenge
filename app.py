# app.py - Day 20: Gemini streaming -> Murf WS stream-input (prints base64 audio)

import os
import logging
import uuid
import asyncio
import json
import threading
import time
import re
from datetime import datetime

from fastapi import FastAPI, File, UploadFile, Query, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

# Schemas/services
from schemas import AgentChatResponse, ErrorResponse
from services import stt, llm, tts

# NEW: Murf WebSocket stream-input client
from services.murf_ws import MurfStreamInputWS

# Load environment variables
load_dotenv()

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- Configure AssemblyAI (turn detection) ---
try:
    import assemblyai as aai
    from assemblyai.streaming.v3 import (
        BeginEvent,
        StreamingClient,
        StreamingClientOptions,
        StreamingError,
        StreamingEvents,
        StreamingParameters,
        TerminationEvent,
        TurnEvent,
    )

    api_key = os.getenv("ASSEMBLYAI_API_KEY")
    if not api_key:
        logger.error("AssemblyAI API key not found.")
        raise ValueError("AssemblyAI API key not found.")

    aai.settings.api_key = api_key
    logger.info("✅ AssemblyAI configured successfully with Enhanced Turn Detection")
except ImportError as e:
    logger.error(f"AssemblyAI import failed: {e}")
    raise

# --- Configure Google Gemini (streaming) ---
try:
    import google.generativeai as genai
    from google.generativeai.types import HarmCategory, HarmBlockThreshold

    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if not gemini_api_key:
        logger.error("Gemini API key not found.")
        raise ValueError("Gemini API key not found.")

    genai.configure(api_key=gemini_api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')
    logger.info("✅ Google Gemini 1.5 Flash configured successfully for streaming LLM responses")
except ImportError as e:
    logger.error(f"Google Generative AI import failed: {e}")
    raise

# --- HTTP endpoints ---

@app.get("/", response_class=HTMLResponse)
def read_root():
    """Serves the main HTML page."""
    with open("templates/index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/voices")
def get_voices_endpoint():
    try:
        murf_voices = tts.get_voices()
        formatted_voices = []
        for voice in murf_voices:
            voice_name = voice.get("name") or voice.get("voiceId")
            formatted_voices.append({
                "voice_id": voice.get("voiceId"),
                "name": voice_name,
                "labels": {
                    "gender": voice.get("gender")
                }
            })
        return {"voices": formatted_voices}
    except Exception as e:
        logger.error(f"Error fetching and formatting voices: {e}")
        raise HTTPException(status_code=500, detail="Could not fetch voices.")

# --- Utility ---

def normalize_text(text: str) -> str:
    """Remove punctuation and convert to lowercase for comparison"""
    return re.sub(r'[^\w\s]', '', text.strip().lower())

def schedule_websocket_message(loop: asyncio.AbstractEventLoop, websocket: WebSocket, message: dict):
    """Thread-safe enqueue of send_text on the running loop."""
    try:
        coro = websocket.send_text(json.dumps(message))
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future
    except Exception as e:
        logger.error(f"Error scheduling WebSocket message: {e}")

# --- LLM streaming -> Murf stream-input bridge ---



def schedule_llm_streaming(loop: asyncio.AbstractEventLoop, websocket: WebSocket, user_input: str, turn_number: int):
    """Schedule LLM streaming response in a separate thread and pipe to Murf stream-input WS."""

    def stream_llm_response():
        try:
            logger.info(f"🤖 Starting LLM streaming for turn #{turn_number}: '{user_input}'")

            schedule_websocket_message(loop, websocket, {
                "type": "llm_streaming_start",
                "turn_number": turn_number,
                "message": f"🤖 AI responding to turn #{turn_number}...",
                "timestamp": datetime.now().isoformat()
            })

            # Start Gemini streaming
            response = model.generate_content(
                user_input,
                stream=True,
                safety_settings={
                    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
                }
            )

            accumulated_response = ""

            murf_api_key = os.getenv("MURF_API_KEY", "").strip()
            if not murf_api_key:
                raise ValueError("MURF_API_KEY is missing")
            voice_id = os.getenv("MURF_DEFAULT_VOICE_ID", "en-US-amara").strip()

            async def run_murf_streaming():
                nonlocal accumulated_response  # FIX: declare nonlocal before using it below

                # Murf stream-input per quickstart: 44.1k WAV MONO
                async with MurfStreamInputWS(
                    api_key=murf_api_key,
                    voice_id=voice_id,
                    sample_rate=44100,
                    channel_type="MONO",
                    audio_format="WAV",
                    style="Conversational",
                    rate=0,
                    pitch=0,
                    variation=1,
                ) as murf:
                    # Forward Gemini chunks as Murf text messages
                    for chunk in response:
                        if hasattr(chunk, "text") and chunk.text:
                            text_piece = chunk.text
                            accumulated = accumulated_response + text_piece

                            logger.info(f"🤖 LLM Chunk: '{text_piece}'")
                            schedule_websocket_message(loop, websocket, {
                                "type": "llm_chunk",
                                "turn_number": turn_number,
                                "chunk": text_piece,
                                "accumulated": accumulated,
                                "timestamp": datetime.now().isoformat()
                            })

                            # Send to Murf
                            await murf.send_text_chunk(text_piece, end=False)

                            # Update accumulator after successful send
                            accumulated_response = accumulated

                    # Signal end of text stream
                    await murf.send_text_chunk("", end=True)
                    # Wait for Murf to finish streaming audio
                    await murf.wait_for_complete(timeout=90)

            # Run the async Murf coroutine on the running loop
            murf_task = asyncio.run_coroutine_threadsafe(run_murf_streaming(), loop)

            # Wait for Murf to finish
            try:
                murf_task.result(timeout=120)
            except Exception as e:
                logger.error(f"Murf streaming task error/timeout: {e}")

            logger.info("=" * 60)
            logger.info(f"🤖 LLM RESPONSE COMPLETED for turn #{turn_number}")
            logger.info(f"📝 Full Response: '{accumulated_response}'")
            logger.info(f"📊 Response Length: {len(accumulated_response)} characters")
            logger.info("=" * 60)

            schedule_websocket_message(loop, websocket, {
                "type": "llm_streaming_complete",
                "turn_number": turn_number,
                "full_response": accumulated_response,
                "message": f"🤖 AI response complete for turn #{turn_number}",
                "timestamp": datetime.now().isoformat()
            })

        except Exception as e:
            logger.error(f"❌ LLM streaming error: {e}")
            schedule_websocket_message(loop, websocket, {
                "type": "llm_error",
                "turn_number": turn_number,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            })

    threading.Thread(target=stream_llm_response, daemon=True).start()

# --- WebSocket endpoint (AssemblyAI streaming + turn detection) ---

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("🔗 WebSocket connection established for Day 20 Streaming LLM -> Murf WS TTS.")

    session_id = str(uuid.uuid4())
    loop = asyncio.get_running_loop()
    streaming_client = None

    # Turn tracking with punctuation handling
    turn_counter = {'count': 0}
    last_turn = {'raw': '', 'timestamp': 0.0}

    try:
        streaming_client = StreamingClient(
            StreamingClientOptions(
                api_key=os.getenv("ASSEMBLYAI_API_KEY"),
                api_host="streaming.assemblyai.com"
            )
        )

        streaming_client.on(StreamingEvents.Begin,
            lambda client, event: handle_begin(event, websocket, loop))
        streaming_client.on(StreamingEvents.Turn,
            lambda client, event: handle_turn_with_llm_streaming(event, websocket, loop, turn_counter, last_turn))
        streaming_client.on(StreamingEvents.Error,
            lambda client, error: handle_error(error, websocket, loop))
        streaming_client.on(StreamingEvents.Termination,
            lambda client, event: handle_termination(event, websocket, loop))

        streaming_client.connect(
            StreamingParameters(
                sample_rate=16000,
                format_turns=True,
                end_of_turn_confidence_threshold=0.7,
                min_end_of_turn_silence_when_confident=800,
                max_turn_silence=1500,
                enable_extra_session_information=True,
                punctuation_level="high"
            )
        )

        logger.info("🚀 Connected to AssemblyAI with Enhanced Turn Detection and LLM Streaming!")
        await websocket.send_text(json.dumps({
            "type": "connection_established",
            "message": "Connected to AssemblyAI with Enhanced Turn Detection and LLM Streaming",
            "session_id": session_id,
            "timestamp": datetime.now().isoformat()
        }))

        while True:
            try:
                data = await websocket.receive_bytes()
                streaming_client.stream(data)
            except WebSocketDisconnect:
                logger.info("Client disconnected")
                break
            except Exception as e:
                logger.error(f"Error in WebSocket loop: {e}")
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": f"Streaming error: {str(e)}"
                }))
                break

    except Exception as e:
        logger.error(f"Failed to establish AssemblyAI connection: {e}")
        await websocket.send_text(json.dumps({
            "type": "error",
            "message": f"Failed to connect to speech recognition service: {str(e)}"
        }))
    finally:
        if streaming_client:
            try:
                logger.info("🧹 Cleaning up AssemblyAI connection...")
                streaming_client.disconnect(terminate=True)
                logger.info("✅ AssemblyAI connection cleaned up")
            except Exception as e:
                logger.error(f"Error during cleanup: {e}")

# --- Event handlers ---

def handle_begin(event: BeginEvent, websocket: WebSocket, loop: asyncio.AbstractEventLoop):
    logger.info(f"🚀 Enhanced Turn Detection with LLM Streaming session began: {event.id}")
    schedule_websocket_message(loop, websocket, {
        "type": "session_begin",
        "session_id": event.id,
        "message": "Turn detection with LLM streaming active - speak naturally and pause to complete turns",
        "timestamp": datetime.now().isoformat()
    })

def handle_turn_with_llm_streaming(event: TurnEvent, websocket: WebSocket, loop: asyncio.AbstractEventLoop, turn_counter: dict, last_turn: dict):
    """Handle turns with LLM streaming integration"""
    if event.transcript:
        if event.end_of_turn:
            current_time = time.time()
            current_normalized = normalize_text(event.transcript)
            last_normalized = normalize_text(last_turn['raw'])

            # If punctuation-only update of same turn within 2 seconds
            if (current_normalized == last_normalized and last_turn['raw'] and (current_time - last_turn['timestamp']) < 2.0):
                if event.transcript != last_turn['raw']:
                    logger.info(f"✏️ Updating punctuation for turn #{turn_counter['count']}: '{event.transcript}'")
                    schedule_websocket_message(loop, websocket, {
                        "type": "turn_updated",
                        "turn_number": turn_counter['count'],
                        "final_transcript": event.transcript,
                        "message": f"Turn #{turn_counter['count']} updated with punctuation",
                        "timestamp": datetime.now().isoformat(),
                        "audio_duration": getattr(event, 'duration_seconds', None)
                    })
                    last_turn['raw'] = event.transcript
                    last_turn['timestamp'] = current_time
                else:
                    logger.info(f"🔁 Skipping identical punctuation update for turn #{turn_counter['count']}")
                return

            # New turn
            turn_counter['count'] += 1
            last_turn['raw'] = event.transcript
            last_turn['timestamp'] = current_time

            logger.info("=" * 60)
            logger.info(f"🎯 TURN #{turn_counter['count']} COMPLETED!")
            logger.info(f"📝 Final Transcript: '{event.transcript}'")
            logger.info(f"⏱️ Turn Duration: {getattr(event, 'duration_seconds', 'N/A')}s")
            logger.info(f"🔇 End of Turn Detected - User stopped speaking")
            logger.info(f"🕒 Timestamp: {datetime.now().strftime('%H:%M:%S.%f')[:-3]}")
            logger.info("=" * 60)

            schedule_websocket_message(loop, websocket, {
                "type": "turn_completed",
                "turn_number": turn_counter['count'],
                "final_transcript": event.transcript,
                "end_of_turn": True,
                "message": f"Turn #{turn_counter['count']} completed - User stopped speaking",
                "timestamp": datetime.now().isoformat(),
                "audio_duration": getattr(event, 'duration_seconds', None)
            })

            # Also send final transcript for display
            schedule_websocket_message(loop, websocket, {
                "type": "final_transcript",
                "text": event.transcript,
                "turn_number": turn_counter['count']
            })

            # Trigger LLM streaming -> Murf streaming
            if event.transcript.strip():
                schedule_llm_streaming(loop, websocket, event.transcript, turn_counter['count'])
        else:
            # Partial transcript
            logger.info(f"📝 Partial (Turn in progress): '{event.transcript}'")
            schedule_websocket_message(loop, websocket, {
                "type": "partial_transcript",
                "text": event.transcript,
                "speaking_status": "user_speaking",
                "timestamp": datetime.now().isoformat()
            })

def handle_error(error: StreamingError, websocket: WebSocket, loop: asyncio.AbstractEventLoop):
    logger.error(f"❌ Enhanced Turn Detection error: {error}")
    schedule_websocket_message(loop, websocket, {
        "type": "error",
        "message": str(error),
        "timestamp": datetime.now().isoformat()
    })

def handle_termination(event: TerminationEvent, websocket: WebSocket, loop: asyncio.AbstractEventLoop):
    logger.info(f"🔒 Turn Detection session terminated: {event.audio_duration_seconds}s")
    schedule_websocket_message(loop, websocket, {
        "type": "session_terminated",
        "message": f"Turn detection session ended - {event.audio_duration_seconds} seconds processed",
        "total_audio_duration": event.audio_duration_seconds,
        "timestamp": datetime.now().isoformat()
    })

if __name__ == "__main__":
    import uvicorn
    logger.info("🎙️ Starting Day 20 - Streaming LLM -> Murf WS stream-input Server")
    uvicorn.run(app, host="127.0.0.1", port=8000)
