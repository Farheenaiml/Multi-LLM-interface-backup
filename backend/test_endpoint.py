import httpx
import asyncio

async def main():
    try:
        async with httpx.AsyncClient() as client:
            payload = {
                "session_id": "test_session",
                "prompt": "Hello",
                "models": [{"provider_id": "google", "model_id": "gemini-2.5-flash", "temperature": 0.7, "max_tokens": 1000}]
            }
            response = await client.post("http://localhost:5001/broadcast", json=payload, timeout=5)
            print(f"Status Code: {response.status_code}")
            print(f"Response: {response.text}")
    except Exception as e:
        print(f"Failed to connect: {e}")

asyncio.run(main())
