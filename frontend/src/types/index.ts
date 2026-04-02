// Core data models and interfaces for the Multi-LLM Broadcast Workspace

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
  provenance?: ProvenanceInfo;
  metadata?: MessageMetadata;
  images?: string[]; // Array of base64 encoded image strings
}

export interface ProvenanceInfo {
  sourceModel: string;
  sourcePaneId: string;
  transferTimestamp: Date;
  contentHash: string;
}

export interface MessageMetadata {
  tokenCount?: number;
  cost?: number;
  latency?: number;
  [key: string]: any;
}

export interface ModelInfo {
  id: string;
  name: string;
  provider: string;
  maxTokens: number;
  costPer1kTokens: number;
  supportsStreaming: boolean;
}

export interface ModelSelection {
  providerId: string;
  modelId: string;
  temperature?: number;
  maxTokens?: number;
}

export interface ChatPane {
  id: string;
  modelInfo: ModelInfo;
  messages: Message[];
  isStreaming: boolean;
  metrics: PaneMetrics;
  personaId?: string; // Add persona override
}

export interface PaneMetrics {
  tokenCount: number;
  cost: number;
  latency: number;
  requestCount: number;
}

export interface SessionMetrics {
  totalTokens: number;
  totalCost: number;
  averageLatency: number;
  activeRequests: number;
}

export interface Session {
  id: string;
  name?: string;
  createdAt: Date;
  updatedAt: Date;
  panes: ChatPane[];
  totalCost: number;
  status: 'active' | 'completed' | 'archived';
}

export interface StreamEvent {
  type: 'token' | 'final' | 'meter' | 'error' | 'status';
  pane_id: string;
  data: TokenData | FinalData | MeterData | ErrorData | StatusData;
  timestamp: Date;
}

export interface TokenData {
  token: string;
  position: number;
}

export interface FinalData {
  content: string;
  finishReason: string;
  message_id?: string; // Backend-generated message ID
}

export interface MeterData {
  tokensUsed: number;
  cost: number;
  latency: number;
}

export interface ErrorData {
  message: string;
  code?: string;
  retryable: boolean;
}

export interface StatusData {
  status: string;
  message?: string;
}

export interface BroadcastRequest {
  prompt: string;
  images?: string[];
  models: ModelSelection[];
  sessionId: string;
}

export interface BroadcastResponse {
  sessionId: string;
  paneIds: string[];
  status: string;
  user_message_ids?: { [paneId: string]: string }; // pane_id -> user_message_id mapping
}

export interface TransferContent {
  messages: Message[];
  provenance: ProvenanceInfo;
}

export interface SelectedContent {
  messageIds: string[];
  text: string;
}

export interface PipelineTemplate {
  id: string;
  name: string;
  description?: string;
  steps: PipelineStep[];
  modelConfigurations: ModelConfiguration[];
  createdAt: Date;
  usageCount: number;
}

export interface PipelineStep {
  order: number;
  prompt: string;
  targetModels: string[];
  dependencies?: string[];
}

export interface ModelConfiguration {
  modelId: string;
  temperature: number;
  maxTokens: number;
  [key: string]: any;
}

export interface CostLimits {
  sessionLimit: number;
  dailyLimit: number;
  warningThreshold: number;
}

export interface ConversationHistory {
  sessionId: string;
  name: string;
  timestamp: Date;
  messageCount: number;
  totalCost: number;
}