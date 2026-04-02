import asyncio
import os
import base64
from dotenv import load_dotenv
import sys
import io
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
except Exception:
    pass

# Ensure dotenv loads from the correct path
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from backend.adapters.registry import AdapterRegistry
from backend.models import Message

async def test_vision_bridge():
    registry = AdapterRegistry()
    google_adapter = registry.get_adapter("google")
    print(f"Got API key? {bool(google_adapter.api_key)}")
    
    # Very small inline PDF
    pdf_content = b"%PDF-1.0\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj 3 0 obj<</Type/Page/MediaBox[0 0 3 3]>>endobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000052 00000 n \n0000000101 00000 n \ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n147\n%%EOF\n"
    b64_pdf = base64.b64encode(pdf_content).decode()
    data_uri = f"data:application/pdf;base64,{b64_pdf}"
    
    vision_messages = [
        Message(
            role="user",
            content="Describe this document.",
            images=[data_uri]
        )
    ]
    
    try:
        print("Streaming...")
        async for event in google_adapter.stream(vision_messages, "gemini-2.5-flash", "temp"):
            if event.type == "error":
                print(f"ERROR: {event.data.message}")
            elif event.type == "token":
                print(event.data.token, end="")
            elif event.type == "final":
                print("\nFINAL:", event.data.content)
    except Exception as e:
        print(f"EXCEPTION: {e}")

if __name__ == "__main__":
    asyncio.run(test_vision_bridge())
