# app.py - DAY 19 STREAMING LLM RESPONSES - CORRECTED VERSION

import os
from fastapi import (
    FastAPI, File, UploadFile, Query,
    HTTPException, WebSocket, WebSocketDisconnect
)
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
import logging
import uuid
import asyncio
import json
import threading
import time
from datetime import datetime
import re

# Import our service and schema modules
from schemas import AgentChatResponse, ErrorResponse
from services import stt, llm, tts

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

# Configure AssemblyAI with Enhanced Turn Detection
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

# DAY 19: Configure Google Gemini API for Streaming
try:
    import google.generativeai as genai
    from google.generativeai.types import HarmCategory, HarmBlockThreshold

    # Configure Gemini API
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if not gemini_api_key:
        logger.error("Gemini API key not found.")
        raise ValueError("Gemini API key not found.")

    genai.configure(api_key=gemini_api_key)

    # CORRECTED: Use gemini-1.5-flash instead of gemini-pro
    model = genai.GenerativeModel('gemini-1.5-flash')
    logger.info("✅ Google Gemini 1.5 Flash configured successfully for streaming LLM responses")

except ImportError as e:
    logger.error(f"Google Generative AI import failed: {e}")
    raise

# --- Standard HTTP Endpoints ---

@app.get("/", response_class=HTMLResponse)
def read_root():
    """Serves the main HTML page."""
    with open("templates/index.html", "r") as f:
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

# --- UTILITY FUNCTIONS ---

def normalize_text(text):
    """Remove punctuation and convert to lowercase for comparison"""
    return re.sub(r'[^\w\s]', '', text.strip().lower())

# --- THREAD-SAFE HELPER FUNCTION ---

def schedule_websocket_message(loop: asyncio.AbstractEventLoop, websocket: WebSocket, message: dict):
    try:
        coro = websocket.send_text(json.dumps(message))
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future
    except Exception as e:
        logger.error(f"Error scheduling WebSocket message: {e}")

# DAY 19: LLM STREAMING FUNCTION - CORRECTED

def schedule_llm_streaming(loop: asyncio.AbstractEventLoop, websocket: WebSocket, user_input: str, turn_number: int):
    """Schedule LLM streaming response in a separate thread"""
    def stream_llm_response():
        try:
            logger.info(f"🤖 Starting LLM streaming for turn #{turn_number}: '{user_input}'")
            
            # Generate streaming response with corrected model
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
            
            # Send streaming start notification
            schedule_websocket_message(loop, websocket, {
                "type": "llm_streaming_start",
                "turn_number": turn_number,
                "message": f"🤖 AI responding to turn #{turn_number}...",
                "timestamp": datetime.now().isoformat()
            })
            
            # Stream the response
            for chunk in response:
                if chunk.text:
                    accumulated_response += chunk.text
                    
                    # Log each chunk to console
                    logger.info(f"🤖 LLM Chunk: '{chunk.text}'")
                    
                    # Send chunk to frontend
                    schedule_websocket_message(loop, websocket, {
                        "type": "llm_chunk",
                        "turn_number": turn_number,
                        "chunk": chunk.text,
                        "accumulated": accumulated_response,
                        "timestamp": datetime.now().isoformat()
                    })
            
            # Send completion notification
            logger.info("="*60)
            logger.info(f"🤖 LLM RESPONSE COMPLETED for turn #{turn_number}")
            logger.info(f"📝 Full Response: '{accumulated_response}'")
            logger.info(f"📊 Response Length: {len(accumulated_response)} characters")
            logger.info("="*60)
            
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
    
    # Run in separate thread to avoid blocking
    threading.Thread(target=stream_llm_response, daemon=True).start()

# --- DAY 19 ENHANCED WEBSOCKET ENDPOINT ---

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("🔗 WebSocket connection established for Day 19 Streaming LLM.")
    session_id = str(uuid.uuid4())
    loop = asyncio.get_running_loop()
    streaming_client = None

    # Turn tracking variables with punctuation handling
    turn_counter = {'count': 0}
    last_turn = {'raw': '', 'timestamp': 0}

    try:
        streaming_client = StreamingClient(
            StreamingClientOptions(
                api_key=api_key,
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

# --- EVENT HANDLERS ---

def handle_begin(event: BeginEvent, websocket: WebSocket, loop: asyncio.AbstractEventLoop):
    logger.info(f"🚀 Enhanced Turn Detection with LLM Streaming session began: {event.id}")
    schedule_websocket_message(loop, websocket, {
        "type": "session_begin",
        "session_id": event.id,
        "message": "Turn detection with LLM streaming active - speak naturally and pause to complete turns",
        "timestamp": datetime.now().isoformat()
    })

def handle_turn_with_llm_streaming(event: TurnEvent, websocket: WebSocket, loop: asyncio.AbstractEventLoop, turn_counter: dict, last_turn: dict):
    """UPDATED: Handle turns with LLM streaming integration"""
    
    if event.transcript:
        if event.end_of_turn:
            current_time = time.time()
            current_normalized = normalize_text(event.transcript)
            last_normalized = normalize_text(last_turn['raw'])

            # Check if this is a punctuation update of the same turn (within 2 seconds)
            if (current_normalized == last_normalized and
                last_turn['raw'] and
                (current_time - last_turn['timestamp']) < 2.0):

                # This is a punctuation update, not a new turn
                if event.transcript != last_turn['raw']:
                    logger.info(f"✏️ Updating punctuation for turn #{turn_counter['count']}: '{event.transcript}'")
                    
                    # Send update message to frontend
                    schedule_websocket_message(loop, websocket, {
                        "type": "turn_updated",
                        "turn_number": turn_counter['count'],
                        "final_transcript": event.transcript,
                        "message": f"Turn #{turn_counter['count']} updated with punctuation",
                        "timestamp": datetime.now().isoformat(),
                        "audio_duration": getattr(event, 'duration_seconds', None)
                    })

                    # Update the stored transcript
                    last_turn['raw'] = event.transcript
                    last_turn['timestamp'] = current_time
                else:
                    logger.info(f"🔁 Skipping identical punctuation update for turn #{turn_counter['count']}")
                
                return  # Don't increment turn counter or trigger LLM

            # This is a new turn
            turn_counter['count'] += 1
            last_turn['raw'] = event.transcript
            last_turn['timestamp'] = current_time

            logger.info("="*60)
            logger.info(f"🎯 TURN #{turn_counter['count']} COMPLETED!")
            logger.info(f"📝 Final Transcript: '{event.transcript}'")
            logger.info(f"⏱️ Turn Duration: {getattr(event, 'duration_seconds', 'N/A')}s")
            logger.info(f"🔇 End of Turn Detected - User stopped speaking")
            logger.info(f"🕒 Timestamp: {datetime.now().strftime('%H:%M:%S.%f')[:-3]}")
            logger.info("="*60)

            # Send new turn completion to client
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

            # DAY 19: NEW - Trigger LLM streaming response
            if event.transcript.strip():  # Only if there's actual content
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
    logger.info("🎙️ Starting Day 19 - Streaming LLM Responses Server")
    uvicorn.run(app, host="127.0.0.1", port=8000)
