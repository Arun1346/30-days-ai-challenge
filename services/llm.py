# services/llm.py - COMPLETE FINAL VERSION

import os
import google.generativeai as genai
import logging
from google.generativeai.types import HarmCategory, HarmBlockThreshold

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# In-memory datastore for chat history
chat_histories = {}

def get_streaming_llm_response(session_id: str, user_text: str):
    """
    Gets a STREAMING response from Google Gemini with chat history.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.error("Gemini API key not found.")
        raise ValueError("Gemini API key not found.")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')

    # Initialize or get existing chat history
    if session_id not in chat_histories:
        chat_histories[session_id] = []
        logger.info(f"✅ NEW CHAT SESSION: {session_id}")
    else:
        logger.info(f"🔄 EXISTING SESSION: {session_id} with {len(chat_histories[session_id])} messages")

    # Start chat with existing history
    chat = model.start_chat(history=chat_histories[session_id])
    
    logger.info(f"💭 Getting streaming LLM response for session {session_id}...")
    logger.info(f"📝 User input: '{user_text}'")

    # Send message and get streaming response
    response = chat.send_message(
        user_text,
        stream=True,
        safety_settings={
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        }
    )

    # Return the streaming response AND chat instance for history updates
    return response, chat

def get_llm_response(session_id: str, user_text: str) -> str:
    """
    Gets a response from the Google Gemini LLM (non-streaming version).
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.error("Gemini API key not found.")
        raise ValueError("Gemini API key not found.")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')

    if session_id not in chat_histories:
        chat_histories[session_id] = []

    logger.info(f"Getting LLM response for session {session_id}...")
    chat = model.start_chat(history=chat_histories[session_id])
    llm_response = chat.send_message(user_text)
    llm_response_text = llm_response.text
    chat_histories[session_id] = chat.history

    logger.info(f"LLM response received: '{llm_response_text}'")
    return llm_response_text
