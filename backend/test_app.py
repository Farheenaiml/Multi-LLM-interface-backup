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

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from backend.broadcast_orchestrator import BroadcastOrchestrator
from backend.adapters.registry import registry
from backend.models import BroadcastRequest, ModelSelection, ChatPane, StreamEvent

class DummyCM:
    async def send_event(self, sid, event: StreamEvent):
        print(f"EVENT {event.type}: {event.data}")

async def test_full():
    orch = BroadcastOrchestrator(registry)
    cm = DummyCM()
    
    pdf_content = b"%PDF-1.0\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj 3 0 obj<</Type/Page/MediaBox[0 0 3 3]>>endobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000052 00000 n \n0000000101 00000 n \ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n147\n%%EOF\n"
    b64_pdf = base64.b64encode(pdf_content).decode()
    data_uri = f"data:application/pdf;base64,{b64_pdf}"
    
    # mock session and pane
    from backend.session_manager import session_manager
    session = session_manager.create_session("test_session_abc")
    
    # mock main.py hydration logic
    from backend.models import Message
    msg = Message(role="user", content="Read this", images=[data_uri])
    
    pane = ChatPane(
        id="pane_123",
        model_info=registry.get_adapter("groq")._get_fallback_models()[0], # Llama 3.1 8b
        messages=[msg]
    )
    session.panes.append(pane)
    session_manager.update_session(session)
    
    req = BroadcastRequest(
        session_id="test_session_abc",
        models=[ModelSelection(model_id="llama-3.1-8b-instant", provider_id="groq", persona_id="global")],
        message="Read this file",
        images=[data_uri],
        needs_web_search=False
    )
    
    await orch.broadcast(req, ["pane_123"], cm)

if __name__ == "__main__":
    asyncio.run(test_full())
