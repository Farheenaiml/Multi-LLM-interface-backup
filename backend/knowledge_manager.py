import json
import os
import asyncio
import logging
import re
from typing import List, Dict, Any
from models import Message

logger = logging.getLogger(__name__)

class KnowledgeManager:
    def __init__(self, file_path="knowledge_vault.json"):
        self.file_path = file_path
        self.facts: List[str] = self._load_facts()
        self._lock = asyncio.Lock()

    def _load_facts(self) -> List[str]:
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get("facts", [])
            except Exception as e:
                logger.error(f"Error loading knowledge vault: {e}")
                return []
        return []

    async def _save_facts(self):
        async with self._lock:
            try:
                with open(self.file_path, 'w', encoding='utf-8') as f:
                    json.dump({"facts": self.facts}, f, indent=2)
            except Exception as e:
                logger.error(f"Error saving knowledge vault: {e}")

    def get_knowledge_context(self) -> str:
        """Returns a formatted string of the Knowledge Vault for context injection."""
        if not self.facts:
            return ""
            
        context = (
            "[[SYSTEM METADATA: USER PROFILE REFERENCE]]\n"
            "Below is a JSON object containing established facts about the user. You may reference these facts ONLY if strictly necessary to answer the user's specific questions about themselves.\n"
            "DO NOT assume these traits for yourself. You are the AI Assistant. The user is the human described below.\n\n"
            "```json\n{\n"
            '  "user": {\n'
            '    "known_facts": [\n'
        )
        
        json_facts = []
        for fact in self.facts:
            # Clean up the facts
            safe_fact = fact.replace("User is ", "").replace("User has ", "").replace("User ", "").strip()
            # Double escape quotes
            safe_fact = safe_fact.replace('"', '\\"')
            json_facts.append(f'      "{safe_fact}"')
            
        context += ",\n".join(json_facts)
        context += (
            "\n    ]\n"
            "  }\n"
            "}\n```\n"
            "[[END SYSTEM METADATA]]\n"
        )
        return context

    async def extract_and_store_facts(self, messages: List[Message], registry) -> None:
        """
        Extracts permanent user facts from the most recent conversation turn and stores them.
        """
        if not messages or messages[-1].role != "user":
            return
            
        # Get the recent block of interaction
        recent_text = f"USER: {messages[-1].content}"
        if len(messages) > 1 and messages[-2].role == "assistant":
            recent_text = f"ASSISTANT: {messages[-2].content}\n" + recent_text

        prompt = (
            "You are a background Knowledge Extractor. Analyze the following conversational exchange "
            "and extract ONLY permanent, structured facts about the user (e.g., 'User's name is John', "
            "'User is building a React app', 'User prefers dark mode', 'User is planning a trip to Paris').\n"
            "DO NOT extract general questions, transient conversation topics, or AI instructions.\n"
            "Return a raw JSON list of strings (e.g. [\"Fact 1\", \"Fact 2\"]). If no new permanent facts are present, return an empty list [].\n"
            "DO NOT wrap your response in markdown code blocks like ```json. Just return the raw JSON array.\n\n"
            f"EXCHANGE:\n{recent_text}"
        )

        try:
            # Prefer groq Llama 3 for fast extraction, fallback to gemini flash
            adapter = registry.get_adapter("groq")
            model_id = "llama-3.1-8b-instant"
            if not adapter:
                adapter = registry.get_adapter("google")
                model_id = "gemini-flash-latest"
                
            if not adapter:
                # No fast provider configured, use whatever is available
                available_providers = registry.list_providers()
                if available_providers:
                    provider_id = available_providers[0]
                    adapter = registry.get_adapter(provider_id)
                    model_id = "litellm:gpt-3.5-turbo" if provider_id == "litellm" else "llama-3.1-8b-instant"
                else:
                    return # No adapter available for summarization
                
            summary_messages = [Message(role="user", content=prompt)]
            output = ""
            
            # Run stream fully
            async for event in adapter.stream(summary_messages, model_id, "extractor", temperature=0.1, max_tokens=300):
                if event.type == "token":
                    output += event.data.token
                elif event.type == "final":
                    output = event.data.content
                    break
                    
            # Parse the JSON array
            match = re.search(r'\[.*\]', output, re.DOTALL)
            if match:
                new_facts = json.loads(match.group(0))
                if new_facts and isinstance(new_facts, list):
                    added_any = False
                    for fact in new_facts:
                        # Avoid exact duplicates or trivial lists
                        if isinstance(fact, str) and fact not in self.facts and len(fact) > 5:
                            self.facts.append(fact)
                            added_any = True
                    
                    if added_any:
                        await self._save_facts()
                        logger.info(f"🧠 Knowledge Vault updated with new facts! Current fact count: {len(self.facts)}")
        except Exception as e:
            logger.warning(f"Fact extraction failed: {e}")

# Global singleton
knowledge_manager = KnowledgeManager()
