import asyncio
import httpx
import uuid

async def test_smart_search():
    session_id = str(uuid.uuid4())
    print(f"Testing Smart Search Broadcast with session: {session_id}")
    
    url = "http://localhost:5000/broadcast"
    
    # Notice there is NO /search command prefix here!
    payload = {
        "prompt": "What are the latest facts regarding Aravali degradation as of 2024?",
        "session_id": session_id,
        "models": [
            {
                "provider_id": "google",
                "model_id": "gemini-flash-latest",
                "temperature": 0.7,
                "max_tokens": 1000
            }
        ]
    }
    
    try:
        async with httpx.AsyncClient() as client:
            print(f"Sending prompt: '{payload['prompt']}'")
            print("The backend should automatically detect this needs internet and trigger a search.")
            response = await client.post(url, json=payload, timeout=30.0)
            
            if response.status_code == 200:
                print("Broadcast request successful!")
                print(response.json())
                print("\nPlease check the backend server logs. You should see:")
                print("1. 'Checking if prompt needs web search via Smart Router...'")
                print("2. 'Web Search triggered for: What are the latest facts...'")
                print("3. 'Web research injected into prompt...'")
            else:
                print(f"Broadcast request failed with status: {response.status_code}")
                print(response.text)
                
    except Exception as e:
        print(f"Error testing broadcast: {e}")

if __name__ == "__main__":
    asyncio.run(test_smart_search())
