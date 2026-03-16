"""
Data models for the Multi-LLM Broadcast Workspace backend
Using Pydantic for request/response validation and type safety
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Union
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, ConfigDict


class ProvenanceInfo(BaseModel):
    source_model: str
    source_pane_id: str
    transfer_timestamp: datetime
    content_hash: str


class MessageMetadata(BaseModel):
    token_count: Optional[int] = None
    cost: Optional[float] = None
    latency: Optional[int] = None
    extra: Dict[str, Any] = Field(default_factory=dict)

# RAG Feature Models
class SearchPrivateRequest(BaseModel):
    query: str
    top_k: int = 4

class RAGQueryRequest(BaseModel):
    query: str
    model_id: str = "google/gemini-2.5-pro"  # Default LiteLLM format model ID


class Message(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    role: Literal["user", "assistant", "system"]
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)
    provenance: Optional[ProvenanceInfo] = None
    metadata: Optional[MessageMetadata] = None
    images: Optional[List[str]] = None  # List of base64 encoded image strings


class ModelInfo(BaseModel):
    id: str
    name: str
    provider: str
    max_tokens: int
    cost_per_1k_tokens: float
    supports_streaming: bool = True
    supports_vision: bool = False


class ModelSelection(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    
    provider_id: str
    model_id: str
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None


class PaneMetrics(BaseModel):
    token_count: int = 0
    cost: float = 0.0
    latency: int = 0
    request_count: int = 0


class SessionMetrics(BaseModel):
    total_tokens: int = 0
    total_cost: float = 0.0
    average_latency: float = 0.0
    active_requests: int = 0


class ChatPane(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    
    id: str = Field(default_factory=lambda: str(uuid4()))
    model_info: ModelInfo
    messages: List[Message] = Field(default_factory=list)
    is_streaming: bool = False
    metrics: PaneMetrics = Field(default_factory=PaneMetrics)


class Session(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    panes: List[ChatPane] = Field(default_factory=list)
    total_cost: float = 0.0
    status: Literal["active", "completed", "archived"] = "active"


# WebSocket Event Models
class TokenData(BaseModel):
    token: str
    position: int


class FinalData(BaseModel):
    content: str
    finish_reason: str
    message_id: Optional[str] = None  # Backend-generated message ID


class MeterData(BaseModel):
    tokens_used: int
    cost: float
    latency: int


class ErrorData(BaseModel):
    message: str
    code: Optional[str] = None
    retryable: bool = False


class StatusData(BaseModel):
    status: str
    message: Optional[str] = None


class StreamEvent(BaseModel):
    type: Literal["token", "final", "meter", "error", "status"]
    pane_id: str
    data: Union[TokenData, FinalData, MeterData, ErrorData, StatusData]
    timestamp: datetime = Field(default_factory=datetime.now)


# API Request/Response Models
class BroadcastRequest(BaseModel):
    prompt: str
    images: Optional[List[str]] = None
    models: List[ModelSelection]
    session_id: str


class BroadcastResponse(BaseModel):
    session_id: str
    pane_ids: List[str]
    status: str
    user_message_ids: Dict[str, str] = {}  # pane_id -> user_message_id mapping


class SendToRequest(BaseModel):
    source_pane_id: str
    target_pane_id: str
    message_ids: List[str]
    session_id: str
    transfer_mode: str = "append"  # "append", "replace", "summarize"
    additional_context: Optional[str] = None
    preserve_roles: bool = True
    summary_instructions: Optional[str] = None


class SendToResponse(BaseModel):
    success: bool
    transferred_count: int
    target_pane_id: str


class SummaryRequest(BaseModel):
    pane_ids: List[str]
    session_id: str
    summary_types: List[Literal["executive", "technical", "bullet"]] = [
        "executive", "technical", "bullet"
    ]


class SummaryResponse(BaseModel):
    summary_pane_id: str
    summaries: Dict[str, str]
    source_panes: List[str]


class HealthResponse(BaseModel):
    status: str
    service: str
    timestamp: datetime = Field(default_factory=datetime.now)


class HistoryResponse(BaseModel):
    sessions: List[Session]
    total_count: int
    page: int
    page_size: int


# Pipeline Template Models
class PipelineStep(BaseModel):
    order: int
    prompt: str
    target_models: List[str]
    dependencies: Optional[List[str]] = None


class ModelConfiguration(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    
    model_id: str
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    extra_params: Dict[str, Any] = Field(default_factory=dict)


class PipelineTemplate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    description: Optional[str] = None
    steps: List[PipelineStep]
    model_configurations: List[ModelConfiguration]
    created_at: datetime = Field(default_factory=datetime.now)
    usage_count: int = 0


class TemplateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    session_id: str
    pane_ids: List[str]


class TemplateResponse(BaseModel):
    template_id: str
    name: str
    steps_count: int