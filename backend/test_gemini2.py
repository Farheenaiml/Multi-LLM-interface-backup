import os
import asyncio
import httpx
from dotenv import load_dotenv

load_dotenv()

async def ping():
    k = os.getenv("GOOGLE_API_KEY")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={k}"
    payload = {"contents": [{"parts": [{"text": "hi"}]}]}
    try:
        r = httpx.post(url, json=payload, timeout=10.0)
        print("2.5 Result:", r.status_code, r.text)
    except Exception as e:
        print("2.5 Error:", e)

    url2 = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={k}"
    try:
        r = httpx.post(url2, json=payload, timeout=10.0)
        print("latest Result:", r.status_code, r.text)
    except Exception as e:
        print("latest Error:", e)

if __name__ == "__main__":
    asyncio.run(ping())
