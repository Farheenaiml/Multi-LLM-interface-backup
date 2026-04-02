import asyncio
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

async def test_vision():
    google_key = os.getenv("GOOGLE_API_KEY")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:streamGenerateContent?key={google_key}"
    
    # We will simulate the payload google_adapter sends for PDF
    # We will just send a very tiny dummy Base64 PDF to see if it even accepts it
    dummy_pdf_base64 = "JVBERi0xLgoxIDAgb2JqPDwvUGFnZXMgMiAwIFI+PmVuZG9iagoyIDAgb2JqPDwvS2lkc1tdL0NvdW50IDA+PmVuZG9iagp0cmFpbGVyPDwvUm9vdCAxIDAgUj4+Cg=="
    
    payload = {
        "contents": [{
            "role": "user",
            "parts": [
                {"text": "What is in this PDF?"},
                {
                    "inlineData": {
                        "mimeType": "application/pdf",
                        "data": dummy_pdf_base64
                    }
                }
            ]
        }],
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 200,
            "candidateCount": 1
        }
    }
    
    async with httpx.AsyncClient() as client:
        print("Sending request...")
        response = await client.post(url, json=payload)
        print(f"Status: {response.status_code}")
        print(f"Body: {response.text}")

if __name__ == "__main__":
    asyncio.run(test_vision())
