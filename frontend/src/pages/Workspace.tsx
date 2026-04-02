import React, { useEffect, useState, useMemo } from 'react';
import { useAppStore } from '../store';
import { FloatingModelSelector } from '../components/FloatingModelSelector';
import { FloatingToolbar } from '../components/FloatingToolbar';
import { FloatingSessionMetrics } from '../components/FloatingSessionMetrics/FloatingSessionMetrics';
import { PaneGrid } from '../components/PaneGrid';
import { SendToMenu } from '../components/SendToMenu';
import { DiffViewer } from '../components/DiffViewer/DiffViewer';
import { CodeCompareArena } from '../components/CodeCompareArena/CodeCompareArena';
import { ModelInfo, SelectedContent, TransferContent } from '../types';
import { apiService } from '../services/api';
import './Workspace.css';

export const Workspace: React.FC = () => {
  const {
    currentSession, createSession, activePanes, availableModels,
    isComparing, selectedPanes, setComparing, setSelectedPanes,
    refreshSessionFromBackend, addPane, addPaneWithId,
    setAvailableModels, updatePaneMessages, updatePaneStreaming
  } = useAppStore();

  const [isStreaming, setIsStreaming] = useState(false);
  const [sendToMenuVisible, setSendToMenuVisible] = useState(false);
  const [sessionMetricsVisible, setSessionMetricsVisible] = useState(false);
  const [arenaVisible, setArenaVisible] = useState(false);
  const [sendToData, setSendToData] = useState<{
    sourcePane: string;
    selectedContent: SelectedContent;
  } | null>(null);

  useEffect(() => {
    if (!currentSession) createSession();
  }, [currentSession, createSession]);

  useEffect(() => {
    if (currentSession) console.log(`🔌 Ensuring WebSocket for session: ${currentSession.id}`);
  }, [currentSession]);

  useEffect(() => {
    const setFallbackModels = () => {
      console.warn('⚠️ Using fallback models');
      setAvailableModels([
        { id: 'google:gemini-2.5-flash', name: 'Gemini 2.5 Flash', provider: 'google', maxTokens: 1048576, costPer1kTokens: 0.0007, supportsStreaming: true },
        { id: 'google:gemini-2.0-flash', name: 'Gemini 2.0 Flash', provider: 'google', maxTokens: 1048576, costPer1kTokens: 0.0001, supportsStreaming: true },
        { id: 'google:gemini-2.0-flash-lite', name: 'Gemini 2.0 Flash Lite', provider: 'google', maxTokens: 1048576, costPer1kTokens: 0.000075, supportsStreaming: true },
        { id: 'google:gemini-1.5-flash', name: 'Gemini 1.5 Flash', provider: 'google', maxTokens: 1048576, costPer1kTokens: 0.000075, supportsStreaming: true },
        { id: 'groq:llama-3.1-8b-instant', name: 'Llama 3.1 8B Instant', provider: 'groq', maxTokens: 8192, costPer1kTokens: 0.0001, supportsStreaming: true },
        { id: 'groq:llama-3.3-70b-versatile', name: 'Llama 3.3 70B Versatile', provider: 'groq', maxTokens: 32768, costPer1kTokens: 0.0005, supportsStreaming: true },
        { id: 'groq:qwen-qwq-32b', name: 'Qwen 3 32B', provider: 'groq', maxTokens: 32768, costPer1kTokens: 0.0008, supportsStreaming: true },
        { id: 'groq:compound', name: 'Compound', provider: 'groq', maxTokens: 4096, costPer1kTokens: 0.0002, supportsStreaming: true }
      ]);
    };

    const fetchModels = async () => {
      try {
        const response = await fetch('http://localhost:5000/models');
        if (response.ok) {
          const data = await response.json();
          if (data.models && Array.isArray(data.models) && data.models.length > 0) {
            const transformedModels = data.models.map((model: any) => ({
              id: model.id, name: model.name, provider: model.provider,
              maxTokens: model.max_tokens, costPer1kTokens: model.cost_per_1k_tokens,
              supportsStreaming: model.supports_streaming
            }));
            setAvailableModels(transformedModels);
            console.log(`✅ Loaded ${transformedModels.length} models from backend`);
          } else {
            setFallbackModels();
          }
        } else {
          setFallbackModels();
        }
      } catch (error) {
        console.warn('⚠️ Could not reach backend, using fallback models', error);
        setFallbackModels();
      }
    };

    fetchModels();
  }, [setAvailableModels]);

  const handleModelSelect = async (model: ModelInfo, prompt?: string, images?: string[]) => {
    await handleMultiModelSelect([model], prompt || '', images);
  };

  const handleSendMessage = async (paneId: string, message: string, images?: string[]) => {
    if (!currentSession) return;
    const pane = activePanes[paneId];
    if (!pane) return;

    updatePaneMessages(paneId, {
      id: `msg-${Date.now()}-user`, role: 'user' as const,
      content: message, images, timestamp: new Date()
    });
    updatePaneStreaming(paneId, true);

    try {
      const response = await fetch(`http://localhost:5000/chat/${paneId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: currentSession.id, message, images })
      });
      if (!response.ok) {
        console.error('Failed to send message:', response.statusText);
        updatePaneStreaming(paneId, false);
      }
    } catch (error) {
      console.error('Error sending message:', error);
      updatePaneStreaming(paneId, false);
    }
  };

  const handleMultiModelSelect = async (models: ModelInfo[], prompt: string, images?: string[]) => {
    if (!currentSession || models.length === 0) return;
    setIsStreaming(true);

    try {
      const response = await fetch('http://localhost:5000/broadcast', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: currentSession.id, prompt, images,
          models: models.map(model => ({
            provider_id: model.provider,
            model_id: model.id.includes(':') ? model.id.split(':').slice(1).join(':') : model.id,
            temperature: 0.7, max_tokens: 1000
          }))
        })
      });

      if (response.ok) {
        const result = await response.json();
        result.pane_ids.forEach((paneId: string, index: number) => {
          const modelInfo = models[index];
          if (modelInfo && !activePanes[paneId]) {
            addPaneWithId(paneId, modelInfo);
            const userMessageId = result.user_message_ids?.[paneId];
            if (userMessageId) {
              updatePaneMessages(paneId, {
                id: userMessageId, role: 'user' as const,
                content: prompt, images, timestamp: new Date()
              });
            }
          }
        });
      }
    } catch (error) {
      console.error('Error broadcasting:', error);
    } finally {
      setIsStreaming(false);
    }
  };

  const handleCompareToggle = (paneIds: [string, string] | null) => {
    setSelectedPanes(paneIds);
    setComparing(!!paneIds);
  };

  const handlePaneAction = (action: any) => {
    if (action.type === 'sendTo') {
      setSendToData({ sourcePane: action.paneId, selectedContent: action.data || { messageIds: [], text: '' } });
      setSendToMenuVisible(true);
    }
  };

  const handleSendTo = async (targetPaneId: string, content: TransferContent, options: {
    transferMode: 'append' | 'replace' | 'summarize';
    additionalContext?: string;
    preserveRoles: boolean;
    summaryInstructions?: string;
  }) => {
    if (!sendToData) return;
    try {
      const result = await apiService.sendToPane({
        sourceId: sendToData.sourcePane, targetId: targetPaneId,
        content, sessionId: currentSession?.id || 'default-session',
        transferMode: options.transferMode, additionalContext: options.additionalContext,
        preserveRoles: options.preserveRoles, summaryInstructions: options.summaryInstructions,
        selectedMessageIds: sendToData.selectedContent.messageIds
      });
      if (result.success && currentSession?.id) {
        await refreshSessionFromBackend(currentSession.id);
      }
    } catch (error) {
      console.error('❌ Failed to transfer content:', error);
    }
    setSendToMenuVisible(false);
    setSendToData(null);
  };

  const handleBroadcastToActive = async (paneIds: string[], prompt: string) => {
    if (!currentSession) return;

    paneIds.forEach((paneId, index) => {
      updatePaneMessages(paneId, {
        id: `msg-${Date.now()}-${index}-user`, role: 'user' as const,
        content: prompt, timestamp: new Date()
      });
      updatePaneStreaming(paneId, true);
    });

    await Promise.all(paneIds.map(async (paneId) => {
      const pane = activePanes[paneId];
      if (!pane) return;
      try {
        const response = await fetch(`${apiService['baseUrl']}/chat/${paneId}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: currentSession.id, message: prompt })
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
      } catch (error) {
        updatePaneMessages(paneId, {
          id: `msg-${Date.now()}-error-${paneId}`, role: 'assistant' as const,
          content: `Error: ${error instanceof Error ? error.message : 'Unknown error'}`,
          timestamp: new Date()
        });
        updatePaneStreaming(paneId, false);
      }
    }));
  };

  const handleArrangeWindows = () => (window as any).arrangeWindows?.();
  const handleMinimizeAll   = () => (window as any).minimizeAllWindows?.();
  const handleCloseAll      = () => (window as any).closeAllWindows?.();

  const availablePanes = Object.values(activePanes);
  const panesForComparison = useMemo(() => availablePanes.length > 0 ? availablePanes : [], [availablePanes]);

  return (
    <div className="workspace">

      <div className="top-right-controls">
        <button
          className="session-metrics-toggle"
          onClick={() => setSessionMetricsVisible(!sessionMetricsVisible)}
          title="Toggle Session Metrics"
        >
          📊
        </button>
        <FloatingToolbar
          activePanes={availablePanes}
          isComparing={isComparing}
          selectedPanes={selectedPanes}
          onCompareToggle={handleCompareToggle}
          onArrangeWindows={handleArrangeWindows}
          onMinimizeAll={handleMinimizeAll}
          onCloseAll={handleCloseAll}
          onBroadcastToActive={handleBroadcastToActive}
          onOpenArena={() => setArenaVisible(true)}
        />
      </div>

      <FloatingSessionMetrics
        isVisible={sessionMetricsVisible}
        onToggle={() => setSessionMetricsVisible(!sessionMetricsVisible)}
      />

      <CodeCompareArena
        isVisible={arenaVisible}
        onClose={() => setArenaVisible(false)}
      />

      <FloatingModelSelector
        availableModels={availableModels}
        onModelSelect={handleModelSelect}
        onMultiModelSelect={handleMultiModelSelect}
        isStreaming={isStreaming}
      />

      <div className={`workspace-content ${isComparing ? 'comparison-active' : ''}`}>
        <PaneGrid
          onPaneAction={handlePaneAction}
          onSendMessage={handleSendMessage}
          isCompareMode={isComparing}
          selectedPanes={selectedPanes}
          onArrangeWindows={handleArrangeWindows}
          onMinimizeAll={handleMinimizeAll}
          onCloseAll={handleCloseAll}
        />
        {isComparing && selectedPanes && selectedPanes.length >= 2 && (
          <DiffViewer panes={panesForComparison} selectedPanes={selectedPanes} />
        )}
      </div>

      {sendToMenuVisible && sendToData && (
        <SendToMenu
          sourcePane={sendToData.sourcePane}
          selectedContent={sendToData.selectedContent}
          availableTargets={availablePanes}
          onSendTo={handleSendTo}
          onClose={() => { setSendToMenuVisible(false); setSendToData(null); }}
          isVisible={sendToMenuVisible}
        />
      )}
    </div>
  );
};
