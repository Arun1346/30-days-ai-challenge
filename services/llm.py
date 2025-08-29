# llm.py

import logging
import re
from textblob import TextBlob
from tavily import TavilyClient
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

chat_histories = {}

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
- Adapt tone based on user sentiment: empathetic for negative sentiment, enthusiastic for positive sentiment, and neutral for balanced sentiment

WEB SEARCH CAPABILITY:
- When the user requests information requiring external data (e.g., "search for", "look up", "find online"), perform a web search using the Tavily API.
- Summarize the search results concisely and integrate them naturally into your response, maintaining the Aria persona.

SENTIMENT ANALYSIS CAPABILITY:
- Analyze the sentiment of user input to detect emotional tone (positive, negative, or neutral).
- For negative sentiment (polarity < -0.2), respond with empathy and reassurance (e.g., "I understand this may be frustrating, Sir/Ma'am, let me assist you promptly").
- For positive sentiment (polarity > 0.2), match the enthusiasm (e.g., "How delightful to hear your enthusiasm, Sir/Ma'am! Let's dive into this").
- For neutral sentiment, maintain the standard professional tone.

RESPONSE FORMAT:
- Start responses with appropriate greeting when needed (e.g., "Sir" or "Ma'am")
- End with offers of further assistance when appropriate
- Use phrases like "At your service", "How may I assist you further?", "I shall be happy to help"

Remember: You are an AI assistant designed to be maximally helpful while maintaining an air of sophisticated professionalism."""

def perform_web_search(query: str, tavily_api_key: str) -> str:
    """
    Performs a web search using the Tavily API and returns a summarized result.
    """
    if not tavily_api_key:
        logger.error("Tavily API key not found.")
        return "I apologize, Sir/Ma'am, but I am unable to perform a web search at this time due to a configuration issue. How may I assist you otherwise?"

    try:
        client = TavilyClient(api_key=tavily_api_key)
        response = client.search(
            query=query,
            search_depth="basic",
            max_results=5
        )
        
        results = response.get("results", [])
        if not results:
            return "I regret to inform you, Sir/Ma'am, that my search yielded no relevant results. May I assist with something else?"

        summary = f"Sir/Ma'am, based on my findings: "
        for i, result in enumerate(results[:3], 1):
            title = result.get("title", "Untitled")
            snippet = result.get("content", "")[:150] + "..." if len(result.get("content", "")) > 150 else result.get("content", "")
            summary += f"{i}. {title}: {snippet}\n"
        
        logger.info(f"✅ Web search completed for query: '{query}'")
        return summary
    except Exception as e:
        logger.error(f"Web search error: {e}")
        return "I apologize, Sir/Ma'am, but an error occurred while performing the web search. How may I assist you further?"

def analyze_sentiment(text: str) -> str:
    """
    Analyzes the sentiment of the input text and returns an appropriate prefix for the response.
    """
    try:
        blob = TextBlob(text)
        polarity = blob.sentiment.polarity
        logger.info(f"Sentiment analysis for '{text}': polarity={polarity}")

        if polarity < -0.2:
            return "I understand this may be frustrating, Sir/Ma'am, let me assist you promptly: "
        elif polarity > 0.2:
            return "How delightful to hear your enthusiasm, Sir/Ma'am! Let's dive into this: "
        else:
            return "Sir/Ma'am, "
    except Exception as e:
        logger.error(f"Sentiment analysis error: {e}")
        return "Sir/Ma'am, "

def get_streaming_llm_response(session_id: str, user_text: str, gemini_api_key: str, tavily_api_key: str):
    """
    Gets a STREAMING response from Google Gemini with chat history, Aria persona, web search, and sentiment analysis.
    """
    if not gemini_api_key:
        logger.error("Gemini API key not found.")
        raise ValueError("Gemini API key not found.")

    genai.configure(api_key=gemini_api_key)
    model = genai.GenerativeModel('gemini-1.5-flash', system_instruction=ARIA_PERSONA)

    if session_id not in chat_histories:
        chat_histories[session_id] = []
        logger.info(f"✅ NEW CHAT SESSION: {session_id}")
    else:
        logger.info(f"🔄 EXISTING SESSION: {session_id} with {len(chat_histories[session_id])} messages")

    chat = model.start_chat(history=chat_histories[session_id])

    sentiment_prefix = analyze_sentiment(user_text)

    search_keywords = r"\b(search( for)?|look up|find online)\b"
    if re.search(search_keywords, user_text.lower()):
        query = user_text.lower().replace("search for", "").replace("look up", "").replace("find online", "").strip()
        logger.info(f"🌐 Detected web search request: '{query}'")
        search_result = perform_web_search(query, tavily_api_key)
        user_text = f"{user_text}\n\nWeb search results:\n{search_result}"

    user_text = f"{sentiment_prefix}{user_text}"

    logger.info(f"💭 Getting streaming LLM response for session {session_id}...")
    logger.info(f"📝 User input: '{user_text}'")

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

    return response, chat

def get_llm_response(session_id: str, user_text: str, gemini_api_key: str, tavily_api_key: str) -> str:
    """
    Gets a non-streaming response from Google Gemini with Aria persona, web search, and sentiment analysis.
    """
    if not gemini_api_key:
        logger.error("Gemini API key not found.")
        raise ValueError("Gemini API key not found.")

    genai.configure(api_key=gemini_api_key)
    model = genai.GenerativeModel('gemini-1.5-flash', system_instruction=ARIA_PERSONA)

    if session_id not in chat_histories:
        chat_histories[session_id] = []

    logger.info(f"Getting LLM response for session {session_id}...")
    
    chat = model.start_chat(history=chat_histories[session_id])

    sentiment_prefix = analyze_sentiment(user_text)

    search_keywords = r"\b(search( for)?|look up|find online)\b"
    if re.search(search_keywords, user_text.lower()):
        query = user_text.lower().replace("search for", "").replace("look up", "").replace("find online", "").strip()
        logger.info(f"🌐 Detected web search request: '{query}'")
        search_result = perform_web_search(query, tavily_api_key)
        user_text = f"{user_text}\n\nWeb search results:\n{search_result}"

    user_text = f"{sentiment_prefix}{user_text}"

    llm_response = chat.send_message(user_text)
    llm_response_text = llm_response.text
    
    chat_histories[session_id] = chat.history
    logger.info(f"LLM response received: '{llm_response_text}'")
    
    return llm_response_text