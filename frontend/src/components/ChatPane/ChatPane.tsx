import React, { useRef, useEffect, useState } from 'react';
import { ChatPane as ChatPaneType, Message, SelectedContent } from '../../types';
import { FileDirectoryModal, FileInfo } from '../FileDirectoryModal';
import { useAppStore } from '../../store';
import { usePersonaStore } from '../../store/personaStore';
import { MarkdownRenderer } from '../MarkdownRenderer/MarkdownRenderer';
import './ChatPane.css';

export interface ChatPaneProps {
  pane: ChatPaneType;
  onSelectContent?: (content: SelectedContent) => void;
  onSendTo?: (paneId: string) => void;
  onSendMessage?: (paneId: string, message: string, images?: string[]) => void;
  isCompareMode?: boolean;
  compareHighlights?: Array<{
    type: 'added' | 'removed' | 'unchanged';
    text: string;
    startIndex: number;
    endIndex: number;
  }>;
}

export const ChatPane: React.FC<ChatPaneProps> = ({
  pane,
  onSelectContent,
  onSendTo,
  onSendMessage,
  isCompareMode = false,
  compareHighlights = []
}) => {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedMessages, setSelectedMessages] = useState<Set<string>>(new Set());
  const [isSelectionMode, setIsSelectionMode] = useState(false);
  const [inputMessage, setInputMessage] = useState('');
  const [selectedFiles, setSelectedFiles] = useState<{ url: string; name: string; type: string }[]>([]);
  const [isDirectoryOpen, setIsDirectoryOpen] = useState(false);
  const currentSession = useAppStore(state => state.currentSession);
  const availableModels = useAppStore(state => state.availableModels);
  const sessionFilesMap = useAppStore(state => state.sessionFilesMap);
  const addSessionFile = useAppStore(state => state.addSessionFile);
  const updatePanePersona = useAppStore(state => state.updatePanePersona);
  const { personas } = usePersonaStore();

  // Track initial scroll to bottom on load
  const [initialScrollDone, setInitialScrollDone] = useState(false);

  const scrollToMessage = (messageId: string) => {
    // Add a small delay to allow DOM render
    setTimeout(() => {
      const messageEl = document.getElementById(`message-${messageId}`);
      if (messageEl) {
        messageEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    }, 100);
  };

  // Handle scrolling behavior
  useEffect(() => {
    // 1. Initial load - scroll to bottom
    if (!initialScrollDone && pane.messages.length > 0) {
      if (messagesEndRef.current) {
        messagesEndRef.current.scrollIntoView({ behavior: 'auto' });
      }
      setInitialScrollDone(true);
      return;
    }

    // 2. New message added
    const lastMessage = pane.messages[pane.messages.length - 1];
    if (lastMessage) {
      if (lastMessage.role === 'user') {
        // If user sent a message, scroll that message to the top
        scrollToMessage(lastMessage.id);
      } else if (lastMessage.role === 'assistant') {
        // If assistant message was added, verify if the previous message was from user
        // and ensure THAT message is at the top. This effectively shows User Prompt + Start of Answer.
        const prevMessage = pane.messages[pane.messages.length - 2];
        if (prevMessage && prevMessage.role === 'user') {
          scrollToMessage(prevMessage.id);
        }
      }
    }
  }, [pane.messages.length, initialScrollDone]);

  // Removed the streaming auto-scroll useEffect to prevent forced scrolling during generation

  const handleMessageSelect = (messageId: string) => {
    if (!isSelectionMode) return;

    const newSelection = new Set(selectedMessages);
    if (newSelection.has(messageId)) {
      newSelection.delete(messageId);
    } else {
      newSelection.add(messageId);
    }
    setSelectedMessages(newSelection);

    // Update selected content
    if (onSelectContent) {
      const selectedMsgs = pane.messages.filter(m => newSelection.has(m.id));
      const selectedText = selectedMsgs.map(m => m.content).join('\n\n');
      onSelectContent({
        messageIds: Array.from(newSelection),
        text: selectedText
      });
    }
  };

  const toggleSelectionMode = () => {
    setIsSelectionMode(!isSelectionMode);
    if (isSelectionMode) {
      setSelectedMessages(new Set());
      onSelectContent?.({ messageIds: [], text: '' });
    }
  };

  const selectAllMessages = () => {
    const allIds = new Set(pane.messages.map(m => m.id));
    setSelectedMessages(allIds);

    if (onSelectContent) {
      const selectedText = pane.messages.map(m => m.content).join('\n\n');
      onSelectContent({
        messageIds: Array.from(allIds),
        text: selectedText
      });
    }
  };

  const clearSelection = () => {
    setSelectedMessages(new Set());
    onSelectContent?.({ messageIds: [], text: '' });
  };

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && currentSession) {
      const files = Array.from(e.target.files);
      for (const file of files) {
        const formData = new FormData();
        formData.append('file', file);
        try {
          const res = await fetch(`http://localhost:5000/session/${currentSession.id}/upload`, {
            method: 'POST',
            body: formData
          });
          if (res.ok) {
            const data = await res.json();
            const fileName = data.originalName || data.name;
            setSelectedFiles(prev => [...prev, {
              url: data.uri,
              name: fileName,
              type: data.type
            }]);
            addSessionFile(data.uri, fileName);
          } else {
            console.error('Failed to upload file', await res.text());
          }
        } catch (error) {
          console.error('Error uploading file:', error);
        }
      }
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleRemoveFile = (index: number) => {
    setSelectedFiles(prev => prev.filter((_, i) => i !== index));
  };

  const handleDirectorySelect = (files: FileInfo[]) => {
    const newFiles = files.map(f => ({
      url: f.uri,
      name: f.name,
      type: f.type
    }));
    const existingUrls = new Set(selectedFiles.map(f => f.url));
    const toAdd = newFiles.filter(f => !existingUrls.has(f.url));
    setSelectedFiles(prev => [...prev, ...toAdd]);
  };

  // Direct send handler for files selected from directory with a specific model
  const handleDirectSend = (modelId: string, files: FileInfo[]) => {
    const model = availableModels.find(m => m.id === modelId);
    if (!model) return;

    const fileUrls = files.map(f => f.uri);

    // If we're sending to the SAME model as this pane, just send it here
    if (model.id === pane.modelInfo.id && onSendMessage) {
      onSendMessage(pane.id, '', fileUrls.length > 0 ? fileUrls : undefined);
    } else {
      // If sending to a DIFFERENT model, we need help from the parent (Workspace)
      // For now, if we don't have a global broadcast prop, we'll try to find an existing pane
      // or just warn that multi-model send from pane isn't fully wired yet.
      // Re-checking Workspace integration...
      console.log(`Sending ${files.length} files to ${model.name}`);

      // We'll pass this up via a new prop or handle it locally if Workspace gives us a handler
      if ((window as any).broadcastToModel) {
        (window as any).broadcastToModel(model, '', fileUrls);
      } else if (onSendMessage) {
        // Fallback: send to this pane but log it
        console.warn('Global broadcast not found, falling back to current pane');
        onSendMessage(pane.id, `[Sent to ${model.name}]`, fileUrls);
      }
    }

    setIsDirectoryOpen(false);
  };

  const handleSendMessage = () => {
    if ((inputMessage.trim() || selectedFiles.length > 0) && onSendMessage && !pane.isStreaming) {
      // Extract just the URLs for the API, as it expects string[]
      const fileUrls = selectedFiles.map(f => f.url);

      onSendMessage(pane.id, inputMessage.trim(), fileUrls.length > 0 ? fileUrls : undefined);
      setInputMessage('');
      setSelectedFiles([]);
      // Reset initial scroll done so we don't interfere with standard behavior? 
      // Actually no, we want standard behavior (user scroll) now.
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const formatTimestamp = (timestamp: Date) => {
    return new Date(timestamp).toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    });
  };

  const renderMessageContent = (message: Message) => {
    if (!isCompareMode || compareHighlights.length === 0) {
      // Render markdown for normal messages
      return (
        <div className="message-text">
          <MarkdownRenderer content={message.content} />
          {message.images && message.images.length > 0 && (
            <div className="message-images">
              {message.images.map((img, idx) => {
                const isImage = img.startsWith('data:image');
                return isImage ? (
                  <img
                    key={idx}
                    src={img}
                    alt={`Attached content ${idx + 1}`}
                    className="message-image"
                    onClick={() => window.open(img, '_blank')}
                  />
                ) : (
                  <div
                    key={idx}
                    className="message-attachment"
                    style={{
                      padding: '10px',
                      background: 'rgba(0,0,0,0.05)',
                      borderRadius: '8px',
                      marginTop: '8px',
                      cursor: 'pointer',
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '8px',
                      border: '1px solid rgba(0,0,0,0.1)'
                    }}
                    onClick={() => window.open(img, '_blank')}
                    title="Click to open"
                  >
                    <span style={{ fontSize: '24px' }}>📄</span>
                    <span style={{ fontWeight: 500 }}>{sessionFilesMap[img] || img.split(';')[0].split(':')[1] || 'Document'}</span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      );
    }

    // Apply compare highlights to message content
    let highlightedContent = message.content;
    const highlights = compareHighlights.filter(h =>
      message.content.includes(h.text)
    );

    if (highlights.length > 0) {
      // Sort highlights by start index to apply them in order
      highlights.sort((a, b) => a.startIndex - b.startIndex);

      let offset = 0;
      highlights.forEach(highlight => {
        const startIndex = highlight.startIndex + offset;
        const endIndex = highlight.endIndex + offset;
        const beforeText = highlightedContent.substring(0, startIndex);
        const highlightText = highlightedContent.substring(startIndex, endIndex);
        const afterText = highlightedContent.substring(endIndex);

        const wrappedText = `<span class="diff-${highlight.type}">${highlightText}</span>`;
        highlightedContent = beforeText + wrappedText + afterText;
        offset += wrappedText.length - highlightText.length;
      });
    }

    return (
      <div
        className="message-text"
        dangerouslySetInnerHTML={{ __html: highlightedContent }}
      />
    );
  };

  return (
    <div className={`chat-pane ${isCompareMode ? 'compare-mode' : ''}`}>
      {/* Pane Header */}
      <div className="pane-header">
        <div className="model-info">
          <h4 className="model-name">
            {pane.modelInfo.name}
          </h4>
          <div className="model-details">
            <span className="model-detail">
              Max: {pane.modelInfo.maxTokens.toLocaleString()}
            </span>
            <span className="model-detail">
              Cost/1K: ${pane.modelInfo.costPer1kTokens.toFixed(4)}
            </span>
            {pane.modelInfo.supportsStreaming && (
              <span className="streaming-support">📡</span>
            )}
          </div>
          <div className="pane-persona-selector">
            <select
              value={pane.personaId || 'global'}
              onChange={(e) => updatePanePersona(pane.id, e.target.value === 'global' ? undefined : e.target.value)}
              className="local-persona-select"
            >
              <option value="global">🌍 Global Persona</option>
              {personas.map(p => (
                <option key={p.id} value={p.id}>🎭 {p.name}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="pane-metrics">
          <div className="metric">
            <span className="metric-label">Tokens:</span>
            <span className="metric-value">{pane.metrics.tokenCount}</span>
          </div>
          <div className="metric">
            <span className="metric-label">Cost:</span>
            <span className="metric-value">${pane.metrics.cost.toFixed(4)}</span>
          </div>
          <div className="metric">
            <span className="metric-label">Latency:</span>
            <span className="metric-value">{pane.metrics.latency}ms</span>
          </div>
        </div>
      </div>

      {/* Messages Container */}
      <div className="messages-container" ref={messagesContainerRef}>
        {pane.messages.length === 0 ? (
          <div className="empty-messages">
            <p>No messages yet. Start a broadcast to see responses here.</p>
          </div>
        ) : (
          pane.messages.map((message) => (
            <div
              key={message.id}
              id={`message-${message.id}`}
              className={`message message-${message.role} ${selectedMessages.has(message.id) ? 'selected' : ''
                } ${isSelectionMode ? 'selectable' : ''}`}
              onClick={() => handleMessageSelect(message.id)}
            >
              <div className="message-header">
                <div className="message-meta">
                  <span className="message-role">{message.role}</span>
                  <span className="message-time">
                    {formatTimestamp(message.timestamp)}
                  </span>

                </div>
                {isSelectionMode && (
                  <div className="selection-checkbox">
                    <input
                      type="checkbox"
                      checked={selectedMessages.has(message.id)}
                      onChange={() => handleMessageSelect(message.id)}
                      onClick={(e) => e.stopPropagation()}
                    />
                  </div>
                )}
              </div>

              <div className="message-content">
                {renderMessageContent(message)}

                {message.metadata && (
                  <div className="message-metadata">
                    {message.metadata.tokenCount && (
                      <span className="metadata-item">
                        {message.metadata.tokenCount} tokens
                      </span>
                    )}
                    {message.metadata.cost && (
                      <span className="metadata-item">
                        ${message.metadata.cost.toFixed(4)}
                      </span>
                    )}
                    {message.metadata.latency && (
                      <span className="metadata-item">
                        {message.metadata.latency}ms
                      </span>
                    )}
                  </div>
                )}
              </div>
            </div>
          ))
        )}

        {/* Streaming/Loading Indicator - mimics GPT thinking state */}
        {pane.isStreaming && (!pane.messages.length || !pane.messages[pane.messages.length - 1].id.startsWith('streaming-')) && (
          <div className="message message-assistant" style={{ width: 'fit-content', alignItems: 'center', justifyContent: 'center' }}>
            <div className="streaming-dots">
              <span></span>
              <span></span>
              <span></span>
            </div>
          </div>
        )}

        {/* Spacer to allow scrolling user prompt to top even with short content */}
        {pane.isStreaming && (
          <div style={{ minHeight: '60vh' }} />
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Chat Input */}
      <div className="chat-input-section">
        {selectedFiles.length > 0 && (
          <div className="file-previews">
            {selectedFiles.map((file, index) => (
              <div key={index} className="file-preview-item" style={{ width: 'auto', minWidth: '120px', maxWidth: '200px', display: 'flex', alignItems: 'center', gap: '8px', padding: '4px 8px', backgroundColor: '#f0f0f0' }}>
                {file.type.startsWith('image/') ? (
                  <img src={file.url} alt={file.name} className="file-thumbnail" style={{ width: '32px', height: '32px', flexShrink: 0 }} />
                ) : (
                  <div className="file-icon" style={{ fontSize: '20px' }}>📄</div>
                )}
                <div className="file-info" style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
                  <span className="file-name" style={{ fontSize: '12px', fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={file.name}>{file.name}</span>
                  <span className="file-type" style={{ fontSize: '10px', color: '#666' }}>{file.type.split('/')[1]?.toUpperCase() || 'FILE'}</span>
                </div>
                <button
                  className="remove-file-btn"
                  onClick={() => handleRemoveFile(index)}
                  title="Remove file"
                  style={{ position: 'static', marginLeft: 'auto', background: 'transparent', color: '#666', border: 'none', fontSize: '14px' }}
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
        )}
        <div className="chat-input-container">
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileSelect}
            style={{ display: 'none' }}
            accept="image/*,application/pdf,text/csv,application/json,text/plain"
            multiple
          />
          <button
            className="action-btn secondary directory-trigger-btn"
            onClick={() => setIsDirectoryOpen(true)}
            title="Session Files Directory"
            disabled={pane.isStreaming}
          >
            📁
          </button>
          <button
            className="action-btn secondary file-upload-btn"
            onClick={() => setIsDirectoryOpen(true)}
            title="Attach or select from session directory (provides LLM options)"
            disabled={pane.isStreaming}
          >
            📎
          </button>
          <textarea
            className="chat-input"
            placeholder={`Chat with ${pane.modelInfo.name}...`}
            value={inputMessage}
            onChange={(e) => setInputMessage(e.target.value)}
            onKeyDown={handleKeyPress}
            disabled={pane.isStreaming}
            rows={2}
          />
          <button
            className="send-btn"
            onClick={handleSendMessage}
            disabled={(!inputMessage.trim() && selectedFiles.length === 0) || pane.isStreaming}
            title="Send message (Enter)"
          >
            {pane.isStreaming ? '⏳' : '📤'}
          </button>
        </div>
      </div>

      {/* Pane Actions */}
      <div className="pane-actions">
        <div className="selection-actions">
          <button
            className={`action-btn ${isSelectionMode ? 'active' : ''}`}
            onClick={toggleSelectionMode}
            title="Toggle message selection mode"
          >
            {isSelectionMode ? '✓ Select Mode' : '☐ Select'}
          </button>

          {isSelectionMode && (
            <>
              <button
                className="action-btn secondary"
                onClick={selectAllMessages}
                title="Select all messages"
              >
                Select All
              </button>
              <button
                className="action-btn secondary"
                onClick={clearSelection}
                title="Clear selection"
              >
                Clear
              </button>
            </>
          )}
        </div>

        <div className="transfer-actions">
          {selectedMessages.size > 0 && onSendTo && (
            <button
              className="action-btn primary"
              onClick={() => onSendTo(pane.id)}
              title="Send selected messages to another pane"
            >
              Send To... ({selectedMessages.size})
            </button>
          )}
        </div>
      </div>

      {currentSession && (
        <FileDirectoryModal
          sessionId={currentSession.id}
          isOpen={isDirectoryOpen}
          onClose={() => setIsDirectoryOpen(false)}
          onSelectFiles={handleDirectorySelect}
          onSendDirect={handleDirectSend}
        />
      )}
    </div>
  );
};