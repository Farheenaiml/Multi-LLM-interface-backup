"""
Multi-LLM Broadcast Workspace Backend
FastAPI application with WebSocket support for real-time LLM streaming
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional
from uuid import uuid4

import httpx
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from models import (
    BroadcastRequest, BroadcastResponse, SendToRequest, SendToResponse,
    SummaryRequest, SummaryResponse, HealthResponse, Session, ChatPane,
    Message, StreamEvent, ModelSelection, ProvenanceInfo
)
from adapters.registry import registry
from broadcast_orchestrator import BroadcastOrchestrator
from session_manager import SessionManager
from error_handler import error_handler
from websocket_manager import connection_manager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Debug: Check if API keys are loaded
google_key = os.getenv("GOOGLE_API_KEY")
groq_key = os.getenv("GROQ_API_KEY")
print(f"🔑 Google API Key: {'✅ Loaded' if google_key else '❌ Missing'}")
print(f"🔑 Groq API Key: {'✅ Loaded' if groq_key else '❌ Missing'}")

app = FastAPI(
    title="Multi-LLM Broadcast Workspace API",
    description="Backend API for broadcasting prompts to multiple LLM providers",
    version="0.1.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global instances
session_manager = SessionManager()
broadcast_orchestrator = BroadcastOrchestrator(registry, session_manager)
manager = connection_manager


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"message": "Multi-LLM Broadcast Workspace API"}


@app.post("/analyze-code")
async def analyze_code(request: Request):
    """Analyze code using Groq and return structured metrics."""
    body = await request.json()
    code = body.get("code", "")
    model_name = body.get("model_name", "unknown")

    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY not set in .env")

    prompt = f"""You are a senior software engineer. Analyze this code and return ONLY a valid JSON object. No markdown, no explanation, no extra text.

Code from {model_name}:
{code}

Return exactly this JSON:
{{
  "timeComplexity": "O(?)",
  "spaceComplexity": "O(?)",
  "readabilityScore": 0,
  "readabilityGrade": "A",
  "cyclomaticComplexity": 1,
  "securityIssues": [
    {{"severity": "low", "title": "example", "description": "example description", "line": null}}
  ],
  "bugs": [
    {{"severity": "low", "title": "example", "description": "example description", "line": null}}
  ],
  "overallScore": 0
}}

Fill in real values based on the code analysis. Return ONLY the JSON, nothing else."""

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "llama-3.1-8b-instant",
                "max_tokens": 1000,
                "temperature": 0.1,
                "messages": [{"role": "user", "content": prompt}]
            }
        )

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Groq error: {resp.text}")

    data = resp.json()
    text = data["choices"][0]["message"]["content"]
    clean = text.replace("```json", "").replace("```", "").strip()

    try:
        return json.loads(clean)
    except Exception:
        return {
            "timeComplexity": "N/A", "spaceComplexity": "N/A",
            "readabilityScore": 50, "readabilityGrade": "C",
            "cyclomaticComplexity": 1, "securityIssues": [], "bugs": [],
            "overallScore": 50
        }


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint with provider status and error handler health"""
    try:
        provider_health = await registry.health_check()
        error_handler_health = error_handler.get_provider_health()
        connection_stats = manager.get_connection_stats()

        healthy_providers = sum(1 for status in provider_health.values() if status)
        total_providers = len(provider_health)

        overall_status = "healthy"
        if healthy_providers == 0:
            overall_status = "unhealthy"
        elif healthy_providers < total_providers:
            overall_status = "degraded"

        error_handler._log_structured(
            "info", "Health check performed",
            healthy_providers=healthy_providers,
            total_providers=total_providers,
            websocket_connections=connection_stats["total_connections"],
            overall_status=overall_status
        )

        return HealthResponse(status=overall_status, service="multi-llm-broadcast-workspace")
    except Exception as e:
        error_handler._log_structured("error", f"Health check error: {str(e)}", error_type=type(e).__name__)
        return HealthResponse(status="unhealthy", service="multi-llm-broadcast-workspace")


@app.post("/broadcast", response_model=BroadcastResponse)
async def create_broadcast(request: BroadcastRequest):
    """Create a broadcast request to multiple LLM providers"""
    try:
        logger.info(f"Creating broadcast for session {request.session_id} with {len(request.models)} models")
        print(f"🎯 Broadcast request: {request.models}")

        for model_selection in request.models:
            model_id = f"{model_selection.provider_id}:{model_selection.model_id}"
            print(f"🔍 Validating model: {model_id}")
            is_valid = await registry.validate_model(model_id)
            print(f"✅ Model {model_id} valid: {is_valid}")
            if not is_valid:
                raise HTTPException(status_code=400, detail=f"Invalid model: {model_id}")

        print(f"📝 Creating/getting session: {request.session_id}")
        session = session_manager.get_or_create_session(request.session_id)
        print(f"✅ Session created: {session.id}")

        pane_ids = []
        user_message_ids = {}
        for model_selection in request.models:
            model_id = f"{model_selection.provider_id}:{model_selection.model_id}"
            print(f"🔍 Getting model info for: {model_id}")
            model_info = await registry.get_model_info(model_id)
            print(f"📋 Model info: {model_info}")

            if model_info:
                user_message = Message(role="user", content=request.prompt, images=request.images)
                print(f"📝 Created user message with ID: {user_message.id}")
                pane = ChatPane(model_info=model_info, messages=[user_message])
                session.panes.append(pane)
                pane_ids.append(pane.id)
                user_message_ids[pane.id] = user_message.id

        session_manager.update_session(session)
        asyncio.create_task(broadcast_orchestrator.broadcast(request, pane_ids, manager))

        return BroadcastResponse(
            session_id=request.session_id,
            pane_ids=pane_ids,
            status="started",
            user_message_ids=user_message_ids
        )

    except Exception as e:
        logger.error(f"Broadcast error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat/{pane_id}")
async def send_chat_message(pane_id: str, request: dict):
    """Send a message to a specific existing pane"""
    try:
        logger.info(f"Chat request for pane {pane_id}: {request}")
        session_id = request.get("session_id")
        message = request.get("message")

        if not session_id or not message:
            logger.error(f"Missing required fields: session_id={session_id}, message={bool(message)}")
            raise HTTPException(status_code=400, detail="Missing session_id or message")

        session = session_manager.get_session(session_id)
        if not session:
            logger.error(f"Session not found: {session_id}")
            raise HTTPException(status_code=404, detail="Session not found")

        pane = next((p for p in session.panes if p.id == pane_id), None)
        if not pane:
            logger.error(f"Pane not found: {pane_id} in session {session_id}")
            raise HTTPException(status_code=404, detail="Pane not found")

        logger.info(f"🔍 CHAT REQUEST DEBUG: Model ID: {pane.model_info.id} (Provider: {pane.model_info.provider})")
        images = request.get("images")

        user_message = Message(role="user", content=message, images=images)
        pane.messages.append(user_message)
        session_manager.update_session(session)

        if ':' in pane.model_info.id:
            provider_id, model_id = pane.model_info.id.split(':', 1)
        else:
            provider_id = pane.model_info.provider
            model_id = pane.model_info.id

        model_selection = ModelSelection(provider_id=provider_id, model_id=model_id, temperature=0.7, max_tokens=1000)
        broadcast_request = BroadcastRequest(session_id=session_id, prompt=message, images=images, models=[model_selection])

        asyncio.create_task(broadcast_orchestrator._stream_to_pane(broadcast_request, model_selection, pane_id, manager))

        return {"success": True, "pane_id": pane_id}

    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/send-to", response_model=SendToResponse)
async def send_to_pane(request: SendToRequest):
    """Send selected messages from one pane to another"""
    try:
        logger.info(f"Transferring messages from {request.source_pane_id} to {request.target_pane_id}")
        session = session_manager.get_session(request.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        source_pane = None
        target_pane = None
        for pane in session.panes:
            if pane.id == request.source_pane_id:
                source_pane = pane
            elif pane.id == request.target_pane_id:
                target_pane = pane

        if not source_pane:
            raise HTTPException(status_code=404, detail=f"Source pane {request.source_pane_id} not found")
        if not target_pane:
            raise HTTPException(status_code=404, detail=f"Target pane {request.target_pane_id} not found")

        selected_messages = []
        for message_id in request.message_ids:
            for msg in source_pane.messages:
                if msg.id == message_id:
                    selected_messages.append(msg)
                    break

        if not selected_messages:
            raise HTTPException(status_code=400, detail="No valid messages found to transfer")

        messages_to_transfer = []

        if request.additional_context and request.additional_context.strip():
            context_message = Message(
                role="system",
                content=request.additional_context.strip(),
                provenance=ProvenanceInfo(
                    source_model="user-context",
                    source_pane_id=request.source_pane_id,
                    transfer_timestamp=datetime.now(),
                    content_hash=str(hash(request.additional_context))
                )
            )
            messages_to_transfer.append(context_message)

        if request.transfer_mode == "summarize":
            conversation_text = "\n\n".join([f"{msg.role.upper()}: {msg.content}" for msg in selected_messages])
            summary_prompt = ""
            if request.summary_instructions and request.summary_instructions.strip():
                summary_prompt = f"Please summarize the following conversation with these specific instructions: {request.summary_instructions.strip()}\n\n"
            else:
                summary_prompt = "Please provide a concise summary of the following conversation:\n\n"
            summary_prompt += f"Conversation to summarize:\n\n{conversation_text}"

            try:
                adapter = registry.get_adapter(source_pane.model_info.provider)
                if not adapter:
                    raise HTTPException(status_code=500, detail=f"No adapter available for {source_pane.model_info.provider}")

                summary_messages = [Message(role="user", content=summary_prompt)]
                summary_content = ""

                async for event in adapter.stream(
                    summary_messages,
                    source_pane.model_info.id.split(':')[-1],
                    f"summary-{request.source_pane_id}",
                    temperature=0.3,
                    max_tokens=500
                ):
                    if event.type == "token":
                        summary_content += event.data.token
                    elif event.type == "final":
                        summary_content = event.data.content
                        break

                if not summary_content.strip():
                    raise HTTPException(status_code=500, detail="Failed to generate summary - empty response")

                summary_message = Message(
                    role="user",
                    content=summary_content.strip(),
                    provenance=ProvenanceInfo(
                        source_model=source_pane.model_info.id,
                        source_pane_id=request.source_pane_id,
                        transfer_timestamp=datetime.now(),
                        content_hash=str(hash(summary_content))
                    )
                )
                messages_to_transfer.append(summary_message)

            except Exception as e:
                logger.error(f"Failed to generate summary: {e}")
                raise HTTPException(status_code=500, detail=f"Summary generation failed: {str(e)}")

        else:
            for msg in selected_messages:
                transferred_message = Message(
                    role=msg.role if request.preserve_roles else "user",
                    content=msg.content,
                    provenance=ProvenanceInfo(
                        source_model=source_pane.model_info.id,
                        source_pane_id=request.source_pane_id,
                        transfer_timestamp=datetime.now(),
                        content_hash=str(hash(msg.content))
                    )
                )
                messages_to_transfer.append(transferred_message)

        if request.transfer_mode == "replace":
            target_pane.messages.clear()

        target_pane.messages.extend(messages_to_transfer)
        transferred_count = len(messages_to_transfer)

        try:
            adapter = registry.get_adapter(target_pane.model_info.provider)
            if adapter and target_pane.messages:
                context_update_message = Message(
                    role="system",
                    content=f"[Context updated: {transferred_count} messages transferred from {source_pane.model_info.name}]",
                    provenance=ProvenanceInfo(
                        source_model="system",
                        source_pane_id=request.target_pane_id,
                        transfer_timestamp=datetime.now(),
                        content_hash="context-update"
                    )
                )
                target_pane.messages.append(context_update_message)
        except Exception as llm_error:
            logger.warning(f"Failed to update LLM context: {llm_error}")

        session_manager.update_session(session)
        logger.info(f"Successfully transferred {transferred_count} messages to pane {request.target_pane_id}")

        return SendToResponse(success=True, transferred_count=transferred_count, target_pane_id=request.target_pane_id)

    except Exception as e:
        import traceback
        logger.error(f"Send-to error: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Send-to error: {str(e)}")


@app.post("/summarize", response_model=SummaryResponse)
async def generate_summary(request: SummaryRequest):
    """Generate summaries of selected panes"""
    try:
        logger.info(f"Generating summary for panes: {request.pane_ids}")
        session = session_manager.get_session(request.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        content_parts = []
        for pane_id in request.pane_ids:
            pane = next((p for p in session.panes if p.id == pane_id), None)
            if pane:
                pane_content = "\n".join([f"{msg.role}: {msg.content}" for msg in pane.messages])
                content_parts.append(f"=== {pane.model_info.name} ===\n{pane_content}")

        combined_content = "\n\n".join(content_parts)

        default_adapter = None
        for provider_name in registry.list_providers():
            adapter = registry.get_adapter(provider_name)
            if adapter:
                default_adapter = adapter
                break

        if not default_adapter:
            raise HTTPException(status_code=503, detail="No summarization model available")

        summary_pane = ChatPane(
            model_info=await registry.get_model_info("litellm:gpt-3.5-turbo") or
                      (await registry.discover_models()).get("litellm", [{}])[0],
            messages=[]
        )

        summaries = {}
        for summary_type in request.summary_types:
            summaries[summary_type] = f"{summary_type.title()} summary of {len(request.pane_ids)} conversations"
            summary_pane.messages.append(Message(role="assistant", content=summaries[summary_type]))

        session.panes.append(summary_pane)
        session_manager.update_session(session)

        return SummaryResponse(summary_pane_id=summary_pane.id, summaries=summaries, source_panes=request.pane_ids)

    except Exception as e:
        logger.error(f"Summarization error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """Get session details"""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@app.get("/sessions")
async def list_sessions(limit: int = 50, offset: int = 0):
    """List sessions with pagination"""
    sessions = session_manager.list_sessions(limit, offset)
    total_count = len(session_manager.sessions)
    return {"sessions": sessions, "total_count": total_count, "limit": limit, "offset": offset}


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a session"""
    success = session_manager.delete_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"success": True, "message": "Session deleted"}


@app.get("/models")
async def get_available_models():
    """Get all available models from all providers"""
    try:
        models_by_provider = await registry.discover_models()
        all_models = []
        for provider, models in models_by_provider.items():
            for model in models:
                all_models.append({
                    "id": model.id,
                    "name": model.name,
                    "provider": provider,
                    "max_tokens": model.max_tokens,
                    "cost_per_1k_tokens": model.cost_per_1k_tokens,
                    "supports_streaming": model.supports_streaming
                })
        return {"models": all_models, "providers": list(models_by_provider.keys()), "total_count": len(all_models)}
    except Exception as e:
        logger.error(f"Error getting models: {e}")
        raise HTTPException(status_code=500, detail="Error retrieving models")


@app.get("/providers/health")
async def get_provider_health():
    """Get health status of all providers"""
    try:
        health_status = await registry.health_check()
        return {
            "providers": health_status,
            "healthy_count": sum(1 for status in health_status.values() if status),
            "total_count": len(health_status)
        }
    except Exception as e:
        logger.error(f"Error checking provider health: {e}")
        raise HTTPException(status_code=500, detail="Error checking provider health")


@app.get("/stats")
async def get_system_stats():
    """Get enhanced system statistics"""
    try:
        session_stats = session_manager.get_session_stats()
        broadcast_stats = {
            "active_broadcasts": sum(1 for b in broadcast_orchestrator.active_broadcasts.values() if b["status"] == "running"),
            "total_broadcasts": len(broadcast_orchestrator.active_broadcasts)
        }
        connection_stats = manager.get_connection_stats()
        error_handler_stats = error_handler.get_provider_health()
        return {
            "sessions": session_stats,
            "broadcasts": broadcast_stats,
            "websocket_connections": connection_stats,
            "error_handler": {"provider_health": error_handler_stats, "circuit_breakers": len(error_handler.circuit_breakers)}
        }
    except Exception as e:
        error_handler._log_structured("error", f"Error getting stats: {str(e)}", error_type=type(e).__name__)
        raise HTTPException(status_code=500, detail="Error retrieving statistics")


@app.get("/system/health/detailed")
async def get_detailed_health():
    """Get detailed system health information"""
    try:
        provider_health = await registry.health_check()
        error_handler_health = error_handler.get_provider_health()
        connection_stats = manager.get_connection_stats()
        return {
            "providers": {"registry_health": provider_health, "error_handler_health": error_handler_health},
            "websockets": connection_stats,
            "system": {
                "active_sessions": len(session_manager.sessions),
                "active_broadcasts": len([b for b in broadcast_orchestrator.active_broadcasts.values() if b["status"] == "running"])
            }
        }
    except Exception as e:
        error_handler._log_structured("error", f"Error getting detailed health: {str(e)}", error_type=type(e).__name__)
        raise HTTPException(status_code=500, detail="Error retrieving detailed health")


@app.post("/system/reset-circuit-breakers")
async def reset_circuit_breakers():
    """Reset all circuit breakers"""
    try:
        reset_count = 0
        for provider, circuit_breaker in error_handler.circuit_breakers.items():
            if circuit_breaker.state != "closed":
                circuit_breaker.failure_count = 0
                circuit_breaker.state = "closed"
                circuit_breaker.last_failure_time = None
                reset_count += 1
        error_handler._log_structured("info", "Circuit breakers reset", reset_count=reset_count)
        return {"success": True, "reset_count": reset_count, "message": f"Reset {reset_count} circuit breakers"}
    except Exception as e:
        error_handler._log_structured("error", f"Error resetting circuit breakers: {str(e)}", error_type=type(e).__name__)
        raise HTTPException(status_code=500, detail="Error resetting circuit breakers")


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for real-time streaming"""
    connection_id = None
    try:
        session = session_manager.get_session(session_id)
        if not session:
            print(f"📝 Creating session in backend for WebSocket: {session_id}")
            session = session_manager.get_or_create_session(session_id)

        connection_id = await manager.connect(websocket, session_id)
        error_handler._log_structured("info", "WebSocket connection established", session_id=session_id, connection_id=connection_id)

        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                print(f"📨 WebSocket received: {data}")
                try:
                    message = json.loads(data)
                    if message.get("type") == "ping":
                        await manager.send_to_connection(connection_id, {"type": "pong", "timestamp": datetime.now().isoformat()})
                    elif message.get("type") == "heartbeat":
                        if connection_id in manager.connections:
                            manager.connections[connection_id].last_ping = datetime.now()
                except json.JSONDecodeError:
                    error_handler._log_structured("warning", "Received malformed JSON from WebSocket client", session_id=session_id, connection_id=connection_id)

            except asyncio.TimeoutError:
                print(f"⏰ WebSocket timeout - sending ping to {session_id}")
                try:
                    await websocket.send_text('{"type":"ping"}')
                except Exception as e:
                    print(f"❌ Failed to send ping: {e}")
                    break
                if not await manager.ping_connection(connection_id):
                    break

    except WebSocketDisconnect:
        error_handler._log_structured("info", "WebSocket client disconnected", session_id=session_id, connection_id=connection_id)
    except Exception as e:
        error_handler._log_structured("error", f"WebSocket error: {str(e)}", session_id=session_id, connection_id=connection_id, error_type=type(e).__name__)
    finally:
        if connection_id:
            manager.disconnect(connection_id, "endpoint_cleanup")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=5000,
        reload=True,
        log_level="info"
    )