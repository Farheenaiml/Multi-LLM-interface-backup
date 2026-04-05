import asyncio
import os
import sys
import io

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
except Exception:
    pass

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from backend.broadcast_orchestrator import BroadcastOrchestrator
from backend.adapters.registry import registry
from backend.models import BroadcastRequest, ModelSelection, ChatPane, StreamEvent

class DummyCM:
    async def send_event(self, sid, event: StreamEvent):
        if event.type == "token":
            print(event.data.token, end="")
        elif event.type == "final":
            print("\n")

async def test_fresh_chat():
    from backend.session_manager import SessionManager
    import backend.knowledge_manager as km
    km.knowledge_manager.file_path = os.path.join(os.path.dirname(__file__), "knowledge_vault.json")
    km.knowledge_manager.facts = km.knowledge_manager._load_facts()
    print(f"Loaded {len(km.knowledge_manager.facts)} facts for testing...")
    
    session_manager = SessionManager()
    orch = BroadcastOrchestrator(registry, session_manager)
    cm = DummyCM()
    
    session = session_manager.create_session("test_session_fresh")
    
    # We DO NOT mock any previous chat history. Completely fresh pane!
    from backend.models import Message
    msg1 = Message(role="user", content="tell me about yourself")
    msg2 = Message(role="assistant", content="I am a generic AI assistant. I do not have a specific persona.")
    msg3 = Message(role="user", content="hi")
    
    pane = ChatPane(
        id="pane_fresh_123",
        model_info={ "id": "llama-3.1-8b-instant", "name": "Llama", "provider": "groq", "max_tokens": 1000, "cost_per_1k_tokens": 0.0 }, # Llama
        messages=[msg1, msg2, msg3]
    )
    session.panes.append(pane)
    session_manager.update_session(session)
    
    # Simulating Global Persona (system_prompt = undefined -> None)
    req = BroadcastRequest(
        session_id="test_session_fresh",
        models=[ModelSelection(model_id="llama-3.1-8b-instant", provider_id="groq")],
        prompt="hi",
        system_prompt="You are an Exam Tutor. Answer ONLY as an Exam Tutor preparing students. Start your response with 'Tutor:'"
    )
    
    print("Running broadcast...")
    await orch.broadcast(req, ["pane_fresh_123"], cm)
    
    # After broadcast, let's see what the actual session messages were!
    final_session = session_manager.get_session("test_session_fresh")
    for pane in final_session.panes:
        if pane.id == "pane_fresh_123":
            print("\n----- FINAL PROMPT SENT -----")
            for m in pane.messages:
                print(f"ROLE {m.role.upper()}: {m.content}")
            print("-----------------------------\n")

    print("\nDone.")

if __name__ == "__main__":
    asyncio.run(test_fresh_chat())
