"""
Broadcast Orchestrator for coordinating multi-provider requests
Manages concurrent streaming from multiple LLM providers
"""

import asyncio
import logging
from typing import List, Dict, Any
from datetime import datetime

from models import (
    BroadcastRequest, StreamEvent, Message, ModelSelection,
    ErrorData, StatusData
)
from adapters.registry import AdapterRegistry
from session_manager import SessionManager
from error_handler import error_handler

logger = logging.getLogger(__name__)


class BroadcastOrchestrator:
    """
    Orchestrates broadcast requests to multiple LLM providers.
    
    Coordinates concurrent streaming, handles errors, and manages
    session state during multi-provider requests.
    """
    
    def __init__(self, adapter_registry: AdapterRegistry, session_manager: SessionManager):
        self.registry = adapter_registry
        self.session_manager = session_manager
        self.active_broadcasts: Dict[str, Dict[str, Any]] = {}
    
    async def broadcast(
        self, 
        request: BroadcastRequest, 
        pane_ids: List[str],
        connection_manager
    ):
        """
        Execute broadcast request to multiple providers.
        
        Args:
            request: Broadcast request with prompt and model selections
            pane_ids: List of pane IDs corresponding to each model
            connection_manager: WebSocket connection manager for streaming events
        """
        broadcast_id = f"{request.session_id}_{datetime.now().timestamp()}"
        
        try:
            error_handler._log_structured(
                "info",
                "Starting broadcast",
                session_id=request.session_id,
                broadcast_id=broadcast_id,
                model_count=len(request.models),
                pane_count=len(pane_ids)
            )
            
            # Track active broadcast
            self.active_broadcasts[broadcast_id] = {
                "session_id": request.session_id,
                "pane_ids": pane_ids,
                "start_time": datetime.now(),
                "status": "running"
            }
            
            # Create tasks for each model
            tasks = []
            for i, model_selection in enumerate(request.models):
                if i < len(pane_ids):
                    pane_id = pane_ids[i]
                    logger.info(f"Creating task {i+1}/{len(request.models)}: {model_selection.provider_id}:{model_selection.model_id} -> pane {pane_id}")
                    
                    task = asyncio.create_task(
                        self._stream_to_pane(
                            request, model_selection, pane_id, connection_manager
                        )
                    )
                    tasks.append(task)
                else:
                    logger.warning(f"No pane ID available for model {i}: {model_selection.provider_id}:{model_selection.model_id}")
            
            # Wait for all streams to complete
            logger.info(f"Waiting for {len(tasks)} concurrent streams to complete...")
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Log results with details
            successful = 0
            failed = 0
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    failed += 1
                    logger.error(f"Task {i+1} failed: {type(result).__name__}: {result}")
                else:
                    successful += 1
                    logger.info(f"Task {i+1} completed successfully")
            
            error_handler._log_structured(
                "info",
                "Broadcast completed",
                session_id=request.session_id,
                broadcast_id=broadcast_id,
                successful=successful,
                failed=failed,
                duration=(datetime.now() - self.active_broadcasts[broadcast_id]["start_time"]).total_seconds()
            )
            
            # Update broadcast status
            self.active_broadcasts[broadcast_id]["status"] = "completed"
            self.active_broadcasts[broadcast_id]["end_time"] = datetime.now()
            
        except Exception as e:
            error_handler._log_structured(
                "error",
                "Broadcast failed",
                session_id=request.session_id,
                broadcast_id=broadcast_id,
                error=str(e),
                error_type=type(e).__name__
            )
            self.active_broadcasts[broadcast_id]["status"] = "failed"
            self.active_broadcasts[broadcast_id]["error"] = str(e)
        
        finally:
            # Clean up old broadcasts (keep last 100)
            if len(self.active_broadcasts) > 100:
                oldest_keys = sorted(self.active_broadcasts.keys())[:50]
                for key in oldest_keys:
                    del self.active_broadcasts[key]
    
    async def _stream_to_pane(
        self,
        request: BroadcastRequest,
        model_selection: ModelSelection,
        pane_id: str,
        connection_manager
    ):
        """
        Stream responses from a single provider to a specific pane.
        
        Args:
            request: Original broadcast request
            model_selection: Model configuration for this stream
            pane_id: Target pane ID for streaming events
            connection_manager: WebSocket connection manager
        """
        try:
            # Build model ID early for error handling
            model_id = f"{model_selection.provider_id}:{model_selection.model_id}"
            
            # Get session
            session = self.session_manager.get_session(request.session_id)
            if not session:
                logger.error(f"Session not found: {request.session_id}")
                return
            
            # Get adapter for the provider
            logger.info(f"Getting adapter for provider: {model_selection.provider_id}")
            adapter = self.registry.get_adapter(model_selection.provider_id)
            
            if not adapter:
                logger.error(f"No adapter found for provider: {model_selection.provider_id}")
                logger.info(f"Available providers: {self.registry.list_providers()}")
                
                error_handler._log_structured(
                    "error",
                    "Provider adapter not available",
                    session_id=request.session_id,
                    pane_id=pane_id,
                    provider=model_selection.provider_id
                )
                
                await connection_manager.send_event(
                    request.session_id,
                    StreamEvent(
                        type="error",
                        pane_id=pane_id,
                        data=ErrorData(
                            message=f"Provider not available: {model_selection.provider_id}",
                            code="provider_unavailable",
                            retryable=False
                        )
                    )
                )
                return
            
            # Prepare messages with conversation history
            messages = []
            
            # Get the pane to retrieve conversation history
            pane = next((p for p in session.panes if p.id == pane_id), None)
            if pane and pane.messages:
                # Include all previous messages for context
                messages = [
                    Message(role=msg.role, content=msg.content, images=msg.images) 
                    for msg in pane.messages
                ]
            
            # Add the new user message
            messages.append(Message(role="user", content=request.prompt, images=request.images))
            
            # Log conversation context for debugging
            logger.info(f"🗨️ Sending {len(messages)} messages to {model_id} (pane: {pane_id})")
            for i, msg in enumerate(messages):
                logger.info(f"  [{i}] {msg.role}: {msg.content[:50]}{'...' if len(msg.content) > 50 else ''}")
            
            # Stream parameters
            stream_params = {
                "temperature": model_selection.temperature or 0.7,
                "max_tokens": model_selection.max_tokens or 1000
            }

            # --- VISION BRIDGE LOGIC ---
            # Check if model supports vision (default to False if info missing)
            model_info = await self.registry.get_model_info(model_id)
            supports_vision = getattr(model_info, 'supports_vision', False) if model_info else False
            
            # Determine if we need to use the bridge
            needs_bridge = False
            bridge_reason = ""
            bridge_prompt = ""
            
            if request.images and len(request.images) > 0:
                # Check for document types (PDF, PPT, CSV, Text)
                has_documents = False
                for img in request.images:
                    if any(mime in img for mime in ["application/pdf", "application/vnd", "text/", "application/json"]):
                        has_documents = True
                        break
                
                if not supports_vision:
                    needs_bridge = True
                    bridge_reason = "Model does not support vision/attachments"
                elif has_documents and model_selection.provider_id != "google":
                    # Even if model claims vision support (like GPT-4o via generic adapter),
                    # it often fails on direct PDF uploads or the adapter doesn't handle it.
                    # Safest to bridge documents for non-Google providers.
                    needs_bridge = True
                    bridge_reason = "Model provider may not support direct document uploads"
                
                # Set appropriate prompt based on content type
                if has_documents:
                    bridge_prompt = "Please analyze the attached document(s) in detail. Extract all text, key information, data points, and structural elements. Provide a comprehensive representation of the document's content so that a text-only AI can understand and analyze it."
                else:
                    bridge_prompt = "Please describe this image in extreme detail so that a text-only AI can understand what is in it. Describe layout, text, colors, objects, relationships, and any other relevant details."

            # Execute bridge if needed
            if needs_bridge:
                print(f"🌉 VISION BRIDGE ACTIVATED: {bridge_reason}")
                logger.info(f"🌉 Vision Bridge Triggered: {bridge_reason}. Handing off to Gemini...")
                
                # Notify user of the bridge action
                status_msg = "Analyzing document..." if has_documents else "Analyzing image..."
                await connection_manager.send_event(
                    request.session_id,
                    StreamEvent(
                        type="status",
                        pane_id=pane_id,
                        data=StatusData(
                            status="analyzing_image",
                            message=f"{status_msg} (via Gemini Bridge)"
                        )
                    )
                )

                try:
                    # Get Google Adapter for vision
                    vision_adapter = self.registry.get_adapter("google")
                    if vision_adapter:
                        # Create a temporary message for Gemini
                        vision_messages = [
                            Message(
                                role="user", 
                                content=bridge_prompt,
                                images=request.images
                            )
                        ]
                        
                        description = ""
                        # Stream the description (we just want the final text)
                        # Use a reliable stable model for analysis (using alias to catch available version)
                        async for event in vision_adapter.stream(vision_messages, "gemini-2.5-flash", "temp_vision_pane"):
                            if event.type == "token":
                                description += event.data.token
                            elif event.type == "final":
                                description = event.data.content
                        
                        if description:
                            # ... (success logic unchanged)
                            logger.info(f"🌉 Vision Bridge Success: Generated {len(description)} chars context")
                            
                            # Append description to the LAST message (current user prompt)
                            if messages:
                                last_msg = messages[-1]
                                context_type_lbl = "DOCUMENT ANALYSIS" if has_documents else "IMAGE DESCRIPTION"
                                last_msg.content += f"\n\n[SYSTEM NOTE: The user attached a file. Here is the {context_type_lbl} generated by a vision model:]\n{description}"
                                last_msg.images = None # Remove images so target adapter doesn't choke
                            
                            # Notify user
                            await connection_manager.send_event(
                                request.session_id,
                                StreamEvent(
                                    type="status",
                                    pane_id=pane_id,
                                    data=StatusData(
                                        status="ready",
                                        message=f"Analysis complete. Sending text context to {model_selection.model_id}..."
                                    )
                                )
                            )
                        else:
                            logger.warning("🌉 Vision Bridge: Gemini returned empty description")
                except Exception as e:
                    logger.error(f"🌉 Vision Bridge Error: {str(e)}", exc_info=True)
                    # Notify user of failure but continue
                    await connection_manager.send_event(
                        request.session_id,
                        StreamEvent(
                            type="status",
                            pane_id=pane_id,
                            data=StatusData(
                                status="streaming",
                                message=f"Document analysis failed, sending raw prompt..."
                            )
                        )
                    )
                    # Continue without description, model will likely fail or say "I can't see"
            # ---------------------------
            
            error_handler._log_structured(
                "info",
                "Starting stream",
                session_id=request.session_id,
                pane_id=pane_id,
                model=model_id,
                provider=model_selection.provider_id
            )
            
            # Update pane status
            pane = next((p for p in session.panes if p.id == pane_id), None)
            if pane:
                pane.is_streaming = True
                self.session_manager.update_session(session)
            
            # Send status event
            await connection_manager.send_event(
                request.session_id,
                StreamEvent(
                    type="status",
                    pane_id=pane_id,
                    data=StatusData(
                        status="streaming",
                        message=f"Streaming from {model_id}"
                    )
                )
            )
            
            # Stream responses with enhanced error handling
            assistant_message = Message(role="assistant", content="")
            
            # Use the streaming method from our custom adapters
            logger.info(f"Starting adapter.stream for {model_id} -> pane {pane_id}")
            
            try:
                async for event in adapter.stream(
                    messages, model_selection.model_id, pane_id, **stream_params
                ):
                    print(f"🎯 Generated event: {event.type} for pane {pane_id} (model: {model_id})")
                    
                    # Update session state
                    if event.type == "token":
                        assistant_message.content += event.data.token
                    elif event.type == "final":
                        assistant_message.content = event.data.content
                        
                        # Add message to pane
                        if session:
                            pane = next((p for p in session.panes if p.id == pane_id), None)
                            if pane:
                                pane.messages.append(assistant_message)
                                pane.is_streaming = False
                                self.session_manager.update_session(session)
                        
                        # Update the event to include the backend-generated message ID
                        event.data.message_id = assistant_message.id
                    
                    elif event.type == "meter":
                        # Update pane metrics
                        if session:
                            pane = next((p for p in session.panes if p.id == pane_id), None)
                            if pane:
                                pane.metrics.token_count += event.data.tokens_used
                                pane.metrics.cost += event.data.cost
                                pane.metrics.latency = event.data.latency
                                pane.metrics.request_count += 1
                                
                                # Update session totals
                                session.total_cost += event.data.cost
                                self.session_manager.update_session(session)
                    
                    # Forward event to WebSocket
                    await connection_manager.send_event(request.session_id, event)
                    
            except Exception as stream_error:
                logger.error(f"Adapter streaming error for {model_id}: {type(stream_error).__name__}: {stream_error}")
                raise stream_error
            
            error_handler._log_structured(
                "info",
                "Stream completed successfully",
                session_id=request.session_id,
                pane_id=pane_id,
                model=model_id
            )
            
        except Exception as e:
            error_handler._log_structured(
                "error",
                "Stream error",
                session_id=request.session_id,
                pane_id=pane_id,
                model=model_id,
                error=str(e),
                error_type=type(e).__name__
            )
            
            # Send error event using error handler
            error_event = error_handler.create_error_event(e, pane_id)
            await connection_manager.send_event(request.session_id, error_event)
            
            # Update pane status
            try:
                session = self.session_manager.get_session(request.session_id)
                if session:
                    pane = next((p for p in session.panes if p.id == pane_id), None)
                    if pane:
                        pane.is_streaming = False
                        self.session_manager.update_session(session)
            except Exception as session_error:
                logger.error(f"Error updating pane status: {session_error}")
    
    def get_broadcast_status(self, session_id: str) -> Dict[str, Any]:
        """
        Get status of broadcasts for a session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Dictionary with broadcast status information
        """
        session_broadcasts = {
            k: v for k, v in self.active_broadcasts.items()
            if v["session_id"] == session_id
        }
        
        return {
            "active_count": sum(1 for b in session_broadcasts.values() if b["status"] == "running"),
            "total_count": len(session_broadcasts),
            "broadcasts": session_broadcasts
        }
    
    def cancel_broadcast(self, session_id: str) -> bool:
        """
        Cancel active broadcasts for a session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            True if any broadcasts were cancelled
        """
        cancelled = False
        
        for broadcast_id, broadcast_info in self.active_broadcasts.items():
            if (broadcast_info["session_id"] == session_id and 
                broadcast_info["status"] == "running"):
                broadcast_info["status"] = "cancelled"
                cancelled = True
        
        return cancelled