# app.py - Day 27 Complete A.R.I.A Voice Agent with Configuration Panel
import os
import logging
import uuid
import asyncio
import json
import threading
import time
import re
from datetime import datetime
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from pydantic import BaseModel
from typing import Dict, Any

# Import configuration manager
from config_manager import config_manager

# Import services
from services import llm, tts
from services.murf_ws import MurfStreamInputWS

# AssemblyAI imports - MOVED TO MODULE LEVEL TO FIX THE ERROR
import assemblyai as aai
from assemblyai.streaming.v3 import (
    BeginEvent, StreamingClient, StreamingClientOptions,
    StreamingError, StreamingEvents, StreamingParameters,
    TerminationEvent, TurnEvent
)

# Load environment variables
load_dotenv()

# Enhanced logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('aria_day27.log')
    ]
)
logger = logging.getLogger(__name__)

app = FastAPI(title="A.R.I.A Voice Agent - Day 27", version="2.0.0")

# Create static directory if it doesn't exist
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Pydantic models for API requests
class ApiKeysRequest(BaseModel):
    keys: Dict[str, str]

class ToggleEnvRequest(BaseModel):
    use_env: bool

# --- Rate Limiter for API Calls ---
class RateLimiter:
    def __init__(self, max_requests=40, time_window=86400):
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = []

    def can_make_request(self):
        now = datetime.now()
        self.requests = [req_time for req_time in self.requests
                        if (now - req_time).total_seconds() < self.time_window]
        return len(self.requests) < self.max_requests

    def add_request(self):
        self.requests.append(datetime.now())

rate_limiter = RateLimiter()

# --- Configure Services with Dynamic API Keys ---
def configure_services():
    """Configure all services with current API keys"""
    try:
        # AssemblyAI
        assemblyai_key = config_manager.get_api_key("assemblyai")
        if assemblyai_key:
            aai.settings.api_key = assemblyai_key
            logger.info("✅ AssemblyAI configured")

        # Gemini
        gemini_key = config_manager.get_api_key("gemini")
        if gemini_key:
            import google.generativeai as genai
            genai.configure(api_key=gemini_key)
            logger.info("✅ Gemini configured")

        return True
    except Exception as e:
        logger.error(f"Error configuring services: {e}")
        return False

# Initialize services
configure_services()

# --- HTTP Endpoints ---
@app.get("/", response_class=HTMLResponse)
async def read_root():
    """Serve the main HTML page"""
    try:
        with open("templates/index.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="HTML file not found")

@app.get("/voices")
async def get_voices_endpoint():
    """Get available Murf voices"""
    try:
        murf_key = config_manager.get_api_key("murf")
        if not murf_key:
            raise HTTPException(status_code=400, detail="Murf API key not configured")
        
        # Temporarily override environment for this call
        original_key = os.environ.get("MURF_API_KEY")
        os.environ["MURF_API_KEY"] = murf_key
        
        try:
            murf_voices = tts.get_voices()
            formatted_voices = []
            
            for voice in murf_voices:
                voice_name = voice.get("name") or voice.get("voiceId")
                formatted_voices.append({
                    "voice_id": voice.get("voiceId"),
                    "name": voice_name,
                    "labels": {"gender": voice.get("gender", "Unknown")}
                })
                
            logger.info(f"✅ Loaded {len(formatted_voices)} voices")
            return {"voices": formatted_voices}
            
        finally:
            # Restore original environment
            if original_key:
                os.environ["MURF_API_KEY"] = original_key
            elif "MURF_API_KEY" in os.environ:
                del os.environ["MURF_API_KEY"]
                
    except Exception as e:
        logger.error(f"Error fetching voices: {e}")
        raise HTTPException(status_code=500, detail=f"Could not fetch voices: {str(e)}")

# --- Configuration API Endpoints ---
@app.post("/api/config/keys")
async def set_api_keys(request: ApiKeysRequest):
    """Set API keys from user input"""
    try:
        success_count = 0
        for service, key in request.keys.items():
            if config_manager.set_api_key(service, key):
                success_count += 1
        
        # Reconfigure services with new keys
        configure_services()
        
        return {
            "success": True, 
            "message": f"Updated {success_count} API keys successfully",
            "configured_services": success_count
        }
    except Exception as e:
        logger.error(f"Error setting API keys: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/config/toggle-env")
async def toggle_env_keys(request: ToggleEnvRequest):
    """Toggle between environment and user keys"""
    try:
        config_manager.set_use_env_keys(request.use_env)
        configure_services()
        
        return {
            "success": True, 
            "use_env": request.use_env,
            "message": f"{'Using' if request.use_env else 'Not using'} environment keys"
        }
    except Exception as e:
        logger.error(f"Error toggling env keys: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/config/test/{service}")
async def test_api_key(service: str):
    """Test API key for a specific service"""
    try:
        result = await config_manager.test_api_connection(service.lower())
        return result
    except Exception as e:
        logger.error(f"Error testing {service}: {e}")
        return {"connected": False, "error": str(e)}

@app.get("/api/config/status")
async def get_config_status():
    """Get comprehensive configuration status"""
    try:
        status = config_manager.get_status_summary()
        return status
    except Exception as e:
        logger.error(f"Error getting config status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/config/export")
async def export_config():
    """Export configuration"""
    try:
        config_data = config_manager.export_config()
        return JSONResponse(
            content=json.loads(config_data),
            headers={
                "Content-Disposition": "attachment; filename=aria_config.json",
                "Content-Type": "application/json"
            }
        )
    except Exception as e:
        logger.error(f"Error exporting config: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- Utility Functions ---
def normalize_text(text: str) -> str:
    """Remove punctuation and convert to lowercase for comparison"""
    return re.sub(r'[^\w\s]', '', text.strip().lower())

def schedule_websocket_message(loop: asyncio.AbstractEventLoop, websocket: WebSocket, message: dict):
    """Thread-safe WebSocket message sending"""
    try:
        coro = websocket.send_text(json.dumps(message))
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future
    except Exception as e:
        logger.error(f"Error scheduling WebSocket message: {e}")

# In app.py, replace the Murf WebSocket section with HTTP streaming:

def schedule_llm_streaming(loop: asyncio.AbstractEventLoop, websocket: WebSocket,
                          user_input: str, turn_number: int, session_id: str):
    """Enhanced LLM streaming with Murf HTTP streaming"""
    
    def stream_llm_response():
        try:
            # Rate limiting check (existing code)
            if not rate_limiter.can_make_request():
                logger.warning("⚠️ Rate limit reached")
                schedule_websocket_message(loop, websocket, {
                    "type": "llm_error",
                    "turn_number": turn_number,
                    "error": "Daily quota limit reached. Try again tomorrow!",
                    "timestamp": datetime.now().isoformat()
                })
                return

            rate_limiter.add_request()

            # Get current API keys
            gemini_key = config_manager.get_api_key("gemini")
            murf_key = config_manager.get_api_key("murf")
            
            if not gemini_key:
                raise ValueError("Gemini API key not configured")
            if not murf_key:
                raise ValueError("Murf AI API key not configured")

            logger.info(f"🤖 Starting LLM streaming for turn #{turn_number}")
            
            # Configure LLM streaming (existing code)
            import google.generativeai as genai
            genai.configure(api_key=gemini_key)
            
            from services.llm import get_streaming_llm_response, chat_histories
            
            # Get streaming response from Gemini
            streaming_response, chat_instance = get_streaming_llm_response(
                session_id, user_input, gemini_key, config_manager.get_api_key("tavily") or ""
            )
            
            accumulated_response = ""
            
            # Collect all LLM text first
            for chunk in streaming_response:
                if hasattr(chunk, "text") and chunk.text:
                    text_piece = chunk.text
                    accumulated_response += text_piece
                    
                    schedule_websocket_message(loop, websocket, {
                        "type": "llm_chunk",
                        "turn_number": turn_number,
                        "chunk": text_piece,
                        "accumulated": accumulated_response,
                        "timestamp": datetime.now().isoformat()
                    })

            # Now generate audio from complete text using HTTP streaming
            async def generate_audio():
                from services.murf_http_stream import MurfHTTPStreaming
                
                murf_client = MurfHTTPStreaming(murf_key)
                voice_id = os.getenv("MURF_DEFAULT_VOICE_ID", "en-US-natalie")
                
                try:
                    # Collect all audio chunks
                    audio_chunks = []
                    async for chunk in murf_client.stream_text_to_audio(accumulated_response, voice_id):
                        audio_chunks.append(chunk)
                    
                    if audio_chunks:
                        # Combine all chunks
                        complete_audio = b''.join(audio_chunks)
                        audio_base64 = base64.b64encode(complete_audio).decode('utf-8')
                        
                        # Send complete audio to client
                        await websocket.send_text(json.dumps({
                            "type": "audio_chunk",
                            "turn_number": turn_number,
                            "audio_data": audio_base64,
                            "final": True,
                            "timestamp": datetime.now().isoformat()
                        }))
                        
                        logger.info(f"🎵 Sent complete audio: {len(complete_audio)} bytes")
                    
                except Exception as e:
                    logger.error(f"Audio generation failed: {e}")
                    await websocket.send_text(json.dumps({
                        "type": "audio_error",
                        "turn_number": turn_number,
                        "error": str(e),
                        "timestamp": datetime.now().isoformat()
                    }))

            # Run audio generation
            audio_task = asyncio.run_coroutine_threadsafe(generate_audio(), loop)
            audio_task.result(timeout=60)
            
            # Update chat history
            chat_histories[session_id] = chat_instance.history
            
            schedule_websocket_message(loop, websocket, {
                "type": "llm_streaming_complete",
                "turn_number": turn_number,
                "full_response": accumulated_response,
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

# --- WebSocket Endpoint ---
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("🔗 WebSocket connection established for A.R.I.A Day 27")
    
    session_id = str(uuid.uuid4())
    loop = asyncio.get_running_loop()
    streaming_client = None
    
    # Check configuration before starting
    config_status = config_manager.get_status_summary()
    if not config_status["overall_health"]:
        await websocket.send_text(json.dumps({
            "type": "config_error",
            "message": f"Missing API keys for: {', '.join(config_status['missing_services'])}",
            "missing_services": config_status["missing_services"],
            "timestamp": datetime.now().isoformat()
        }))
        return

    # Turn tracking
    turn_counter = {'count': 0}
    last_turn = {'raw': '', 'timestamp': 0.0}

    try:
        # Get current AssemblyAI key
        assemblyai_key = config_manager.get_api_key("assemblyai")
        if not assemblyai_key:
            raise ValueError("AssemblyAI API key not configured")

        # Configure AssemblyAI
        aai.settings.api_key = assemblyai_key
        
        streaming_client = StreamingClient(
            StreamingClientOptions(
                api_key=assemblyai_key,
                api_host="streaming.assemblyai.com"
            )
        )

        # Event handlers
        streaming_client.on(StreamingEvents.Begin,
            lambda client, event: handle_begin(event, websocket, loop))
        streaming_client.on(StreamingEvents.Turn,
            lambda client, event: handle_turn_with_llm_streaming(
                event, websocket, loop, turn_counter, last_turn, session_id))
        streaming_client.on(StreamingEvents.Error,
            lambda client, error: handle_error(error, websocket, loop))
        streaming_client.on(StreamingEvents.Termination,
            lambda client, event: handle_termination(event, websocket, loop))

        # Connect with enhanced parameters
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

        logger.info("🚀 Connected to AssemblyAI with Dynamic Configuration!")
        
        await websocket.send_text(json.dumps({
            "type": "connection_established",
            "message": "A.R.I.A Day 27 ready with dynamic API configuration",
            "session_id": session_id,
            "config_status": config_status,
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
        logger.error(f"Failed to establish connection: {e}")
        await websocket.send_text(json.dumps({
            "type": "error",
            "message": f"Failed to connect: {str(e)}"
        }))
    finally:
        if streaming_client:
            try:
                logger.info("🧹 Cleaning up connections...")
                streaming_client.disconnect(terminate=True)
                logger.info("✅ Cleanup complete")
            except Exception as e:
                logger.error(f"Error during cleanup: {e}")

# --- Event Handlers - NOW WITH PROPER IMPORTS ---
def handle_begin(event: BeginEvent, websocket: WebSocket, loop: asyncio.AbstractEventLoop):
    logger.info(f"🚀 A.R.I.A session began: {event.id}")
    schedule_websocket_message(loop, websocket, {
        "type": "session_begin",
        "session_id": event.id,
        "message": "A.R.I.A Day 27 active - speak naturally!",
        "timestamp": datetime.now().isoformat()
    })

def handle_turn_with_llm_streaming(event: TurnEvent, websocket: WebSocket, 
                                 loop: asyncio.AbstractEventLoop, turn_counter: dict, 
                                 last_turn: dict, session_id: str):
    """Enhanced turn handler with dynamic configuration"""
    if event.transcript:
        if event.end_of_turn:
            current_time = time.time()
            current_normalized = normalize_text(event.transcript)
            last_normalized = normalize_text(last_turn['raw'])

            # Check for punctuation-only updates
            if (current_normalized == last_normalized and last_turn['raw'] and
                (current_time - last_turn['timestamp']) < 2.0):
                if event.transcript != last_turn['raw']:
                    logger.info(f"✏️ Updating punctuation for turn #{turn_counter['count']}")
                    schedule_websocket_message(loop, websocket, {
                        "type": "turn_updated",
                        "turn_number": turn_counter['count'],
                        "final_transcript": event.transcript,
                        "timestamp": datetime.now().isoformat()
                    })
                    last_turn['raw'] = event.transcript
                    last_turn['timestamp'] = current_time
                return

            # New turn
            turn_counter['count'] += 1
            last_turn['raw'] = event.transcript
            last_turn['timestamp'] = current_time

            logger.info(f"🎯 TURN #{turn_counter['count']} COMPLETED: '{event.transcript}'")

            schedule_websocket_message(loop, websocket, {
                "type": "turn_completed",
                "turn_number": turn_counter['count'],
                "final_transcript": event.transcript,
                "end_of_turn": True,
                "timestamp": datetime.now().isoformat()
            })

            schedule_websocket_message(loop, websocket, {
                "type": "final_transcript",
                "text": event.transcript,
                "turn_number": turn_counter['count']
            })

            # Trigger LLM streaming
            if event.transcript.strip():
                schedule_llm_streaming(loop, websocket, event.transcript, 
                                     turn_counter['count'], session_id)
        else:
            # Partial transcript
            schedule_websocket_message(loop, websocket, {
                "type": "partial_transcript",
                "text": event.transcript,
                "timestamp": datetime.now().isoformat()
            })

def handle_error(error: StreamingError, websocket: WebSocket, loop: asyncio.AbstractEventLoop):
    logger.error(f"❌ A.R.I.A error: {error}")
    schedule_websocket_message(loop, websocket, {
        "type": "error",
        "message": str(error),
        "timestamp": datetime.now().isoformat()
    })

def handle_termination(event: TerminationEvent, websocket: WebSocket, loop: asyncio.AbstractEventLoop):
    logger.info(f"🔒 A.R.I.A session terminated: {event.audio_duration_seconds}s")
    schedule_websocket_message(loop, websocket, {
        "type": "session_terminated",
        "message": f"A.R.I.A session ended - {event.audio_duration_seconds} seconds processed",
        "total_audio_duration": event.audio_duration_seconds,
        "timestamp": datetime.now().isoformat()
    })


if __name__ == "__main__":
    import uvicorn
    import os
    
    # Get port from environment variable (Render sets this)
    port = int(os.environ.get("PORT", 8000))
    
    logger.info(f"🎙️ Starting A.R.I.A Day 27 on port {port}")
    uvicorn.run(
        app, 
        host="0.0.0.0",  # Important: bind to all interfaces for cloud deployment
        port=port,
        log_level="info"
    )