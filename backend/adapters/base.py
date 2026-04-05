"""
Abstract base class for LLM adapters
Defines the interface that all provider adapters must implement
"""

from abc import ABC, abstractmethod
from typing import AsyncGenerator, List, Dict, Any, Optional
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Message, ModelInfo, StreamEvent
from error_handler import error_handler


class LLMAdapter(ABC):
    """
    Abstract base class for LLM provider adapters.
    
    All adapters must implement the stream() method for generating responses
    and get_models() method for model discovery.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the adapter with configuration.
        
        Args:
            config: Provider-specific configuration dictionary
        """
        self.config = config or {}
    
    @abstractmethod
    def stream(
        self, 
        messages: List[Message], 
        model: str,
        pane_id: str,
        **kwargs
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        Stream responses from the LLM provider.
        
        Args:
            messages: List of conversation messages
            model: Model identifier (e.g., "gpt-4", "claude-3-opus")
            pane_id: Unique identifier for the chat pane
            **kwargs: Additional model parameters (temperature, max_tokens, etc.)
            
        Yields:
            StreamEvent: Normalized events (token, final, meter, error, status)
        """
        pass
    
    @abstractmethod
    async def get_models(self) -> List[ModelInfo]:
        """
        Get available models for this provider.
        
        Returns:
            List[ModelInfo]: Available models with metadata
        """
        pass
    
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """
        Get the provider name identifier.
        
        Returns:
            str: Provider name (e.g., "openai", "anthropic", "google")
        """
        pass
    
    def format_model_id(self, model: str) -> str:
        """
        Format model ID with provider prefix.
        
        Args:
            model: Base model name
            
        Returns:
            str: Formatted model ID (provider:model)
        """
        return f"{self.provider_name}:{model}"
    
    async def validate_model(self, model: str) -> bool:
        """
        Validate if a model is available from this provider.
        
        Args:
            model: Model identifier to validate
            
        Returns:
            bool: True if model is available
        """
        available_models = await self.get_models()
        return any(m.id == model for m in available_models)
    
    async def stream_with_error_handling(
        self,
        messages: List[Message],
        model: str,
        pane_id: str,
        session_id: str,
        **kwargs
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        Stream with enhanced error handling and retry logic.
        
        Args:
            messages: List of conversation messages
            model: Model identifier
            pane_id: Unique identifier for the chat pane
            session_id: Session identifier for logging
            **kwargs: Additional model parameters
            
        Yields:
            StreamEvent: Normalized events with error handling
        """
        context = {
            "model": model,
            "message_count": len(messages),
            "kwargs": kwargs
        }
        
        error_handler._log_structured(
            "info",
            "Starting stream with error handling",
            session_id=session_id,
            pane_id=pane_id,
            provider=self.provider_name,
            **context
        )
        
        try:
            # Stream directly with error handling in the adapters
            async for event in self.stream(messages, model, pane_id, **kwargs):
                yield event
                
        except Exception as e:
            error_handler._log_structured(
                "error",
                "Stream failed in base adapter",
                session_id=session_id,
                pane_id=pane_id,
                provider=self.provider_name,
                error=str(e),
                error_type=type(e).__name__,
                **context
            )
            
            # Create and yield error event
            error_event = error_handler.create_error_event(e, pane_id, context=context)
            yield error_event