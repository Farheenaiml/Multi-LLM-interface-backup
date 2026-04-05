"""
Groq Adapter for direct API integration
Provides access to Groq's high-speed inference models
"""

import json
import httpx
from datetime import datetime
from typing import AsyncGenerator, List, Dict, Any, Optional

from .base import LLMAdapter
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Message, ModelInfo, StreamEvent, TokenData, FinalData, MeterData, ErrorData, StatusData  # type: ignore
from error_handler import error_handler  # type: ignore


class GroqAdapter(LLMAdapter):
    """
    Adapter for direct Groq AI API integration.
    
    Provides access to Groq's high-speed inference models
    including Mixtral and other optimized models.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.api_key = self.config.get("api_key")
        self.base_url = self.config.get("base_url", "https://api.groq.com/openai/v1")
        # Enhanced timeout configuration for Groq's fast inference
        timeout_config = httpx.Timeout(
            connect=15.0,  # Connection timeout
            read=300.0,    # Read timeout
            write=60.0,    # Write timeout
            pool=None      # Pool timeout
        )
        self.client = httpx.AsyncClient(timeout=timeout_config)
    
    @property
    def provider_name(self) -> str:
        return "groq"
    
    async def stream(
        self, 
        messages: List[Message], 
        model: str,
        pane_id: str,
        **kwargs
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        Stream responses from Groq API.
        """
        if not self.api_key:
            yield StreamEvent(
                type="error",
                pane_id=pane_id,
                data=ErrorData(
                    message="Groq API key not configured",
                    code="auth_error",
                    retryable=False
                )
            )
            return
        
        try:
            # Emit status event
            yield StreamEvent(
                type="status",
                pane_id=pane_id,
                data=StatusData(status="connecting", message=f"Connecting to Groq {model}")
            )
            
            # Convert messages to OpenAI format (Groq uses OpenAI-compatible API)
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
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            start_time = datetime.now()
            token_count = 0
            full_content = ""
            
            max_retries = 5
            for attempt in range(max_retries):
                async with self.client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers
                ) as response:
                    
                    if response.status_code in [503, 429] and attempt < max_retries - 1:
                        import asyncio
                        import random
                        
                        # Read Retry-After header if present
                        retry_after_str = response.headers.get("retry-after")
                        if retry_after_str and retry_after_str.isdigit():
                            wait_time = float(retry_after_str)
                        else:
                            # Exponential backoff: 2, 4, 8, 16...
                            base_wait = 2 
                            wait_time = (2 ** attempt) * base_wait
                            wait_time += random.uniform(0.1, 1.0)
                            
                        wait_time = min(wait_time, 60.0)
                        print(f"Groq API {response.status_code} on attempt {attempt+1}. Retrying in {wait_time:.2f}s...")
                        await asyncio.sleep(wait_time)
                        continue
                        
                    if response.status_code != 200:
                        error_text = await response.aread()
                        error_content = error_text.decode()
                        
                        # Print detailed error information
                        print(f"🔴 GROQ API ERROR - Status Code: {response.status_code}")
                        print(f"🔴 Model: {model}")
                        print(f"🔴 Response Headers: {dict(response.headers)}")
                        print(f"🔴 Error Content: {error_content[:1000]}")
                        
                        error_handler._log_structured(
                            "error",
                            f"Groq API error: {response.status_code}",
                            pane_id=pane_id,
                            model=model,
                            status_code=response.status_code,
                            error_text=error_content[:500]
                        )
                        
                        # Handle specific error codes
                        if response.status_code == 429:
                            retry_after = response.headers.get("retry-after")
                            if retry_after:
                                error_msg = f"Groq Rate Limited (429) - Retry after: {retry_after}s"
                            else:
                                error_msg = "Groq Rate Limited (429) - Please wait before trying again"
                        elif response.status_code == 403:
                            error_msg = f"Groq Forbidden (403) - Check API key permissions"
                        elif response.status_code == 404:
                            error_msg = f"Groq Not Found (404) - Model '{model}' may not exist"
                        elif response.status_code == 400:
                            error_msg = f"Groq Bad Request (400) - Invalid request format"
                        else:
                            error_msg = f"Groq API Error ({response.status_code})"
                        
                        yield StreamEvent(
                            type="error",
                            pane_id=pane_id,
                            data=ErrorData(
                                message=error_msg,
                                code=f"http_{response.status_code}",
                                retryable=response.status_code >= 500 or response.status_code == 429
                            )
                        )
                        return
                
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
                    
                break # Success, exit retry loop
                
        except httpx.TimeoutException as e:
            error_handler._log_structured(
                "warning",
                "Groq request timeout",
                pane_id=pane_id,
                model=model,
                timeout_type=type(e).__name__
            )
            
            yield StreamEvent(
                type="error",
                pane_id=pane_id,
                data=ErrorData(
                    message="Request timeout - Groq service may be busy",
                    code="timeout",
                    retryable=True
                )
            )
        except httpx.ConnectError as e:
            error_handler._log_structured(
                "error",
                "Groq connection error",
                pane_id=pane_id,
                model=model,
                error=str(e)
            )
            
            yield StreamEvent(
                type="error",
                pane_id=pane_id,
                data=ErrorData(
                    message="Unable to connect to Groq service",
                    code="network_error",
                    retryable=True
                )
            )
        except Exception as e:
            error_handler._log_structured(
                "error",
                "Unexpected Groq error",
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
        Get available Groq models - return hardcoded models to avoid API calls.
        """
        if not self.api_key:
            print("Groq API key not configured")
            return []
        
        # Always return fallback models to avoid unnecessary API calls
        print("Returning Groq fallback models")
        return self._get_fallback_models()
    
    def _get_chat_model_ids(self) -> Dict[str, str]:
        """Return mapping of chat-capable model IDs to display names - working models from API"""
        return {
            "llama-3.1-8b-instant": "Llama 3.1 8B Instant",
            "qwen/qwen3-32b": "Qwen 3 32B",
            "openai/gpt-oss-120b": "GPT OSS 120B",
            "openai/gpt-oss-20b": "GPT OSS 20B",
            "meta-llama/llama-4-maverick-17b-128e-instruct": "Llama 4 Maverick 17B"
        }
    
    def _get_fallback_models(self) -> List[ModelInfo]:
        """Return hardcoded working Groq models"""
        return [
            ModelInfo(
                id="llama-3.1-8b-instant",
                name="Llama 3.1 8B Instant",
                provider="groq",
                max_tokens=8192,
                cost_per_1k_tokens=0.0001,
                supports_streaming=True,
                supports_vision=False
            ),
            ModelInfo(
                id="qwen/qwen3-32b",
                name="Qwen 3 32B",
                provider="groq",
                max_tokens=32768,
                cost_per_1k_tokens=0.0008,
                supports_streaming=True
            ),
            ModelInfo(
                id="openai/gpt-oss-120b",
                name="GPT OSS 120B",
                provider="groq",
                max_tokens=8192,
                cost_per_1k_tokens=0.0012,
                supports_streaming=True
            ),
            ModelInfo(
                id="openai/gpt-oss-20b",
                name="GPT OSS 20B",
                provider="groq",
                max_tokens=8192,
                cost_per_1k_tokens=0.0006,
                supports_streaming=True
            )
        ]
    
    def _estimate_cost(self, model: str, tokens: int) -> float:
        """
        Estimate cost based on model and token count.
        """
        cost_per_1k = self._get_cost_per_1k(model)
        return (tokens / 1000.0) * cost_per_1k
    
    def _get_cost_per_1k(self, model: str) -> float:
        """
        Get cost per 1K tokens for Groq models.
        """
        # Updated Groq pricing - only working models
        cost_map = {
            "llama-3.1-8b-instant": 0.0001,
            "qwen/qwen3-32b": 0.0008,
            "openai/gpt-oss-120b": 0.0012,
            "openai/gpt-oss-20b": 0.0006
        }
        
        return cost_map.get(model, 0.0005)  # Default cost
    
    def _get_max_tokens(self, model: str) -> int:
        """
        Get maximum tokens for Groq models.
        """
        # Updated Groq model token limits - only working models
        token_map = {
            "llama-3.1-8b-instant": 8192,
            "qwen/qwen3-32b": 32768,
            "openai/gpt-oss-120b": 8192,
            "openai/gpt-oss-20b": 8192
        }
        
        return token_map.get(model, 8192)  # Default limit
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()