"""
Google Data Studio Adapter for direct API integration
Provides direct access to Google's AI models
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


class GoogleDataStudioAdapter(LLMAdapter):
    """
    Adapter for direct Google Data Studio API integration.
    
    Provides access to Google's AI models including Gemini Pro
    through direct API calls.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.api_key = self.config.get("api_key")
        self.base_url = self.config.get("base_url", "https://generativelanguage.googleapis.com/v1beta")
        # Enhanced timeout configuration for Google API
        timeout_config = httpx.Timeout(
            connect=15.0,  # Connection timeout
            read=90.0,     # Read timeout (Google can be slower)
            write=10.0,    # Write timeout
            pool=5.0       # Pool timeout
        )
        self.client = httpx.AsyncClient(timeout=timeout_config)
    
    @property
    def provider_name(self) -> str:
        return "google"
    
    async def stream(
        self, 
        messages: List[Message], 
        model: str,
        pane_id: str,
        **kwargs
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        Stream responses from Google Data Studio API.
        """
        if not self.api_key:
            yield StreamEvent(
                type="error",
                pane_id=pane_id,
                data=ErrorData(
                    message="Google API key not configured",
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
                data=StatusData(status="connecting", message=f"Connecting to Google {model}")
            )
            
            # Extract system messages for Google's specific systemInstruction format
            system_instructions = []
            conversation_messages = []
            
            for msg in messages:
                if msg.role == "system":
                    system_instructions.append(msg.content)
                else:
                    conversation_messages.append(msg)
                    
            # Convert remaining messages to Google format
            formatted_messages = self._format_messages(conversation_messages)
            
            # Prepare request payload
            payload = {
                "contents": formatted_messages,
                "generationConfig": {
                    "temperature": kwargs.get("temperature", 0.7),
                    "maxOutputTokens": kwargs.get("max_tokens", 8192),
                    "candidateCount": 1
                }
            }
            
            if system_instructions:
                combined_system_text = "\n\n".join(system_instructions)
                payload["systemInstruction"] = {
                    "parts": [{"text": combined_system_text}]
                }
            
            # Use streaming endpoint
            url = f"{self.base_url}/models/{model}:streamGenerateContent"
            params = {"key": self.api_key}
            headers = {"Content-Type": "application/json"}
            
            start_time = datetime.now()
            token_count = 0
            full_content = ""
            
            async with self.client.stream(
                "POST",
                url,
                json=payload,
                params=params,
                headers=headers
            ) as response:
                
                if response.status_code != 200:
                    error_text = await response.aread()
                    error_content = error_text.decode()
                    
                    # Print detailed error information
                    print(f"🔴 GOOGLE API ERROR - Status Code: {response.status_code}")
                    print(f"🔴 Model: {model}")
                    print(f"🔴 Response Headers: {dict(response.headers)}")
                    print(f"🔴 Error Content: {error_content[:1000]}")
                    
                    error_handler._log_structured(
                        "error",
                        f"Google API error: {response.status_code}",
                        pane_id=pane_id,
                        model=model,
                        status_code=response.status_code,
                        error_text=error_content[:500]
                    )
                    
                    # Handle specific error codes
                    if response.status_code == 429:
                        retry_after = response.headers.get("retry-after", "unknown")
                        error_msg = f"Google Rate Limited (429) - Retry after: {retry_after}s"
                    elif response.status_code == 403:
                        error_msg = f"Google Forbidden (403) - Check API key permissions"
                    elif response.status_code == 404:
                        error_msg = f"Google Not Found (404) - Model '{model}' may not exist"
                    else:
                        error_msg = f"Google API Error ({response.status_code})"
                    
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
                
                print(f"🔍 Starting to process Google streaming response for pane: {pane_id}")
                
                # Read the entire response and parse as JSON
                response_text = await response.aread()
                response_str = response_text.decode('utf-8')
                print(f"📥 Complete response from Google ({len(response_str)} bytes): {response_str[:1000]}...")
                
                try:
                    # Parse the complete JSON response
                    data = json.loads(response_str)
                    print(f"📊 Parsed complete JSON data keys/length: {len(data) if isinstance(data, list) else 'Dict'}")
                    
                    # Handle array of streaming chunks (Standard Google Stream API)
                    if isinstance(data, list):
                        for response_obj in data:
                            if "candidates" in response_obj and len(response_obj["candidates"]) > 0:
                                candidate = response_obj["candidates"][0]
                                
                                # Extract text content
                                if "content" in candidate and "parts" in candidate["content"]:
                                    for part in candidate["content"]["parts"]:
                                        if "text" in part:
                                            token = part["text"]
                                            if token:
                                                full_content += token
                                                token_count += len(token.split())
                                                
                                                yield StreamEvent(
                                                    type="token",
                                                    pane_id=pane_id,
                                                    data=TokenData(token=token, position=token_count)
                                                )
                                
                                # Check for finish reason in the last chunk or current chunk
                                if "finishReason" in candidate:
                                    end_time = datetime.now()
                                    latency = int((end_time - start_time).total_seconds() * 1000)
                                    
                                    # Emit final content
                                    yield StreamEvent(
                                        type="final",
                                        pane_id=pane_id,
                                        data=FinalData(
                                            content=full_content,
                                            finish_reason=candidate["finishReason"]
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
                                    break
                    
                    # Handle single object response (e.g. error or non-streaming structure)
                    elif isinstance(data, dict):
                         # If it's a valid response dict (candidates) but not list
                         if "candidates" in data and len(data["candidates"]) > 0:
                            # Re-use similar logic or just extract all at once
                            candidate = data["candidates"][0]
                            if "content" in candidate and "parts" in candidate["content"]:
                                text = "".join([p.get("text", "") for p in candidate["content"]["parts"]])
                                full_content = text
                                token_count = len(text.split())
                                
                                yield StreamEvent(
                                    type="token",
                                    pane_id=pane_id,
                                    data=TokenData(token=text, position=token_count)
                                )
                                
                                yield StreamEvent(
                                    type="final",
                                    pane_id=pane_id,
                                    data=FinalData(
                                        content=full_content,
                                        finish_reason=candidate.get("finishReason", "STOP")
                                    )
                                )
                         else:
                            print(f"⚠️ Warning: Unrecognized JSON dict structure: {data.keys()}")

                except json.JSONDecodeError as e:
                    print(f"❌ Failed to parse JSON response from Google: {e}")
                    # Log error but try to continue or fail gracefully
                    yield StreamEvent(
                        type="error",
                        pane_id=pane_id,
                        data=ErrorData(
                            message=f"Google API Error: Invalid JSON response",
                            code="parse_error",
                            retryable=True
                        )
                    )
                    
                except json.JSONDecodeError:
                    print(f"❌ Failed to parse JSON response from Google")
                    pass  # Skip malformed JSON
                
        except httpx.TimeoutException as e:
            error_handler._log_structured(
                "warning",
                "Google API request timeout",
                pane_id=pane_id,
                model=model,
                timeout_type=type(e).__name__
            )
            
            yield StreamEvent(
                type="error",
                pane_id=pane_id,
                data=ErrorData(
                    message="Request timeout - Google service may be busy",
                    code="timeout",
                    retryable=True
                )
            )
        except httpx.ConnectError as e:
            error_handler._log_structured(
                "error",
                "Google API connection error",
                pane_id=pane_id,
                model=model,
                error=str(e)
            )
            
            yield StreamEvent(
                type="error",
                pane_id=pane_id,
                data=ErrorData(
                    message="Unable to connect to Google service",
                    code="network_error",
                    retryable=True
                )
            )
        except Exception as e:
            error_handler._log_structured(
                "error",
                "Unexpected Google API error",
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
        Get available Google models - return hardcoded models to avoid API rate limits.
        """
        if not self.api_key:
            print("❌ Google API key not configured")
            return []
        
        # Always return fallback models to avoid rate limiting and API calls
        print("✅ Returning Google fallback models")
        return self._get_fallback_models()
    
    def _get_fallback_models(self) -> List[ModelInfo]:
        """Return hardcoded working Google models - 3 core models"""
        return [
            ModelInfo(
                id="gemini-1.5-flash",
                name="Gemini 1.5 Flash",
                provider="google",
                max_tokens=1048576,
                cost_per_1k_tokens=0.0007,
                supports_streaming=True,
                supports_vision=True
            ),
            ModelInfo(
                id="gemini-flash-latest",
                name="Gemini Flash Latest",
                provider="google",
                max_tokens=1048576,
                cost_per_1k_tokens=0.0007,
                supports_streaming=True,
                supports_vision=True
            )
        ]
    
        return formatted
    
    def _format_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """
        Convert messages to Google format, handling images if present.
        """
        formatted = []
        
        for msg in messages:
            # Google uses 'user' and 'model' roles
            role = "user" if msg.role == "user" else "model"
            
            parts = []
            
            # DEBUG: Log image processing
            if msg.images:
                print(f"🖼️ Google Adapter: Processing {len(msg.images)} images for message")
                for i, img in enumerate(msg.images):
                    print(f"  - Image {i} length: {len(img)}")
                    if "," in img:
                        print(f"  - Image {i} header: {img.split(',')[0]}")
            
            # Handle images if present (Gemini prefers images before text)
            if msg.images:
                for img_data in msg.images:
                    # Parse base64 data dict
                    # Expected format: "data:image/png;base64,..."
                    if "," in img_data:
                        header, base64_str = img_data.split(",", 1)
                        # Clean base64 string
                        base64_str = base64_str.strip()
                        mime_type = header.split(":")[1].split(";")[0]
                        
                        parts.append({
                            "inlineData": {
                                "mimeType": mime_type,
                                "data": base64_str
                            }
                        })

            # Handle text content
            if msg.content:
                parts.append({"text": msg.content})
            
            print(f"📤 Google Adapter: Constructed {len(parts)} parts (Images: {len([p for p in parts if 'inlineData' in p])}, Text: {len([p for p in parts if 'text' in p])})")
            
            if parts:
                formatted.append({
                    "role": role,
                    "parts": parts
                })
        
        return formatted
    
    def _estimate_cost(self, model: str, tokens: int) -> float:
        """
        Estimate cost based on model and token count.
        """
        cost_per_1k = self._get_cost_per_1k(model)
        return (tokens / 1000.0) * cost_per_1k
    
    def _get_cost_per_1k(self, model: str) -> float:
        """
        Get cost per 1K tokens for Google models.
        """
        # Google Gemini pricing (simplified)
        cost_map = {
            "gemini-pro": 0.001,
            "gemini-pro-vision": 0.002,
            "gemini-1.5-pro": 0.0035,
            "gemini-1.5-flash": 0.0007
        }
        
        return cost_map.get(model, 0.001)  # Default cost
    
    def _get_max_tokens(self, model: str) -> int:
        """
        Get maximum tokens for Google models.
        """
        # Google model token limits
        token_map = {
            "gemini-pro": 32768,
            "gemini-pro-vision": 16384,
            "gemini-1.5-pro": 1048576,
            "gemini-1.5-flash": 1048576
        }
        
        return token_map.get(model, 32768)  # Default limit
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()