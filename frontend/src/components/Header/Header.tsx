import React, { useState } from 'react';
import { useAppStore } from '../../store';
import { CodeCompareArena } from '../CodeCompareArena/CodeCompareArena';
import './Header.css';

export const Header: React.FC = () => {
  const { currentSession, metricsVisible, setMetricsVisible } = useAppStore();
  const [arenaVisible, setArenaVisible] = useState(false);

  return (
    <>
      <header className="header">
        <div className="header-left">
          <h1 className="app-title">Multi-LLM Broadcast Workspace</h1>
          {currentSession && (
            <div className="session-info">
              <span className="session-name">{currentSession.name}</span>
              <span className="session-status">{currentSession.status}</span>
            </div>
          )}
        </div>

        <div className="header-right">
          <button
            className={`metrics-toggle ${metricsVisible ? 'active' : ''}`}
            onClick={() => setMetricsVisible(!metricsVisible)}
            title="Toggle Metrics Panel"
          >
            📊 Metrics
          </button>

          {/* ── Code Compare Arena button ── */}
          <button
            className="arena-btn"
            onClick={() => setArenaVisible(true)}
            title="Open Code Compare Arena"
          >
            ⚔️ Code Arena
          </button>

          <div className="session-controls">
            <button className="session-btn" title="Session History">
              📚 History
            </button>
            <button className="session-btn" title="Pipeline Templates">
              🔧 Templates
            </button>
          </div>
        </div>
      </header>

      {/* ── Code Compare Arena Modal ── */}
      <CodeCompareArena
        isVisible={arenaVisible}
        onClose={() => setArenaVisible(false)}
      />
    </>
  );
};
