import React, { useState } from 'react';
import { ChatPane } from '../../types';
import './FloatingToolbar.css';

export interface FloatingToolbarProps {
  activePanes: ChatPane[];
  isComparing: boolean;
  selectedPanes: [string, string] | null;
  onCompareToggle: (paneIds: [string, string] | null) => void;
  onArrangeWindows: () => void;
  onMinimizeAll: () => void;
  onCloseAll: () => void;
  onBroadcastToActive?: (paneIds: string[], prompt: string) => void;
  onOpenArena?: () => void;
}

export const FloatingToolbar: React.FC<FloatingToolbarProps> = ({
  activePanes,
  isComparing,
  selectedPanes,
  onCompareToggle,
  onArrangeWindows,
  onMinimizeAll,
  onCloseAll,
  onBroadcastToActive,
  onOpenArena
}) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [showCompareSelector, setShowCompareSelector] = useState(false);
  const [showBroadcastSelector, setShowBroadcastSelector] = useState(false);
  const [broadcastPrompt, setBroadcastPrompt] = useState('');
  const [selectedBroadcastPanes, setSelectedBroadcastPanes] = useState<Set<string>>(new Set());
  const [tempSelection, setTempSelection] = useState<{
    first: string | null;
    second: string | null;
  }>({
    first: selectedPanes?.[0] || null,
    second: selectedPanes?.[1] || null
  });

  const paneCount = activePanes.length;
  const canCompare = paneCount >= 2;

  const handleCompareStart = () => {
    if (canCompare) {
      setShowCompareSelector(true);
      setTempSelection({ first: null, second: null });
    }
  };

  const applyComparison = () => {
    if (tempSelection.first && tempSelection.second && tempSelection.first !== tempSelection.second) {
      onCompareToggle([tempSelection.first, tempSelection.second]);
      setShowCompareSelector(false);
    }
  };

  const clearComparison = () => {
    onCompareToggle(null);
    setShowCompareSelector(false);
    setTempSelection({ first: null, second: null });
  };

  const getModelName = (paneId: string) => {
    const pane = activePanes.find(p => p.id === paneId);
    return pane ? `${pane.modelInfo.provider}:${pane.modelInfo.name}` : 'Unknown';
  };

  const handleBroadcastStart = () => {
    if (paneCount > 0) {
      setShowBroadcastSelector(true);
      setBroadcastPrompt('');
      setSelectedBroadcastPanes(new Set());
    }
  };

  const handleBroadcastPaneToggle = (paneId: string) => {
    const newSelected = new Set(selectedBroadcastPanes);
    if (newSelected.has(paneId)) {
      newSelected.delete(paneId);
    } else {
      newSelected.add(paneId);
    }
    setSelectedBroadcastPanes(newSelected);
  };

  const handleBroadcastToSelected = () => {
    if (broadcastPrompt.trim() && selectedBroadcastPanes.size > 0 && onBroadcastToActive) {
      onBroadcastToActive(Array.from(selectedBroadcastPanes), broadcastPrompt.trim());
      setShowBroadcastSelector(false);
      setBroadcastPrompt('');
      setSelectedBroadcastPanes(new Set());
    }
  };

  const handleBroadcastToAll = () => {
    if (broadcastPrompt.trim() && onBroadcastToActive) {
      onBroadcastToActive(activePanes.map(p => p.id), broadcastPrompt.trim());
      setShowBroadcastSelector(false);
      setBroadcastPrompt('');
      setSelectedBroadcastPanes(new Set());
    }
  };

  const selectAllBroadcastPanes = () => setSelectedBroadcastPanes(new Set(activePanes.map(p => p.id)));
  const clearAllBroadcastPanes = () => setSelectedBroadcastPanes(new Set());

  const estimateTokens = (text: string): number => Math.ceil(text.length / 4);

  const getBroadcastEstimates = (paneIds: string[]) => {
    const promptTokens = estimateTokens(broadcastPrompt);
    const estimatedResponseTokens = Math.min(promptTokens * 2, 500);
    const totalTokens = promptTokens + estimatedResponseTokens;
    const totalCost = paneIds.reduce((sum, paneId) => {
      const pane = activePanes.find(p => p.id === paneId);
      if (pane) return sum + ((totalTokens / 1000) * (pane.modelInfo.costPer1kTokens || 0));
      return sum;
    }, 0);
    return { promptTokens, estimatedResponseTokens, totalTokens, totalCost, panesCount: paneIds.length };
  };

  return (
    <div className="floating-toolbar">
      <div className="toolbar-main">
        <button
          className="toolbar-toggle"
          onClick={() => setIsExpanded(!isExpanded)}
          title="Window Controls"
        >
          <span className="toggle-icon">{isExpanded ? '✕' : '⚙️'}</span>
          {paneCount > 0 && <span className="pane-count">{paneCount}</span>}
        </button>

        {isExpanded && (
          <div className="toolbar-menu">
            {/* Window Management */}
            <div className="menu-section">
              <div className="section-title">Window Management</div>
              <button className="menu-item" onClick={onArrangeWindows} disabled={paneCount === 0}>
                <span className="item-icon">📐</span>
                <span className="item-text">Arrange</span>
              </button>
              <button className="menu-item" onClick={onMinimizeAll} disabled={paneCount === 0}>
                <span className="item-icon">🗕</span>
                <span className="item-text">Minimize All</span>
              </button>
              <button className="menu-item danger" onClick={onCloseAll} disabled={paneCount === 0}>
                <span className="item-icon">🗙</span>
                <span className="item-text">Close All</span>
              </button>
            </div>

            {/* Broadcast */}
            <div className="menu-section">
              <div className="section-title">Broadcast to Active</div>
              <button className="menu-item broadcast" onClick={handleBroadcastStart} disabled={paneCount === 0}>
                <span className="item-icon">📡</span>
                <span className="item-text">Broadcast</span>
              </button>
            </div>

            {/* Comparison */}
            <div className="menu-section">
              <div className="section-title">Comparison</div>
              {!isComparing ? (
                <button className="menu-item" onClick={handleCompareStart} disabled={!canCompare}>
                  <span className="item-icon">⚖️</span>
                  <span className="item-text">Compare</span>
                </button>
              ) : (
                <button className="menu-item active" onClick={clearComparison}>
                  <span className="item-icon">✓</span>
                  <span className="item-text">Stop Compare</span>
                </button>
              )}
              <button
                className="menu-item"
                onClick={() => { setIsExpanded(false); onOpenArena?.(); }}
                disabled={paneCount === 0}
                title={paneCount > 0 ? 'Analyze and compare code across panes' : 'No active panes'}
              >
                <span className="item-icon">⚔️</span>
                <span className="item-text">Code Compare Arena</span>
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Broadcast Selector */}
      {showBroadcastSelector && (
        <div className="broadcast-selector-overlay">
          <div className="broadcast-selector">
            <div className="selector-header">
              <h4>Broadcast to Active LLMs</h4>
              <button className="close-btn" onClick={() => setShowBroadcastSelector(false)}>×</button>
            </div>

            <div className="broadcast-prompt-section">
              <label className="prompt-label">Message to broadcast:</label>
              <textarea
                className="broadcast-prompt-input"
                placeholder="Enter your message to send to selected LLMs..."
                value={broadcastPrompt}
                onChange={(e) => setBroadcastPrompt(e.target.value)}
                rows={3}
              />
            </div>

            <div className="pane-selection-section">
              <div className="selection-header">
                <h5>Select LLMs ({selectedBroadcastPanes.size} of {paneCount} selected)</h5>
                <div className="selection-controls">
                  <button className="select-all-btn" onClick={selectAllBroadcastPanes}>Select All</button>
                  <button className="clear-all-btn" onClick={clearAllBroadcastPanes}>Clear</button>
                </div>
              </div>

              <div className="broadcast-pane-list">
                {activePanes.map(pane => {
                  const isSelected = selectedBroadcastPanes.has(pane.id);
                  return (
                    <div key={pane.id} className={`broadcast-pane-option ${isSelected ? 'selected' : ''}`}>
                      <label className="pane-checkbox">
                        <input type="checkbox" checked={isSelected} onChange={() => handleBroadcastPaneToggle(pane.id)} />
                        <div className="pane-info">
                          <div className="pane-name">{getModelName(pane.id)}</div>
                          <div className="pane-stats">{pane.messages.length} messages</div>
                        </div>
                      </label>
                      {pane.isStreaming && (
                        <div className="streaming-indicator">
                          <span className="streaming-dot"></span>Streaming
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>

            {broadcastPrompt.trim() && (
              <div className="broadcast-estimates">
                {selectedBroadcastPanes.size > 0 && (() => {
                  const estimates = getBroadcastEstimates(Array.from(selectedBroadcastPanes));
                  const warningLevel = estimates.totalCost >= 0.20 ? 'high' : estimates.totalCost >= 0.05 ? 'medium' : 'low';
                  return (
                    <div className="estimate-card selected">
                      <div className={`estimate-content ${warningLevel}`}>
                        <span className="estimate-icon">{warningLevel === 'high' ? '⚠️' : warningLevel === 'medium' ? '💰' : '💡'}</span>
                        <span className="estimate-header">Selected LLMs Estimate</span>
                        <div className="estimate-details">
                          <div className="estimate-row">
                            <span>Models: {estimates.panesCount}</span>
                            <span>~{estimates.totalTokens.toLocaleString()} tokens</span>
                            <span>${estimates.totalCost.toFixed(4)}</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })()}

                {(() => {
                  const estimates = getBroadcastEstimates(activePanes.map(p => p.id));
                  const warningLevel = estimates.totalCost >= 0.20 ? 'high' : estimates.totalCost >= 0.05 ? 'medium' : 'low';
                  return (
                    <div className="estimate-card all">
                      <div className={`estimate-content ${warningLevel}`}>
                        <span className="estimate-icon">{warningLevel === 'high' ? '⚠️' : warningLevel === 'medium' ? '💰' : '📊'}</span>
                        <span className="estimate-header">All LLMs Estimate</span>
                        <div className="estimate-details">
                          <div className="estimate-row">
                            <span>Models: {estimates.panesCount}</span>
                            <span>~{estimates.totalTokens.toLocaleString()} tokens</span>
                            <span>${estimates.totalCost.toFixed(4)}</span>
                          </div>
                          {estimates.totalCost >= 0.20 && (
                            <div className="cost-warning">High cost operation - consider selecting fewer LLMs</div>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })()}
              </div>
            )}

            <div className="selector-actions">
              <button className="cancel-btn" onClick={() => setShowBroadcastSelector(false)}>Cancel</button>
              <button className="broadcast-selected-btn" onClick={handleBroadcastToSelected}
                disabled={!broadcastPrompt.trim() || selectedBroadcastPanes.size === 0}>
                🚀 Send to Selected ({selectedBroadcastPanes.size})
              </button>
              <button className="broadcast-all-btn" onClick={handleBroadcastToAll} disabled={!broadcastPrompt.trim()}>
                📡 Send to All ({paneCount})
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Compare Selector */}
      {showCompareSelector && (
        <div className="compare-selector-overlay">
          <div className="compare-selector">
            <div className="selector-header">
              <h4>Select Panes to Compare</h4>
              <button className="close-btn" onClick={() => setShowCompareSelector(false)}>×</button>
            </div>

            <div className="pane-selection">
              <div className="selection-column">
                <h5>First Pane</h5>
                {activePanes.map(pane => (
                  <button
                    key={`first-${pane.id}`}
                    className={`pane-btn ${tempSelection.first === pane.id ? 'selected' : ''} ${tempSelection.second === pane.id ? 'disabled' : ''}`}
                    onClick={() => { if (tempSelection.second !== pane.id) setTempSelection(prev => ({ ...prev, first: pane.id })); }}
                    disabled={tempSelection.second === pane.id}
                  >
                    {getModelName(pane.id)}
                  </button>
                ))}
              </div>

              <div className="vs-divider">VS</div>

              <div className="selection-column">
                <h5>Second Pane</h5>
                {activePanes.map(pane => (
                  <button
                    key={`second-${pane.id}`}
                    className={`pane-btn ${tempSelection.second === pane.id ? 'selected' : ''} ${tempSelection.first === pane.id ? 'disabled' : ''}`}
                    onClick={() => { if (tempSelection.first !== pane.id) setTempSelection(prev => ({ ...prev, second: pane.id })); }}
                    disabled={tempSelection.first === pane.id}
                  >
                    {getModelName(pane.id)}
                  </button>
                ))}
              </div>
            </div>

            <div className="selector-actions">
              <button className="cancel-btn" onClick={() => setShowCompareSelector(false)}>Cancel</button>
              <button className="apply-btn" onClick={applyComparison}
                disabled={!tempSelection.first || !tempSelection.second || tempSelection.first === tempSelection.second}>
                Start Comparison
              </button>
            </div>
          </div>
        </div>
      )}

      {isComparing && selectedPanes && (
        <div className="compare-status">
          <div className="status-content">
            <span className="status-icon">⚖️</span>
            <span className="status-text">
              Comparing: {getModelName(selectedPanes[0])} vs {getModelName(selectedPanes[1])}
            </span>
          </div>
        </div>
      )}
    </div>
  );
};
