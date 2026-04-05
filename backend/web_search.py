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
    Uses Groq or Gemini as a fast router to determine if the prompt requires a web search.
    
    Args:
        prompt (str): The user's input prompt.
        
    Returns:
        bool: True if the prompt requires live internet data, False otherwise.
    """
    import json
    from adapters.registry import registry
    from models import Message
    
    system_instruction = (
        "You are an intent classifier. Determine if the user's prompt strongly requires live, recent, or specifically obscure data from the internet.\n"
        "Return EXACTLY 'true' if the prompt contains words like 'news', 'latest', 'today', 'current', 'recent', or asks for highly current events.\n"
        "Return EXACTLY 'false' if it is a general coding question, greeting, translation, creative writing, dictionary definition (like 'what is velocity'), or relies entirely on general or encyclopedic knowledge."
    )
    
    messages = [
        Message(role="system", content=system_instruction),
        Message(role="user", content=prompt)
    ]
    
    async def try_router(current_adapter, current_model_id):
        if not current_adapter:
            return None
        output = ""
        try:
            async for event in current_adapter.stream(messages, current_model_id, "router_pane", temperature=0.0, max_tokens=20):
                if event.type == "token":
                    output += event.data.token
                elif event.type == "final":
                    output = event.data.content
                    break
                elif event.type == "error":
                    raise Exception(event.data.message)
            return output
        except Exception as e:
            print(f"Smart router try_router failed with {current_model_id}: {e}")
            return None
            
    # Try Groq first for speed
    output = await try_router(registry.get_adapter("groq"), "llama-3.1-8b-instant")
    
    if output is None:
        # Fallback to Google
        print("Smart router falling back to Google adapter...")
        output = await try_router(registry.get_adapter("google"), "gemini-flash-latest")
        
    if output and "true" in output.lower():
        return True
    return False
