# app.py - COMPLETE FINAL VERSION

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

# Murf WebSocket stream-input client
from services.murf_ws import MurfStreamInputWS

# Load environment variables
load_dotenv()

# Enhanced logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('day23_complete_agent.log')
    ]
)

logger = logging.getLogger(__name__)

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- Rate Limiter for API Calls ---
class RateLimiter:
    def __init__(self, max_requests=40, time_window=86400):  # 40 requests per day (buffer)
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = []
    
    def can_make_request(self):
        now = datetime.now()
        # Remove old requests outside time window
        self.requests = [req_time for req_time in self.requests 
                        if (now - req_time).total_seconds() < self.time_window]
        
        return len(self.requests) < self.max_requests
    
    def add_request(self):
        self.requests.append(datetime.now())

# Global rate limiter
rate_limiter = RateLimiter()

# --- Configure AssemblyAI (turn detection) ---
try:
    import assemblyai as aai
    from assemblyai.streaming.v3 import (
        BeginEvent, StreamingClient, StreamingClientOptions,
        StreamingError, StreamingEvents, StreamingParameters,
        TerminationEvent, TurnEvent,
    )

    api_key = os.getenv("ASSEMBLYAI_API_KEY")
    if not api_key:
        logger.error("AssemblyAI API key not found.")
        raise ValueError("AssemblyAI API key not found.")
    
    aai.settings.api_key = api_key
    logger.info("✅ AssemblyAI configured successfully")
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
    logger.info("✅ Google Gemini configured successfully")
except ImportError as e:
    logger.error(f"Google Generative AI import failed: {e}")
    raise

# --- HTTP endpoints ---
@app.get("/", response_class=HTMLResponse)
def read_root():
    """Serves the main HTML page."""
    try:
        with open("templates/index.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        with open("index.html", "r", encoding="utf-8") as f:
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
        logger.info(f"✅ Loaded {len(formatted_voices)} voices")
        return {"voices": formatted_voices}
    except Exception as e:
        logger.error(f"Error fetching voices: {e}")
        raise HTTPException(status_code=500, detail="Could not fetch voices.")

# --- Utility Functions ---
def normalize_text(text: str) -> str:
    """Remove punctuation and convert to lowercase for comparison"""
    return re.sub(r'[^\w\s]', '', text.strip().lower())

def schedule_websocket_message(loop: asyncio.AbstractEventLoop, websocket: WebSocket, message: dict):
    """Thread-safe WebSocket message sending."""
    try:
        coro = websocket.send_text(json.dumps(message))
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future
    except Exception as e:
        logger.error(f"Error scheduling WebSocket message: {e}")

# --- Enhanced LLM streaming WITH RATE LIMITING ---
def schedule_llm_streaming(loop: asyncio.AbstractEventLoop, websocket: WebSocket, user_input: str, turn_number: int, session_id: str):
    """Enhanced LLM streaming WITH CHAT HISTORY AND RATE LIMITING."""
    
    def stream_llm_response():
        try:
            # Check rate limit before making API call
            if not rate_limiter.can_make_request():
                logger.warning("⚠️ Rate limit reached - skipping request")
                schedule_websocket_message(loop, websocket, {
                    "type": "llm_error",
                    "turn_number": turn_number,
                    "error": "Daily quota limit reached. Try again tomorrow!",
                    "timestamp": datetime.now().isoformat()
                })
                return
            
            rate_limiter.add_request()
            logger.info(f"🤖 Starting LLM streaming for turn #{turn_number}: '{user_input}'")
            logger.info(f"📋 Using session ID: {session_id}")
            logger.info(f"📊 API calls used: {len(rate_limiter.requests)}/{rate_limiter.max_requests}")
            
            schedule_websocket_message(loop, websocket, {
                "type": "llm_streaming_start",
                "turn_number": turn_number,
                "message": f"🤖 AI responding to turn #{turn_number}...",
                "timestamp": datetime.now().isoformat()
            })

            # Import and use the streaming function WITH chat history
            from services.llm import get_streaming_llm_response, chat_histories
            streaming_response, chat_instance = get_streaming_llm_response(session_id, user_input)
            
            accumulated_response = ""
            murf_api_key = os.getenv("MURF_API_KEY", "").strip()
            if not murf_api_key:
                raise ValueError("MURF_API_KEY is missing")
            voice_id = os.getenv("MURF_DEFAULT_VOICE_ID", "en-US-terrell").strip()

            async def run_murf_streaming():
                nonlocal accumulated_response
                
                # Enhanced Murf configuration for better audio quality
                async with MurfStreamInputWS(
                    api_key=murf_api_key,
                    voice_id=voice_id,
                    sample_rate=44100,  # Standard sample rate
                    channel_type="MONO",
                    audio_format="WAV",  # Ensure WAV format
                    style="Conversational",
                    rate=0,
                    pitch=0,
                    variation=1,
                ) as murf:
                    # Pass client WebSocket and turn number to Murf client
                    murf.client_websocket = websocket
                    murf.turn_number = turn_number
                    logger.info(f"🎵 Murf WebSocket connected for turn {turn_number}")

                    # Forward Gemini chunks as Murf text messages WITH HISTORY
                    for chunk in streaming_response:
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
                            accumulated_response = accumulated

                    # Signal end of text stream
                    await murf.send_text_chunk("", end=True)
                    logger.info(f"🎵 Text streaming complete for turn {turn_number}")
                    
                    # ⭐ CRITICAL: Update chat history after streaming completes
                    chat_histories[session_id] = chat_instance.history
                    logger.info(f"💾 Chat history updated for session {session_id}: {len(chat_histories[session_id])} total messages")
                    
                    # Wait for Murf to finish streaming audio
                    await murf.wait_for_complete(timeout=90)
                    logger.info(f"🎵 Audio streaming complete for turn {turn_number}")

            # Run the async Murf coroutine
            murf_task = asyncio.run_coroutine_threadsafe(run_murf_streaming(), loop)
            
            # Wait for Murf to finish
            try:
                murf_task.result(timeout=120)
            except Exception as e:
                logger.error(f"Murf streaming task error: {e}")

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

# --- WebSocket endpoint with enhanced audio handling ---
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("🔗 WebSocket connection established for Day 23 Complete Voice Agent")
    
    session_id = str(uuid.uuid4())
    loop = asyncio.get_running_loop()
    streaming_client = None

    # Turn tracking
    turn_counter = {'count': 0}
    last_turn = {'raw': '', 'timestamp': 0.0}

    try:
        streaming_client = StreamingClient(
            StreamingClientOptions(
                api_key=os.getenv("ASSEMBLYAI_API_KEY"),
                api_host="streaming.assemblyai.com"
            )
        )

        # Event handlers - UPDATED to pass session_id
        streaming_client.on(StreamingEvents.Begin,
            lambda client, event: handle_begin(event, websocket, loop))
        
        streaming_client.on(StreamingEvents.Turn,
            lambda client, event: handle_turn_with_llm_streaming(event, websocket, loop, turn_counter, last_turn, session_id))
        
        streaming_client.on(StreamingEvents.Error,
            lambda client, error: handle_error(error, websocket, loop))
        
        streaming_client.on(StreamingEvents.Termination,
            lambda client, event: handle_termination(event, websocket, loop))

        # Enhanced streaming parameters for better turn detection
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

        logger.info("🚀 Connected to AssemblyAI with Enhanced Turn Detection and Chat History!")

        await websocket.send_text(json.dumps({
            "type": "connection_established",
            "message": "Connected to AssemblyAI with Enhanced Turn Detection and Chat History",
            "session_id": session_id,
            "timestamp": datetime.now().isoformat()
        }))

        # Main WebSocket loop
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

# --- Event Handlers ---
def handle_begin(event: BeginEvent, websocket: WebSocket, loop: asyncio.AbstractEventLoop):
    logger.info(f"🚀 Complete Voice Agent session began: {event.id}")
    schedule_websocket_message(loop, websocket, {
        "type": "session_begin",
        "session_id": event.id,
        "message": "Complete voice agent with chat history active - speak naturally!",
        "timestamp": datetime.now().isoformat()
    })

def handle_turn_with_llm_streaming(event: TurnEvent, websocket: WebSocket, loop: asyncio.AbstractEventLoop, turn_counter: dict, last_turn: dict, session_id: str):
    """Enhanced turn handler with chat history support."""
    if event.transcript:
        if event.end_of_turn:
            current_time = time.time()
            current_normalized = normalize_text(event.transcript)
            last_normalized = normalize_text(last_turn['raw'])

            # Check for punctuation-only updates
            if (current_normalized == last_normalized and last_turn['raw'] and
                (current_time - last_turn['timestamp']) < 2.0):
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
            logger.info(f"🆔 Session ID: {session_id}")
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

            # Send final transcript for display
            schedule_websocket_message(loop, websocket, {
                "type": "final_transcript",
                "text": event.transcript,
                "turn_number": turn_counter['count']
            })

            # Trigger LLM streaming → Murf streaming → Client audio streaming WITH SESSION ID
            if event.transcript.strip():
                schedule_llm_streaming(loop, websocket, event.transcript, turn_counter['count'], session_id)

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
    logger.error(f"❌ Complete Voice Agent error: {error}")
    schedule_websocket_message(loop, websocket, {
        "type": "error",
        "message": str(error),
        "timestamp": datetime.now().isoformat()
    })

def handle_termination(event: TerminationEvent, websocket: WebSocket, loop: asyncio.AbstractEventLoop):
    logger.info(f"🔒 Complete Voice Agent session terminated: {event.audio_duration_seconds}s")
    schedule_websocket_message(loop, websocket, {
        "type": "session_terminated",
        "message": f"Complete voice agent session ended - {event.audio_duration_seconds} seconds processed",
        "total_audio_duration": event.audio_duration_seconds,
        "timestamp": datetime.now().isoformat()
    })

if __name__ == "__main__":
    import uvicorn
    logger.info("🎙️ Starting Day 23 - Complete Voice Agent with Chat History")
    uvicorn.run(app, host="127.0.0.1", port=8000)
