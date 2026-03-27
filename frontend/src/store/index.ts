import { create } from 'zustand';
import { devtools } from 'zustand/middleware';
import { 
  Session, 
  ChatPane, 
  ModelInfo, 
  Message, 
  TransferContent, 
  PaneMetrics,
  ConversationHistory,
  PipelineTemplate,
  StreamEvent,
  TokenData,
  FinalData
} from '../types';
import { WebSocketClient } from '../services/websocket';

// Window Manager State (for external library integration)
export interface WindowManagerState {
  layout: 'grid' | 'tabs' | 'split';
  resizable: boolean;
  closable: boolean;
  draggable: boolean;
  windows: Record<string, any>; // WinBox instances
}

// Global WebSocket Manager
class GlobalWebSocketManager {
  private static instance: GlobalWebSocketManager;
  private wsClients: Map<string, WebSocketClient> = new Map();
  private eventHandlers: Map<string, (event: StreamEvent) => void> = new Map();

  static getInstance(): GlobalWebSocketManager {
    if (!GlobalWebSocketManager.instance) {
      GlobalWebSocketManager.instance = new GlobalWebSocketManager();
    }
    return GlobalWebSocketManager.instance;
  }

  async getOrCreateClient(sessionId: string): Promise<WebSocketClient> {
    if (this.wsClients.has(sessionId)) {
      return this.wsClients.get(sessionId)!;
    }

    console.log(`🔌 Creating global WebSocket client for session: ${sessionId}`);
    const client = new WebSocketClient(sessionId);
    
    // Set up event handler
    const eventHandler = (event: StreamEvent) => {
      console.log('Global WebSocket event:', event);
      
      // Update store directly
      const store = useAppStore.getState();
      
      if (event.type === 'token') {
        console.log('🎯 Processing token event for pane:', event.pane_id, 'token:', (event.data as TokenData).token);
        
        // Accumulate tokens into streaming content
        const pane = store.activePanes[event.pane_id];
        if (pane) {
          const lastMessage = pane.messages[pane.messages.length - 1];
          const currentContent = (lastMessage && lastMessage.role === 'assistant' && lastMessage.id.startsWith('streaming-')) 
            ? lastMessage.content + (event.data as TokenData).token 
            : (event.data as TokenData).token;
          
          store.updateStreamingContent(event.pane_id, currentContent);
          console.log('✅ Token accumulated for pane:', event.pane_id);
        } else {
          console.log('❌ Pane NOT found for ID:', event.pane_id);
        }
      } else if (event.type === 'final') {
        console.log('🎯 Processing final event for pane:', event.pane_id, 'content:', (event.data as FinalData).content);
        console.log('🎯 Current active panes:', Object.keys(store.activePanes));
        
        // Finalize the streaming message instead of adding a new one
        const finalData = event.data as FinalData;
        store.finalizeStreamingMessage(event.pane_id, finalData.content, finalData.message_id);
        
        // Check if pane exists and has messages
        const pane = store.activePanes[event.pane_id];
        if (pane) {
          console.log('✅ Pane found! Messages count:', pane.messages.length);
        } else {
          console.log('❌ Pane NOT found for ID:', event.pane_id);
        }
      } else if (event.type === 'meter') {
        console.log('🎯 Processing meter event for pane:', event.pane_id, 'data:', event.data);
        
        // Update pane metrics with token count, cost, and latency
        const meterData = event.data as any;
        const metrics = {
          tokenCount: meterData.tokens_used || 0,
          cost: meterData.cost || 0,
          latency: meterData.latency || 0
        };
        
        store.updatePaneMetrics(event.pane_id, metrics);
        console.log('✅ Metrics updated for pane:', event.pane_id, metrics);
      }
    };

    client.onEvent(eventHandler);
    this.eventHandlers.set(sessionId, eventHandler);
    
    try {
      await client.connect();
      console.log(`✅ Global WebSocket connected for session: ${sessionId}`);
      this.wsClients.set(sessionId, client);
      return client;
    } catch (error) {
      console.error(`❌ Global WebSocket connection failed for session ${sessionId}:`, error);
      throw error;
    }
  }

  disconnectSession(sessionId: string) {
    const client = this.wsClients.get(sessionId);
    if (client) {
      console.log(`🧹 Disconnecting global WebSocket for session: ${sessionId}`);
      client.disconnect();
      this.wsClients.delete(sessionId);
      this.eventHandlers.delete(sessionId);
    }
  }

  disconnectAll() {
    console.log('🧹 Disconnecting all global WebSocket connections');
    for (const [_sessionId, client] of this.wsClients) {
      client.disconnect();
    }
    this.wsClients.clear();
    this.eventHandlers.clear();
  }
}

export interface AppState {
  // Session Management
  currentSession: Session | null;
  sessions: Session[];
  
  // Global WebSocket Management
  wsManager: GlobalWebSocketManager;
  
  // Pane Management
  activePanes: Record<string, ChatPane>;
  windowManagerState: WindowManagerState;
  
  // UI State
  isComparing: boolean;
  selectedPanes: [string, string] | null;
  metricsVisible: boolean;
  
  // History & Templates
  conversationHistory: ConversationHistory[];
  pipelineTemplates: PipelineTemplate[];
  
  // Available Models
  availableModels: ModelInfo[];
  
  // File Metadata
  sessionFilesMap: Record<string, string>;
  
  // Actions
  addSessionFile: (uri: string, name: string) => void;
  setSessionFilesMap: (map: Record<string, string>) => void;
  createSession: () => void;
  setCurrentSession: (session: Session) => void;
  refreshSessionFromBackend: (sessionId: string) => Promise<void>;
  initializeWebSocket: (sessionId: string) => Promise<void>;
  addPane: (modelInfo: ModelInfo) => void;
  addPaneWithId: (paneId: string, modelInfo: ModelInfo) => void;
  removePane: (paneId: string) => void;
  updatePaneMessages: (paneId: string, message: Message) => void;
  updateStreamingContent: (paneId: string, content: string) => void;
  finalizeStreamingMessage: (paneId: string, finalContent: string, messageId?: string) => void;
  updatePaneStreaming: (paneId: string, isStreaming: boolean) => void;
  updatePaneMetrics: (paneId: string, metrics: Partial<PaneMetrics>) => void;
  transferContent: (sourceId: string, targetId: string, content: TransferContent, mode?: 'append' | 'replace' | 'summarize') => void;
  
  // Comparison Actions
  setComparing: (comparing: boolean) => void;
  setSelectedPanes: (panes: [string, string] | null) => void;
  
  // UI Actions
  setMetricsVisible: (visible: boolean) => void;
  
  // Window Manager Actions
  updateWindowManagerState: (state: Partial<WindowManagerState>) => void;
  registerWindow: (paneId: string, window: any) => void;
  unregisterWindow: (paneId: string) => void;
  
  // History Actions
  addToHistory: (history: ConversationHistory) => void;
  
  // Template Actions
  addTemplate: (template: PipelineTemplate) => void;
  removeTemplate: (templateId: string) => void;
  
  // Model Actions
  setAvailableModels: (models: ModelInfo[]) => void;
}

const generateId = () => Math.random().toString(36).substr(2, 9);

export const useAppStore = create<AppState>()(
  devtools(
    (set, get) => ({
      // Initial State
      currentSession: null,
      sessions: [],
      wsManager: GlobalWebSocketManager.getInstance(),
      activePanes: {},
      windowManagerState: {
        layout: 'grid',
        resizable: true,
        closable: true,
        draggable: true,
        windows: {}
      },
      isComparing: false,
      selectedPanes: null,
      metricsVisible: true,
      conversationHistory: [],
      pipelineTemplates: [],
      availableModels: [],
      sessionFilesMap: {},
      
      // File Metadata Actions
      addSessionFile: (uri, name) => {
        set((state) => ({
          sessionFilesMap: { ...state.sessionFilesMap, [uri]: name }
        }));
      },
      setSessionFilesMap: (map) => {
        set((state) => ({
          sessionFilesMap: { ...state.sessionFilesMap, ...map }
        }));
      },
      
      // Session Actions
      createSession: () => {
        const newSession: Session = {
          id: generateId(),
          name: `Session ${new Date().toLocaleString()}`,
          createdAt: new Date(),
          updatedAt: new Date(),
          panes: [],
          totalCost: 0,
          status: 'active'
        };
        
        set((state) => ({
          currentSession: newSession,
          sessions: [...state.sessions, newSession]
        }));

        // Initialize WebSocket for the new session
        get().initializeWebSocket(newSession.id);
      },

      initializeWebSocket: async (sessionId: string) => {
        try {
          const { wsManager } = get();
          await wsManager.getOrCreateClient(sessionId);
          console.log(`✅ WebSocket initialized for session: ${sessionId}`);
        } catch (error) {
          console.error(`❌ Failed to initialize WebSocket for session ${sessionId}:`, error);
        }
      },
      
      setCurrentSession: (session) => {
        set({ currentSession: session });
      },

      refreshSessionFromBackend: async (sessionId: string) => {
        try {
          const fileRes = await fetch(`http://localhost:5000/session/${sessionId}/files`);
          if (fileRes.ok) {
            const fileData = await fileRes.json();
            const map: Record<string, string> = {};
            fileData.files?.forEach((f: any) => { map[f.uri] = f.originalName || f.name; });
            set((state) => ({ sessionFilesMap: { ...state.sessionFilesMap, ...map } }));
          }
        } catch (e) { console.error('Failed to fetch session files map:', e); }

        try {
          const { apiService } = await import('../services/api');
          const backendSession = await apiService.getSession(sessionId);
          
          if (backendSession) {
            // Update the current session with backend data
            set((state) => {
              const updatedActivePanes: { [key: string]: any } = {};
              
              // Convert backend panes to frontend format
              backendSession.panes?.forEach((pane: any) => {
                updatedActivePanes[pane.id] = {
                  id: pane.id,
                  modelInfo: pane.model_info,
                  messages: pane.messages || [],
                  isStreaming: false,
                  metrics: pane.metrics || { tokenCount: 0, cost: 0, latency: 0 }
                };
              });
              
              return {
                ...state,
                currentSession: {
                  id: backendSession.id,
                  name: backendSession.name || `Session ${backendSession.id}`,
                  createdAt: new Date(backendSession.created_at),
                  updatedAt: new Date(backendSession.updated_at),
                  panes: backendSession.panes || [],
                  totalCost: backendSession.total_cost || 0,
                  status: backendSession.status || 'active'
                },
                activePanes: updatedActivePanes
              };
            });
            
            console.log(`✅ Session refreshed from backend: ${sessionId}`);
          }
        } catch (error) {
          console.error(`❌ Failed to refresh session from backend: ${error}`);
        }
      },
      
      // Pane Actions
      addPane: (modelInfo) => {
        const paneId = generateId();
        const newPane: ChatPane = {
          id: paneId,
          modelInfo,
          messages: [],
          isStreaming: false,
          metrics: {
            tokenCount: 0,
            cost: 0,
            latency: 0,
            requestCount: 0
          }
        };
        
        set((state) => ({
          activePanes: {
            ...state.activePanes,
            [paneId]: newPane
          }
        }));
        
        // Update current session if exists
        const currentSession = get().currentSession;
        if (currentSession) {
          const updatedSession = {
            ...currentSession,
            panes: [...currentSession.panes, newPane],
            updatedAt: new Date()
          };
          
          set((state) => ({
            currentSession: updatedSession,
            sessions: state.sessions.map(s => 
              s.id === currentSession.id ? updatedSession : s
            )
          }));
        }
      },

      addPaneWithId: (paneId, modelInfo) => {
        console.log('➕ addPaneWithId called for pane:', paneId, 'model:', modelInfo.name);
        const newPane: ChatPane = {
          id: paneId,
          modelInfo,
          messages: [],
          isStreaming: true,
          metrics: {
            tokenCount: 0,
            cost: 0,
            latency: 0,
            requestCount: 0
          }
        };
        
        set((state) => ({
          activePanes: {
            ...state.activePanes,
            [paneId]: newPane
          }
        }));
        
        // Update current session if exists
        const currentSession = get().currentSession;
        if (currentSession) {
          const updatedSession = {
            ...currentSession,
            panes: [...currentSession.panes, newPane],
            updatedAt: new Date()
          };
          
          set((state) => ({
            currentSession: updatedSession,
            sessions: state.sessions.map(s => 
              s.id === updatedSession.id ? updatedSession : s
            )
          }));
        }
      },
      
      removePane: (paneId) => {
        set((state) => {
          const { [paneId]: removed, ...remainingPanes } = state.activePanes;
          return { activePanes: remainingPanes };
        });
        
        // Update current session
        const currentSession = get().currentSession;
        if (currentSession) {
          const updatedSession = {
            ...currentSession,
            panes: currentSession.panes.filter(p => p.id !== paneId),
            updatedAt: new Date()
          };
          
          set((state) => ({
            currentSession: updatedSession,
            sessions: state.sessions.map(s => 
              s.id === currentSession.id ? updatedSession : s
            )
          }));
        }
      },
      
      updatePaneMessages: (paneId, message) => {
        set((state) => {
          const pane = state.activePanes[paneId];
          if (!pane) {
            console.log('❌ Pane not found for ID:', paneId, 'Available panes:', Object.keys(state.activePanes));
            return state;
          }
          
          console.log('✅ Found pane, current messages:', pane.messages.length, 'Adding message:', message.content.substring(0, 50));
          
          const updatedPane = {
            ...pane,
            messages: [...pane.messages, message]
          };
          
          console.log('✅ Updated pane, new message count:', updatedPane.messages.length);
          
          return {
            activePanes: {
              ...state.activePanes,
              [paneId]: updatedPane
            }
          };
        });
      },

      updateStreamingContent: (paneId, content) => {
        console.log('🔄 updateStreamingContent called for pane:', paneId, 'content length:', content.length);
        set((state) => {
          const pane = state.activePanes[paneId];
          if (!pane) {
            console.log('❌ updateStreamingContent: Pane not found for ID:', paneId);
            return state;
          }
          
          const messages = [...pane.messages];
          const lastMessage = messages[messages.length - 1];
          
          if (lastMessage && lastMessage.role === 'assistant' && lastMessage.id.startsWith('streaming-')) {
            // Update existing streaming message
            messages[messages.length - 1] = {
              ...lastMessage,
              content: content
            };
          } else {
            // Create new streaming message
            messages.push({
              id: `streaming-${Date.now()}`,
              role: 'assistant' as const,
              content: content,
              timestamp: new Date()
            });
          }
          
          return {
            activePanes: {
              ...state.activePanes,
              [paneId]: {
                ...pane,
                messages
              }
            }
          };
        });
      },

      finalizeStreamingMessage: (paneId, finalContent, messageId) => {
        console.log('🏁 finalizeStreamingMessage called for pane:', paneId, 'content length:', finalContent.length, 'messageId:', messageId);
        set((state) => {
          const pane = state.activePanes[paneId];
          if (!pane) {
            console.log('❌ finalizeStreamingMessage: Pane not found for ID:', paneId);
            return state;
          }
          
          const messages = [...pane.messages];
          const lastMessage = messages[messages.length - 1];
          
          if (lastMessage && lastMessage.role === 'assistant' && lastMessage.id.startsWith('streaming-')) {
            // Convert streaming message to final message using backend-provided ID
            messages[messages.length - 1] = {
              ...lastMessage,
              id: messageId || `final-${Date.now()}`, // Use backend ID if available
              content: finalContent,
              timestamp: new Date()
            };
          } else {
            // No streaming message found, add new final message
            messages.push({
              id: messageId || `final-${Date.now()}`, // Use backend ID if available
              role: 'assistant' as const,
              content: finalContent,
              timestamp: new Date()
            });
          }
          
          return {
            activePanes: {
              ...state.activePanes,
              [paneId]: {
                ...pane,
                messages: messages,
                isStreaming: false
              }
            }
          };
        });
      },
      
      updatePaneStreaming: (paneId, isStreaming) => {
        set((state) => {
          const pane = state.activePanes[paneId];
          if (!pane) return state;
          
          return {
            activePanes: {
              ...state.activePanes,
              [paneId]: { ...pane, isStreaming }
            }
          };
        });
      },
      
      updatePaneMetrics: (paneId, metrics) => {
        set((state) => {
          const pane = state.activePanes[paneId];
          if (!pane) return state;
          
          return {
            activePanes: {
              ...state.activePanes,
              [paneId]: {
                ...pane,
                metrics: { ...pane.metrics, ...metrics }
              }
            }
          };
        });
      },
      
      transferContent: (_sourceId, targetId, content, mode = 'append') => {
        set((state) => {
          const targetPane = state.activePanes[targetId];
          if (!targetPane) return state;
          
          let newMessages: Message[];
          
          if (mode === 'replace') {
            // Replace all messages with transferred content
            newMessages = [...content.messages];
          } else {
            // Append mode (default) - add to existing messages
            newMessages = [...targetPane.messages, ...content.messages];
          }
          
          const updatedPane = {
            ...targetPane,
            messages: newMessages
          };
          
          return {
            activePanes: {
              ...state.activePanes,
              [targetId]: updatedPane
            }
          };
        });
      },
      
      // Comparison Actions
      setComparing: (comparing) => {
        set({ isComparing: comparing });
      },
      
      setSelectedPanes: (panes) => {
        set({ selectedPanes: panes });
      },
      
      // UI Actions
      setMetricsVisible: (visible) => {
        set({ metricsVisible: visible });
      },
      
      // Window Manager Actions
      updateWindowManagerState: (newState) => {
        set((state) => ({
          windowManagerState: { ...state.windowManagerState, ...newState }
        }));
      },
      
      registerWindow: (paneId, window) => {
        set((state) => ({
          windowManagerState: {
            ...state.windowManagerState,
            windows: { ...state.windowManagerState.windows, [paneId]: window }
          }
        }));
      },
      
      unregisterWindow: (paneId) => {
        set((state) => {
          const { [paneId]: removed, ...remainingWindows } = state.windowManagerState.windows;
          return {
            windowManagerState: {
              ...state.windowManagerState,
              windows: remainingWindows
            }
          };
        });
      },
      
      // History Actions
      addToHistory: (history) => {
        set((state) => ({
          conversationHistory: [...state.conversationHistory, history]
        }));
      },
      
      // Template Actions
      addTemplate: (template) => {
        set((state) => ({
          pipelineTemplates: [...state.pipelineTemplates, template]
        }));
      },
      
      removeTemplate: (templateId) => {
        set((state) => ({
          pipelineTemplates: state.pipelineTemplates.filter(t => t.id !== templateId)
        }));
      },
      
      // Model Actions
      setAvailableModels: (models) => {
        set({ availableModels: models });
      }
    }),
    {
      name: 'multi-llm-broadcast-store'
    }
  )
);