# services/murf_ws.py - Day 21: Modified to stream audio to client

import os
import asyncio
import json
import logging
import urllib.parse
import websockets
from datetime import datetime

logger = logging.getLogger(__name__)

class MurfStreamInputWS:
    """
    Murf TTS WebSocket client for stream-input contract:
    - Connect: wss://api.murf.ai/v1/speech/stream-input?api-key=...&sample_rate=...&channel_type=...&format=...
    - Send voice_config first
    - Send multiple {"text": "..."} messages (one per LLM chunk)
    - End with {"end": true}
    - Receive {"audio": "", "final": bool}; forward base64 to client
    """

    def __init__(
        self,
        api_key: str,
        voice_id: str,
        sample_rate: int = 44100,
        channel_type: str = "MONO", # MONO or STEREO
        audio_format: str = "WAV", # WAV or MP3 (per docs)
        style: str = "Conversational",
        rate: int = 0,
        pitch: int = 0,
        variation: int = 1,
    ):
        if not api_key:
            raise ValueError("Murf API key is required")
        if not voice_id:
            raise ValueError("Murf voice_id is required")

        self.api_key = api_key.strip()
        self.voice_id = voice_id.strip()
        self.sample_rate = sample_rate
        self.channel_type = channel_type
        self.audio_format = audio_format
        self.style = style
        self.rate = rate
        self.pitch = pitch
        self.variation = variation
        self.ws = None
        self._connected = False
        self._done = asyncio.Event()
        
        # NEW: Client WebSocket reference for forwarding audio
        self.client_websocket = None
        self.turn_number = None

    def _build_url(self) -> str:
        base = "wss://api.murf.ai/v1/speech/stream-input"
        qs = urllib.parse.urlencode({
            "api-key": self.api_key,
            "sample_rate": str(self.sample_rate),
            "channel_type": self.channel_type,
            "format": self.audio_format,
        })
        return f"{base}?{qs}"

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()

    async def connect(self):
        url = self._build_url()
        self.ws = await websockets.connect(url, max_size=None)
        self._connected = True
        logger.info("🔊 Connected to Murf stream-input WebSocket")

        # Send voice configuration first
        voice_config_msg = {
            "voice_config": {
                "voiceId": self.voice_id,
                "style": self.style,
                "rate": self.rate,
                "pitch": self.pitch,
                "variation": self.variation,
            }
        }
        await self._send_json(voice_config_msg)

        # Start listener
        asyncio.create_task(self._listen())

    async def close(self):
        if self._connected and self.ws:
            try:
                await self.ws.close()
            except Exception as e:
                logger.warning(f"Murf WS close error: {e}")
        self._connected = False
        self.ws = None
        logger.info("🔊 Murf stream-input WebSocket closed")

    async def _send_json(self, payload: dict):
        if not self._connected or not self.ws:
            raise RuntimeError("Murf WS not connected")
        await self.ws.send(json.dumps(payload))

    async def send_text_chunk(self, text: str, end: bool = False):
        """
        Send a chunk of text. Set end=True for the last message.
        """
        if not text and not end:
            return

        msg = {"text": text} if text else {}
        if end:
            msg["end"] = True

        await self._send_json(msg)

    async def wait_for_complete(self, timeout: float = 90.0):
        try:
            await asyncio.wait_for(self._done.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("Murf stream-input session timed out waiting for final audio")

    async def _listen(self):
        try:
            async for message in self.ws:
                try:
                    data = json.loads(message)
                except Exception:
                    logger.debug(f"Murf non-JSON message: {message}")
                    continue

                # Murf sends {"audio":"", "final": bool, ...}
                if "audio" in data:
                    b64 = data.get("audio", "")
                    # Print base64 chunk (truncate for log readability)
                    logger.info(f"🎧 Murf base64 audio chunk: {b64[:120]}... (len={len(b64)})")
                    
                    # NEW: Forward base64 chunk to client WebSocket
                    if self.client_websocket and b64:
                        try:
                            await self.client_websocket.send_text(json.dumps({
                                "type": "audio_chunk",
                                "audio_data": b64,
                                "final": data.get("final", False),
                                "turn_number": self.turn_number,
                                "timestamp": datetime.now().isoformat()
                            }))
                            logger.info(f"✅ Forwarded audio chunk to client (turn {self.turn_number})")
                        except Exception as e:
                            logger.error(f"Error sending audio chunk to client: {e}")

                    if data.get("final"):
                        logger.info("✅ Murf stream-input synthesis complete")
                        # Send final audio completion message to client
                        if self.client_websocket:
                            try:
                                await self.client_websocket.send_text(json.dumps({
                                    "type": "audio_streaming_complete",
                                    "turn_number": self.turn_number,
                                    "message": f"Audio streaming complete for turn {self.turn_number}",
                                    "timestamp": datetime.now().isoformat()
                                }))
                            except Exception as e:
                                logger.error(f"Error sending audio completion to client: {e}")
                        self._done.set()

        except websockets.ConnectionClosed as e:
            logger.info(f"Murf WS connection closed: {e}")
            self._done.set()
        except Exception as e:
            logger.error(f"Murf WS listener error: {e}")
            self._done.set()
