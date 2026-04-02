import os
import asyncio
import httpx
from dotenv import load_dotenv

load_dotenv()

async def fetch_groq_models():
    groq_key = os.getenv('GROQ_API_KEY')
    if not groq_key:
        print('No Groq API Key')
        return
    async with httpx.AsyncClient() as client:
        resp = await client.get('https://api.groq.com/openai/v1/models', headers={'Authorization': f'Bearer {groq_key}'})
        data = resp.json()
        print('GROQ MODELS:')
        for m in data.get('data', []):
            if "id" in m:
                print(f"- {m['id']}")

async def fetch_google_models():
    google_key = os.getenv('GOOGLE_API_KEY')
    if not google_key:
        print('No Google API Key')
        return
    async with httpx.AsyncClient() as client:
        resp = await client.get(f'https://generativelanguage.googleapis.com/v1beta/models?key={google_key}')
        data = resp.json()
        print('\nGOOGLE MODELS:')
        for m in data.get('models', []):
            if 'generateContent' in m.get('supportedGenerationMethods', []):
                print(f"- {str(m.get('name', '')).replace('models/', '')}")

async def main():
    await fetch_groq_models()
    await fetch_google_models()

if __name__ == "__main__":
    asyncio.run(main())
