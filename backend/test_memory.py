import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

from models import Message, Session, ChatPane, ModelInfo, BroadcastRequest, ModelSelection, StreamEvent, FinalData
from broadcast_orchestrator import BroadcastOrchestrator
from session_manager import SessionManager


async def test_long_term_memory_compression():
    print("Starting Long-Term Memory Compression Test...")
    
    # 1. Setup mocks
    mock_registry = Mock()
    mock_adapter = Mock()
    mock_registry.get_adapter.return_value = mock_adapter
    mock_registry.get_model_info = AsyncMock(return_value=ModelInfo(
        id="test:model",
        name="Test Model",
        provider="test",
        max_tokens=1000,
        cost_per_1k_tokens=0.1
    ))
    
    # Mock adapter.stream to just return a single final event
    async def mock_stream(*args, **kwargs):
        # We want to capture the messages passed to the adapter
        test_long_term_memory_compression.captured_messages = args[0]
        yield StreamEvent(
            type="final",
            pane_id="test_pane",
            data=FinalData(content="Test response", finish_reason="stop")
        )
    mock_adapter.stream = mock_stream
    
    session_manager = SessionManager()
    orchestrator = BroadcastOrchestrator(mock_registry, session_manager)
    
    # Also mock _summarize_messages so we don't make real API calls in the test
    async def mock_summarize(*args, **kwargs):
        return "This is a mocked summary of older messages."
    orchestrator._summarize_messages = mock_summarize
    
    # 2. Create a session with 15 messages
    session = session_manager.create_session("test_session")
    model_info = ModelInfo(
        id="test:model",
        name="Test Model",
        provider="test",
        max_tokens=1000,
        cost_per_1k_tokens=0.1
    )
    pane = ChatPane(id="test_pane", model_info=model_info)
    session_manager.add_pane_to_session("test_session", pane)
    
    # Add 15 messages to the pane
    for i in range(15):
        msg = Message(role="user" if i % 2 == 0 else "assistant", content=f"Message {i+1}")
        session_manager.add_message_to_pane("test_session", "test_pane", msg)
        
    print(f"Added {len(pane.messages)} messages to pane.")
    
    # 3. Create a broadcast request
    request = BroadcastRequest(
        prompt="Message 16",
        session_id="test_session",
        models=[ModelSelection(provider_id="test", model_id="model")]
    )
    
    mock_connection_manager = Mock()
    mock_connection_manager.send_event = AsyncMock()
    
    # 4. Run the stream (we call _stream_to_pane directly for easier testing)
    print("Triggering stream to pane...")
    await orchestrator._stream_to_pane(
        request, 
        request.models[0], 
        "test_pane", 
        mock_connection_manager
    )
    
    # 5. Assertions
    captured = getattr(test_long_term_memory_compression, "captured_messages", None)
    assert captured is not None, "Adapter stream was not called"
    
    # Should be 1 summary message + 10 recent messages = 11 messages total
    print(f"Adapter received {len(captured)} messages.")
    assert len(captured) == 11, f"Expected 11 messages, got {len(captured)}"
    
    # First message should be the system summary
    assert captured[0].role == "system", "First message should be the system summary"
    assert "LONG-TERM MEMORY SUMMARY" in captured[0].content, "Summary message missing header"
    assert "mocked summary" in captured[0].content, "Mocked summary content missing"
    
    # The last message should be "Message 15"
    assert captured[-1].content == "Message 15", f"Last message should be 'Message 15', got '{captured[-1].content}'"
    
    print("Test passed! Long-Term Memory compression is working correctly.")

if __name__ == "__main__":
    asyncio.run(test_long_term_memory_compression())
