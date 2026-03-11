import {
  BroadcastRequest,
  BroadcastResponse,
  ModelInfo,
  TransferContent,
  PipelineTemplate
} from '../types';

class ApiService {
  private baseUrl: string;

  constructor() {
    const protocol = import.meta.env.VITE_BACKEND_PROTOCOL || 'http';
    const host = import.meta.env.VITE_BACKEND_HOST || 'localhost';
    const port = import.meta.env.VITE_BACKEND_PORT || '5000';
    this.baseUrl = `${protocol}://${host}:${port}`;
    console.log('🔗 API Service configured:', this.baseUrl);
  }

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    const config: RequestInit = {
      headers: { 'Content-Type': 'application/json', ...options.headers },
      ...options,
    };
    try {
      const response = await fetch(url, config);
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
      return await response.json();
    } catch (error) {
      console.error(`API request failed: ${endpoint}`, error);
      throw error;
    }
  }

  async healthCheck(): Promise<{ status: string; timestamp: string }> {
    return this.request('/health');
  }

  async getAvailableModels(): Promise<ModelInfo[]> {
    const response = await this.request<{ models: ModelInfo[] }>('/models');
    // No filtering — show all models the backend provides
    return response.models || [];
  }

  async createBroadcast(request: BroadcastRequest): Promise<BroadcastResponse> {
    return this.request('/broadcast', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  async sendToPane(request: {
    sourceId: string;
    targetId: string;
    content: TransferContent;
    sessionId: string;
    transferMode?: 'append' | 'replace' | 'summarize';
    additionalContext?: string;
    preserveRoles?: boolean;
    summaryInstructions?: string;
    selectedMessageIds?: string[];
  }): Promise<{ success: boolean; transferred_count: number; target_pane_id: string }> {
    let messageIds: string[];
    if (request.selectedMessageIds) {
      messageIds = request.selectedMessageIds;
    } else {
      messageIds = request.content.messages
        .map(msg => {
          const match = msg.id.match(/^(.+)-transfer-\d+$/);
          return match ? match[1] : msg.id;
        })
        .filter(id => !id.startsWith('context-'));
    }

    const backendRequest = {
      source_pane_id: request.sourceId,
      target_pane_id: request.targetId,
      message_ids: messageIds,
      session_id: request.sessionId,
      transfer_mode: request.transferMode || 'append',
      additional_context: request.additionalContext || null,
      preserve_roles: request.preserveRoles !== false,
      summary_instructions: request.summaryInstructions || null
    };

    return this.request('/send-to', {
      method: 'POST',
      body: JSON.stringify(backendRequest),
    });
  }

  async generateSummary(request: {
    paneIds: string[];
    format: 'executive' | 'technical' | 'bullet';
    sessionId: string;
  }): Promise<{ summary: string; paneId: string }> {
    return this.request('/summarize', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  async getSession(sessionId: string): Promise<any> {
    return this.request(`/sessions/${sessionId}`);
  }

  async getSessionHistory(sessionId: string): Promise<{ session: any; messages: any[] }> {
    return this.request(`/sessions/${sessionId}/history`);
  }

  async createPipelineTemplate(template: Omit<PipelineTemplate, 'id' | 'createdAt' | 'usageCount'>): Promise<PipelineTemplate> {
    return this.request('/templates', { method: 'POST', body: JSON.stringify(template) });
  }

  async getPipelineTemplates(): Promise<PipelineTemplate[]> {
    return this.request('/templates');
  }

  async deletePipelineTemplate(templateId: string): Promise<{ success: boolean }> {
    return this.request(`/templates/${templateId}`, { method: 'DELETE' });
  }

  async executePipelineTemplate(templateId: string, sessionId: string): Promise<BroadcastResponse> {
    return this.request(`/templates/${templateId}/execute`, {
      method: 'POST',
      body: JSON.stringify({ sessionId }),
    });
  }
}

export const apiService = new ApiService();