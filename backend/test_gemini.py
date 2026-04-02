import os
import asyncio
import httpx
from dotenv import load_dotenv

load_dotenv()

async def ping():
    k = os.getenv("GOOGLE_API_KEY")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={k}"
    payload = {"contents": [{"parts": [{"text": "hi"}]}]}
    r = httpx.post(url, json=payload)
    print(r.status_code, r.text)

if __name__ == "__main__":
    asyncio.run(ping())
