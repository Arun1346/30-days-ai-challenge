# services/llm.py
import os
import google.generativeai as genai
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# In-memory datastore for chat history
chat_histories = {}

def get_llm_response(session_id: str, user_text: str) -> str:
    """
    Gets a response from the Google Gemini LLM.
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
