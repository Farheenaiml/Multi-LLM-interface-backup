import asyncio
import os
import json
from unittest.mock import Mock

from models import Message, StreamEvent, FinalData
from knowledge_manager import KnowledgeManager

async def test_knowledge_extraction_and_injection():
    print("Starting Knowledge Vault Test...")
    
    # 1. Setup temporary knowledge manager
    test_file = "test_knowledge_vault.json"
    if os.path.exists(test_file):
        os.remove(test_file)
        
    km = KnowledgeManager(file_path=test_file)
    
    # 2. Setup mock registry and adapter
    mock_registry = Mock()
    mock_adapter = Mock()
    mock_registry.get_adapter.return_value = mock_adapter
    
    # Mock adapter stream to return a JSON array
    async def mock_stream(*args, **kwargs):
        test_knowledge_extraction_and_injection.prompt_sent = args[0]
        yield StreamEvent(
            type="final",
            pane_id="extractor",
            data=FinalData(content='["User loves pizza", "User is building an AI called Antigravity"]', finish_reason="stop")
        )
    mock_adapter.stream = mock_stream
    
    # 3. Simulate an extraction process
    messages = [
        Message(role="user", content="I really love pizza and I am currently building an AI named Antigravity.")
    ]
    
    print("Triggering fact extraction...")
    await km.extract_and_store_facts(messages, mock_registry)
    
    # Assert facts were extracted and saved
    assert len(km.facts) == 2, f"Expected 2 facts, got {len(km.facts)}"
    assert "User loves pizza" in km.facts
    
    # Assert JSON file was written
    assert os.path.exists(test_file), "Vault JSON file was not created"
    
    # 4. Verify context injection formatting
    context = km.get_knowledge_context()
    print("===== GENERATED CONTEXT =====")
    print(context)
    print("=============================")
    
    assert "User is building" in context
    assert "SYSTEM DIRECTIVE: GLOBAL KNOWLEDGE VAULT" in context
    
    print("Knowledge Vault test passed completely!")
    
    # Cleanup
    if os.path.exists(test_file):
        os.remove(test_file)

if __name__ == "__main__":
    asyncio.run(test_knowledge_extraction_and_injection())
