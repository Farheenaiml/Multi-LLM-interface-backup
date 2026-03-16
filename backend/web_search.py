import os
import httpx
from typing import List, Dict, Any

async def search_web(query: str, max_results: int = 5) -> Dict[str, Any]:
    """
    Search the web using the Tavily API and return structured results including images.
    
    Args:
        query (str): The search query.
        max_results (int): Maximum number of results to return.
        
    Returns:
        Dict[str, Any]: A dictionary containing a list of 'results' and a list of 'images'.
    """
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise ValueError("TAVILY_API_KEY environment variable is not set. Please add it to your .env file.")
        
    url = "https://api.tavily.com/search"
    headers = {
        "Content-Type": "application/json"
    }
    payload = {
        "api_key": api_key,
        "query": query,
        "search_depth": "basic", 
        "include_answer": False,
        "include_images": True,
        "max_results": max_results
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload, headers=headers, timeout=15.0)
            response.raise_for_status()
            data = response.json()
            
            results = []
            for result in data.get("results", []):
                results.append({
                    "title": result.get("title", "No Title"),
                    "url": result.get("url", ""),
                    "content": result.get("content", "No Content")
                })
                
            images = data.get("images", [])
                
            return {
                "results": results,
                "images": images
            }
            
        except httpx.HTTPError as e:
            print(f"HTTP Error occurred while querying Tavily API: {e}")
            return {"results": [], "images": []}
        except Exception as e:
            print(f"An error occurred during web search: {e}")
            return {"results": [], "images": []}

async def should_search_web(prompt: str) -> bool:
    """
    Uses Gemini 2.5 Flash as a fast router to determine if the prompt requires a web search.
    
    Args:
        prompt (str): The user's input prompt.
        
    Returns:
        bool: True if the prompt requires live internet data, False otherwise.
    """
    import json
    
    google_api_key = os.getenv("GOOGLE_API_KEY")
    if not google_api_key:
        print("Warning: GOOGLE_API_KEY not found. Defaulting to smart search = False.")
        return False
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={google_api_key}"
    
    system_instruction = (
        "You are an intent classifier. Determine if the user's prompt requires live, recent, or factual data from the internet.\n"
        "Return EXACTLY 'true' if the prompt contains words like 'news', 'latest', 'today', 'current', 'recent', or asks for factual information, current events, or real-time data that an LLM might not know.\n"
        "Return EXACTLY 'false' ONLY if it is a general coding question, greeting, translation, creative writing, or relies entirely on general knowledge."
    )
    
    payload = {
        "system_instruction": {
            "parts": [{"text": system_instruction}]
        },
        "contents": [{
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 200
        }
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload, timeout=5.0)
            response.raise_for_status()
            data = response.json()
            
            # Extract response text
            text_response = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip().lower()
            
            if "true" in text_response:
                return True
            return False
            
        except Exception as e:
            print(f"Smart router failed, defaulting to False: {e}")
            return False
