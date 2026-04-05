"""
LiteLLM Adapter for unified provider access
Connects to LiteLLM service running on Docker for multi-provider support
"""

import json
import httpx
from datetime import datetime
from typing import AsyncGenerator, List, Dict, Any, Optional

from .base import LLMAdapter
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Message, ModelInfo, StreamEvent, TokenData, FinalData, MeterData, ErrorData, StatusData
from error_handler import error_handler


class LiteLLMAdapter(LLMAdapter):
    """
    Adapter for LiteLLM service providing unified access to multiple providers.
    
    LiteLLM service handles provider abstraction and normalization,
    running on Docker at the configured base URL.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.base_url = self.config.get("base_url", "http://localhost:8000")
        self.master_key = self.config.get("master_key", "sk-1234")
        # Enhanced timeout configuration
        timeout_config = httpx.Timeout(
            connect=30.0,  # Connection timeout
            read=180.0,    # Read timeout for streaming
            write=120.0,   # Write timeout
            pool=10.0      # Pool timeout
        )
        self.client = httpx.AsyncClient(timeout=timeout_config)
    
    @property
    def provider_name(self) -> str:
        return "litellm"
    
    async def stream(
        self, 
        messages: List[Message], 
        model: str,
        pane_id: str,
        **kwargs
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        Stream responses through LiteLLM service.
        
        LiteLLM normalizes responses from different providers into a consistent format.
        """
        try:
            # Emit status event
            yield StreamEvent(
                type="status",
                pane_id=pane_id,
                data=StatusData(status="connecting", message=f"Connecting to {model}")
            )
            
            error_handler._log_structured(
                "info",
                "Starting LiteLLM stream",
                pane_id=pane_id,
                model=model,
                base_url=self.base_url,
                message_count=len(messages)
            )
            
            # Convert messages to LiteLLM format
            formatted_messages = [
                {"role": msg.role, "content": msg.content}
                for msg in messages
            ]
            
            # Prepare request payload
            payload = {
                "model": model,
                "messages": formatted_messages,
                "stream": True,
                "temperature": kwargs.get("temperature", 0.7),
                "max_tokens": kwargs.get("max_tokens", 1000)
            }
            
            headers = {
                "Authorization": f"Bearer {self.master_key}",
                "Content-Type": "application/json"
            }
            
            start_time = datetime.now()
            token_count = 0
            
            # Stream request to LiteLLM
            async with self.client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers
            ) as response:
                
                if response.status_code != 200:
                    error_text = await response.aread()
                    
                    error_handler._log_structured(
                        "error",
                        f"LiteLLM API error: {response.status_code}",
                        pane_id=pane_id,
                        model=model,
                        status_code=response.status_code,
                        error_text=error_text.decode()[:500]  # Truncate error text
                    )
                    
                    # Create appropriate error based on status code
                    error_type = error_handler.classify_error(Exception(error_text.decode()), response.status_code)
                    
                    yield StreamEvent(
                        type="error",
                        pane_id=pane_id,
                        data=ErrorData(
                            message=f"LiteLLM API error: {response.status_code}",
                            code=error_type.value,
                            retryable=response.status_code >= 500 or response.status_code == 429
                        )
                    )
                    return
                
                full_content = ""
                
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    
                    if line.startswith("data: "):
                        data_str = line[6:]  # Remove "data: " prefix
                        
                        if data_str.strip() == "[DONE]":
                            break
                        
                        try:
                            data = json.loads(data_str)
                            
                            if "choices" in data and len(data["choices"]) > 0:
                                choice = data["choices"][0]
                                
                                if "delta" in choice and "content" in choice["delta"]:
                                    token = choice["delta"]["content"]
                                    if token:
                                        full_content += token
                                        token_count += 1
                                        
                                        yield StreamEvent(
                                            type="token",
                                            pane_id=pane_id,
                                            data=TokenData(token=token, position=token_count)
                                        )
                                
                                # Check for finish reason
                                if "finish_reason" in choice and choice["finish_reason"]:
                                    end_time = datetime.now()
                                    latency = int((end_time - start_time).total_seconds() * 1000)
                                    
                                    # Emit final content
                                    yield StreamEvent(
                                        type="final",
                                        pane_id=pane_id,
                                        data=FinalData(
                                            content=full_content,
                                            finish_reason=choice["finish_reason"]
                                        )
                                    )
                                    
                                    # Emit metrics
                                    estimated_cost = self._estimate_cost(model, token_count)
                                    yield StreamEvent(
                                        type="meter",
                                        pane_id=pane_id,
                                        data=MeterData(
                                            tokens_used=token_count,
                                            cost=estimated_cost,
                                            latency=latency
                                        )
                                    )
                        
                        except json.JSONDecodeError:
                            continue  # Skip malformed JSON
                
        except httpx.TimeoutException as e:
            error_handler._log_structured(
                "warning",
                "LiteLLM request timeout",
                pane_id=pane_id,
                model=model,
                timeout_type=type(e).__name__
            )
            
            yield StreamEvent(
                type="error",
                pane_id=pane_id,
                data=ErrorData(
                    message="Request timeout - please try again",
                    code="timeout",
                    retryable=True
                )
            )
        except httpx.ConnectError as e:
            error_handler._log_structured(
                "error",
                "LiteLLM connection error",
                pane_id=pane_id,
                model=model,
                error=str(e)
            )
            
            yield StreamEvent(
                type="error",
                pane_id=pane_id,
                data=ErrorData(
                    message="Unable to connect to LiteLLM service",
                    code="network_error",
                    retryable=True
                )
            )
        except Exception as e:
            error_handler._log_structured(
                "error",
                "Unexpected LiteLLM error",
                pane_id=pane_id,
                model=model,
                error=str(e),
                error_type=type(e).__name__
            )
            
            yield StreamEvent(
                type="error",
                pane_id=pane_id,
                data=ErrorData(
                    message=f"Unexpected error: {str(e)}",
                    code="unknown",
                    retryable=False
                )
            )
    
    async def get_models(self) -> List[ModelInfo]:
        """
        Get available models from LiteLLM service.
        """
        try:
            headers = {"Authorization": f"Bearer {self.master_key}"}
            response = await self.client.get(f"{self.base_url}/models", headers=headers)
            
            if response.status_code != 200:
                return []
            
            data = response.json()
            models = []
            
            for model_data in data.get("data", []):
                model_id = model_data.get("id", "")
                
                # Extract provider from model ID if available
                provider = "unknown"
                if "/" in model_id:
                    provider = model_id.split("/")[0]
                
                # Generate a proper display name from the model ID
                display_name = self._generate_display_name(model_id)
                
                models.append(ModelInfo(
                    id=model_id,
                    name=display_name,
                    provider=provider,
                    max_tokens=self._get_max_tokens(model_id),
                    cost_per_1k_tokens=self._get_cost_per_1k(model_id),
                    supports_streaming=True
                ))
            
            return models
            
        except Exception:
            return []  # Return empty list on error
    
    def _estimate_cost(self, model: str, tokens: int) -> float:
        """
        Estimate cost based on model and token count.
        """
        # Basic cost estimation - should be enhanced with actual pricing
        cost_per_1k = self._get_cost_per_1k(model)
        return (tokens / 1000.0) * cost_per_1k
    
    def _get_cost_per_1k(self, model: str) -> float:
        """
        Get cost per 1K tokens for a model.
        """
        # Cost mapping based on actual models in litellm_config.yaml
        cost_map = {
            # Google Gemma Models (free/very low cost)
            "gemma-3n-e2b-it": 0.0,
            "gemma-3n-e4b-it": 0.0,
            "gemma-3-1b-it": 0.0,
            "gemma-3-4b-it": 0.0,
            "gemma-3-12b-it": 0.0,
            "gemma-3-27b-it": 0.0,
            
            # Google Gemini Models (current pricing)
            "gemini-2.5-pro": 1.25,  # Input cost per 1K tokens
            "gemini-flash-latest": 0.30,
            "gemini-flash-lite-latest": 0.10,
            "gemini-2.5-flash-lite": 0.10,
            "gemini-2.0-flash": 0.10,
            "gemini-2.0-flash-lite": 0.075,
            "learnlm-2.0-flash-experimental": 0.10,
            
            # Groq Models (very fast, low cost)
            "llama-3.1-8b-instant": 0.05,
            "llama-3.3-70b-versatile": 0.59,
            "compound": 0.10,
            "compound-mini": 0.05,
            
            # Legacy models
            "gpt-4": 30.0,
            "gpt-3.5-turbo": 2.0,
            "claude-3-opus": 15.0,
            "claude-3-sonnet": 3.0,
            "gemini-pro": 1.0,
            "gemini-1.5-pro": 1.25,
            "gemini-1.5-flash": 0.075,
            "llama-3.1-70b": 0.8,
            "llama-3.1-8b": 0.1,
            "mixtral-8x7b": 0.7,
            "gemma-7b": 0.1
        }
        
        # Extract base model name
        base_model = model.split("/")[-1] if "/" in model else model
        return cost_map.get(base_model, 0.001)  # Default cost
    
    def _generate_display_name(self, model_id: str) -> str:
        """
        Generate a human-readable display name from model ID.
        """
        # Extract the actual model name from the ID
        if "/" in model_id:
            model_name = model_id.split("/")[-1]
        else:
            model_name = model_id
        
        # Clean up and format the name based on actual litellm_config.yaml models
        name_map = {
            # Google Gemma Models
            "gemma-3n-e2b-it": "Gemma 3n E2B IT",
            "gemma-3n-e4b-it": "Gemma 3n E4B IT",
            "gemma-3-1b-it": "Gemma 3 1B IT",
            "gemma-3-4b-it": "Gemma 3 4B IT", 
            "gemma-3-12b-it": "Gemma 3 12B IT",
            "gemma-3-27b-it": "Gemma 3 27B IT",
            
            # Google Gemini Models
            "gemini-2.5-pro": "Gemini 2.5 Pro",
            "gemini-flash-latest": "Gemini Flash Latest",
            "gemini-flash-lite-latest": "Gemini Flash Lite Latest",
            "gemini-2.5-flash-lite": "Gemini 2.5 Flash Lite",
            "gemini-2.0-flash": "Gemini 2.0 Flash",
            "gemini-2.0-flash-lite": "Gemini 2.0 Flash Lite",
            "learnlm-2.0-flash-experimental": "LearnLM 2.0 Flash Experimental",
            
            # Groq Models
            "llama-3.1-8b-instant": "Llama 3.1 8B Instant",
            "llama-3.3-70b-versatile": "Llama 3.3 70B Versatile",
            "compound": "Compound",
            "compound-mini": "Compound Mini",
            
            # Alibaba Cloud Models via Groq
            "qwen3-32b": "Qwen 3 32B",
            
            # OpenAI Models via Groq
            "gpt-oss-120b": "GPT OSS 120B",
            "gpt-oss-20b": "GPT OSS 20B",
            "gpt-oss-safeguard-20b": "GPT OSS Safeguard 20B",
            
            # Whisper Models via Groq
            "whisper-large-v3": "Whisper Large V3",
            "whisper-large-v3-turbo": "Whisper Large V3 Turbo",
            
            # Meta Llama Models via Groq
            "llama-4-maverick-17b-128k": "Llama 4 Maverick 17B 128K",
            "llama-4-scout-17b-16e-instruct": "Llama 4 Scout 17B 16E Instruct",
            "llama-guard-4-12b": "Llama Guard 4 12B",
            "llama-prompt-guard-2-28b": "Llama Prompt Guard 2 28B",
            "llama-prompt-guard-2-8b": "Llama Prompt Guard 2 8B",
            
            # Legacy models that might still appear
            "gemini-pro": "Gemini Pro",
            "gemini-1.5-pro": "Gemini 1.5 Pro", 
            "gemini-1.5-flash": "Gemini 1.5 Flash",
            "llama-3.1-70b": "Llama 3.1 70B",
            "llama-3.1-8b": "Llama 3.1 8B",
            "mixtral-8x7b": "Mixtral 8x7B",
            "gemma-7b": "Gemma 7B",
            "gpt-4": "GPT-4",
            "gpt-3.5-turbo": "GPT-3.5 Turbo",
            "claude-3-opus": "Claude 3 Opus",
            "claude-3-sonnet": "Claude 3 Sonnet"
        }
        
        return name_map.get(model_name, model_name.replace("-", " ").title())
    
    def _get_max_tokens(self, model: str) -> int:
        """
        Get maximum tokens for a model.
        """
        # Token limits based on actual models in litellm_config.yaml
        token_map = {
            # Google Gemma Models
            "gemma-3n-e2b-it": 8192,
            "gemma-3n-e4b-it": 8192,
            "gemma-3-1b-it": 8192,
            "gemma-3-4b-it": 8192,
            "gemma-3-12b-it": 8192,
            "gemma-3-27b-it": 8192,
            
            # Google Gemini Models
            "gemini-2.5-pro": 2000000,
            "gemini-flash-latest": 1000000,
            "gemini-flash-lite-latest": 1000000,
            "gemini-2.5-flash-lite": 1000000,
            "gemini-2.0-flash": 1000000,
            "gemini-2.0-flash-lite": 1000000,
            "learnlm-2.0-flash-experimental": 1000000,
            
            # Groq Models
            "llama-3.1-8b-instant": 131072,
            "llama-3.3-70b-versatile": 32768,
            "compound": 32768,
            "compound-mini": 32768,
            
            # Legacy models
            "gpt-4": 8192,
            "gpt-3.5-turbo": 4096,
            "claude-3-opus": 200000,
            "claude-3-sonnet": 200000,
            "gemini-pro": 32768,
            "gemini-1.5-pro": 1000000,
            "gemini-1.5-flash": 1000000,
            "llama-3.1-70b": 32768,
            "llama-3.1-8b": 32768,
            "mixtral-8x7b": 32768,
            "gemma-7b": 8192
        }
        
        # Extract base model name
        base_model = model.split("/")[-1] if "/" in model else model
        return token_map.get(base_model, 4096)  # Default limit
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()