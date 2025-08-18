# app.py - FINAL WORKING VERSION WITH THREADING ISSUE FIXED

import os
from fastapi import (
    FastAPI,
    File,
    UploadFile,
    Query,
    HTTPException,
    WebSocket,
    WebSocketDisconnect
)
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
import logging
import uuid
import asyncio
import json
import threading

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

# Configure AssemblyAI - CORRECT IMPORTS WITH THREADING FIX
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
    logger.info("✅ AssemblyAI configured successfully with Universal Streaming")
    
except ImportError as e:
    logger.error(f"AssemblyAI import failed: {e}")
    raise

# --- Standard HTTP Endpoints ---

@app.get("/", response_class=HTMLResponse)
def read_root():
    """Serves the main HTML page."""
    with open("templates/index.html", "r") as f:
        return f.read()

@app.get("/voices")
def get_voices_endpoint():
    """
    Endpoint to get available voices.
    This function now transforms the Murf AI voice data into the format
    expected by the frontend JavaScript.
    """
    try:
        murf_voices = tts.get_voices()
        # Transform the data structure to match the frontend's expectation
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

# --- THREAD-SAFE HELPER FUNCTION ---

def schedule_websocket_message(loop: asyncio.AbstractEventLoop, websocket: WebSocket, message: dict):
    """Thread-safe function to schedule WebSocket messages from background threads"""
    try:
        coro = websocket.send_text(json.dumps(message))
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future
    except Exception as e:
        logger.error(f"Error scheduling WebSocket message: {e}")

# --- WORKING UNIVERSAL STREAMING WEBSOCKET ENDPOINT ---

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint using Universal Streaming API with threading fix
    """
    await websocket.accept()
    logger.info("🔗 WebSocket connection established.")
    session_id = str(uuid.uuid4())
    
    # Get the current event loop for thread-safe operations
    loop = asyncio.get_running_loop()
    
    # Store client for cleanup
    streaming_client = None
    
    try:
        # Create Universal Streaming client
        streaming_client = StreamingClient(
            StreamingClientOptions(
                api_key=api_key,
                api_host="streaming.assemblyai.com"
            )
        )
        
        # Set up event handlers with thread-safe websocket messaging
        streaming_client.on(StreamingEvents.Begin, lambda client, event: handle_begin(event, websocket, loop))
        streaming_client.on(StreamingEvents.Turn, lambda client, event: handle_turn(event, websocket, loop))
        streaming_client.on(StreamingEvents.Error, lambda client, error: handle_error(error, websocket, loop))
        streaming_client.on(StreamingEvents.Termination, lambda client, event: handle_termination(event, websocket, loop))
        
        # Connect with streaming parameters
        streaming_client.connect(
            StreamingParameters(
                sample_rate=16000,
                format_turns=True,
                end_of_turn_confidence_threshold=0.8,
                min_end_of_turn_silence_when_confident=500,
                max_turn_silence=2000
            )
        )
        
        logger.info("✅ Connected to AssemblyAI Universal Streaming!")
        
        # Send connection success to client
        await websocket.send_text(json.dumps({
            "type": "connection_established",
            "message": "Connected to AssemblyAI Universal Streaming",
            "session_id": session_id
        }))
        
        # Main WebSocket loop
        while True:
            try:
                # Receive audio data from client
                data = await websocket.receive_bytes()
                
                # Stream to AssemblyAI
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
        # Cleanup
        if streaming_client:
            try:
                logger.info("🧹 Cleaning up AssemblyAI connection...")
                streaming_client.disconnect(terminate=True)
                logger.info("✅ AssemblyAI connection cleaned up")
            except Exception as e:
                logger.error(f"Error during cleanup: {e}")

# --- THREAD-SAFE EVENT HANDLERS FOR UNIVERSAL STREAMING ---

def handle_begin(event: BeginEvent, websocket: WebSocket, loop: asyncio.AbstractEventLoop):
    """Handle session begin event - THREAD SAFE"""
    logger.info(f"🚀 Universal Streaming session began: {event.id}")
    schedule_websocket_message(loop, websocket, {
        "type": "session_begin",
        "session_id": event.id
    })

def handle_turn(event: TurnEvent, websocket: WebSocket, loop: asyncio.AbstractEventLoop):
    """Handle turn event (both partial and final transcripts) - THREAD SAFE"""
    if event.transcript:
        if event.end_of_turn:
            logger.info(f"🎯 Final: {event.transcript}")
            schedule_websocket_message(loop, websocket, {
                "type": "final_transcript",
                "text": event.transcript
            })
        else:
            logger.info(f"📝 Partial: {event.transcript}")
            schedule_websocket_message(loop, websocket, {
                "type": "partial_transcript",
                "text": event.transcript
            })

def handle_error(error: StreamingError, websocket: WebSocket, loop: asyncio.AbstractEventLoop):
    """Handle error event - THREAD SAFE"""
    logger.error(f"❌ Universal Streaming error: {error}")
    schedule_websocket_message(loop, websocket, {
        "type": "error",
        "message": str(error)
    })

def handle_termination(event: TerminationEvent, websocket: WebSocket, loop: asyncio.AbstractEventLoop):
    """Handle session termination event - THREAD SAFE"""
    logger.info(f"🔒 Universal Streaming session terminated: {event.audio_duration_seconds}s")
    schedule_websocket_message(loop, websocket, {
        "type": "session_terminated",
        "message": f"Session ended - {event.audio_duration_seconds} seconds processed"
    })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
