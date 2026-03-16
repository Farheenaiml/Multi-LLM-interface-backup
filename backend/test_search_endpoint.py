import asyncio
import httpx
import uuid

async def test_search_broadcast():
    session_id = str(uuid.uuid4())
    print(f"Testing Broadcast with session: {session_id}")
    
    url = "http://localhost:5000/broadcast"
    
    payload = {
        "prompt": "/search What is FastAPI?",
        "session_id": session_id,
        "models": [
            {
                "provider_id": "google",
                "model_id": "gemini-2.5-flash",
                "temperature": 0.7,
                "max_tokens": 1000
            }
        ]
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, timeout=30.0)
            
            if response.status_code == 200:
                print("Broadcast request successful!")
                print(response.json())
                print("\nPlease check the backend server logs to verify that the web search was triggered and the context was injected into the prompt before being sent to Gemini.")
            else:
                print(f"Broadcast request failed with status: {response.status_code}")
                print(response.text)
                
    except Exception as e:
        print(f"Error testing broadcast: {e}")

if __name__ == "__main__":
    asyncio.run(test_search_broadcast())
