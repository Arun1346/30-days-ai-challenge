# services/murf_http_stream.py
import asyncio
import aiohttp
import base64
import json
import logging
from typing import AsyncIterator

logger = logging.getLogger(__name__)

class MurfHTTPStreaming:
    """Murf HTTP Streaming client for reliable audio generation."""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.murf.ai/v1/speech"
    
    async def stream_text_to_audio(self, text: str, voice_id: str = "en-US-natalie") -> AsyncIterator[bytes]:
        """Stream text to audio using Murf HTTP streaming API."""
        
        headers = {
            "api-key": self.api_key,
            "Content-Type": "application/json"
        }
        
        payload = {
            "text": text,
            "voiceId": voice_id
        }
        
        try:
            timeout = aiohttp.ClientTimeout(total=60)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{self.base_url}/stream",
                    headers=headers,
                    json=payload
                ) as response:
                    
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Murf HTTP streaming failed: {response.status} - {error_text}")
                        raise Exception(f"Murf API error: {response.status} - {error_text}")
                    
                    logger.info(f"🎵 Murf HTTP streaming started for: '{text[:50]}...'")
                    
                    # Stream audio chunks
                    chunk_count = 0
                    async for chunk in response.content.iter_chunked(8192):
                        if chunk:
                            chunk_count += 1
                            logger.debug(f"🎵 Received chunk {chunk_count}: {len(chunk)} bytes")
                            yield chunk
                            
                    logger.info(f"🎵 Murf HTTP streaming completed: {chunk_count} chunks")
                    
        except asyncio.TimeoutError:
            logger.error("🎵 Murf HTTP streaming timeout")
            raise Exception("Murf streaming timeout")
        except Exception as e:
            logger.error(f"🎵 Murf HTTP streaming error: {e}")
            raise
