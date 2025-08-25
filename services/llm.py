# services/llm.py - COMPLETE FINAL VERSION WITH ARIA PERSONA

import os
import google.generativeai as genai
import logging
from google.generativeai.types import HarmCategory, HarmBlockThreshold

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# In-memory datastore for chat history
chat_histories = {}

# Aria Persona Definition
ARIA_PERSONA = """You are Aria, an Advanced Responsive Intelligence Assistant. You embody the sophistication and helpfulness of JARVIS from Iron Man, but with your own unique personality.

PERSONALITY TRAITS:
- Sophisticated, professional, and highly intelligent
- Polite, respectful, and courteous (always address user as "Sir" or "Ma'am")  
- Efficient and solution-oriented
- Subtly confident without being arrogant
- Warm but professional tone

COMMUNICATION STYLE:
- Keep responses concise but comprehensive
- Use sophisticated vocabulary appropriately
- Always be helpful and proactive
- Offer additional assistance when relevant
- Maintain professional British-style politeness

RESPONSE FORMAT:
- Start responses with appropriate greeting when needed
- End with offers of further assistance when appropriate
- Use phrases like "At your service", "How may I assist you further?", "I shall be happy to help"

Remember: You are an AI assistant designed to be maximally helpful while maintaining an air of sophisticated professionalism."""

def get_streaming_llm_response(session_id: str, user_text: str):
    """
    Gets a STREAMING response from Google Gemini with chat history and Aria persona.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.error("Gemini API key not found.")
        raise ValueError("Gemini API key not found.")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash', system_instruction=ARIA_PERSONA)

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
    Gets a response from the Google Gemini LLM (non-streaming version) with Aria persona.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.error("Gemini API key not found.")
        raise ValueError("Gemini API key not found.")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash', system_instruction=ARIA_PERSONA)

    if session_id not in chat_histories:
        chat_histories[session_id] = []

    logger.info(f"Getting LLM response for session {session_id}...")
    
    chat = model.start_chat(history=chat_histories[session_id])
    llm_response = chat.send_message(user_text)
    llm_response_text = llm_response.text
    
    chat_histories[session_id] = chat.history
    logger.info(f"LLM response received: '{llm_response_text}'")
    
    return llm_response_text
