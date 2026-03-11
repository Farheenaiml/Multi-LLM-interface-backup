import React, { useState, useMemo } from 'react';
import { useAppStore } from '../../store';
import './CodeCompareArena.css';

interface CodeAnalysis {
  paneId: string;
  modelName: string;
  provider: string;
  code: string;
  language: string;
  timeComplexity: string;
  spaceComplexity: string;
  readabilityScore: number;
  readabilityGrade: string;
  securityIssues: SecurityIssue[];
  bugs: BugReport[];
  linesOfCode: number;
  cyclomaticComplexity: number;
  overallScore: number;
  analysisStatus: 'idle' | 'analyzing' | 'done' | 'error';
  errorMessage?: string;
}

interface SecurityIssue {
  severity: 'critical' | 'high' | 'medium' | 'low';
  title: string;
  description: string;
  line?: number;
}

interface BugReport {
  severity: 'critical' | 'high' | 'medium' | 'low';
  title: string;
  description: string;
  line?: number;
}

interface CodeCompareArenaProps {
  isVisible: boolean;
  onClose: () => void;
}

const extractCodeFromMessages = (messages: any[]): string => {
  const assistantMsgs = [...messages].reverse().filter(m => m.role === 'assistant');
  for (const msg of assistantMsgs) {
    const match = msg.content.match(/```[\w]*\n?([\s\S]*?)```/);
    if (match) return match[1].trim();
  }
  const last = assistantMsgs[0];
  return last ? last.content.trim() : '';
};

const detectLanguage = (code: string): string => {
  if (/def |import |print\(|:\s*$/.test(code)) return 'Python';
  if (/function |const |let |var |=>/.test(code)) return 'JavaScript/TypeScript';
  if (/public class|System\.out|void main/.test(code)) return 'Java';
  if (/#include|int main|std::/.test(code)) return 'C/C++';
  if (/func |package main|fmt\./.test(code)) return 'Go';
  if (/fn |let mut|println!/.test(code)) return 'Rust';
  return 'Unknown';
};

const callClaudeForAnalysis = async (code: string, modelName: string): Promise<Partial<CodeAnalysis>> => {
  const response = await fetch('http://localhost:5000/analyze-code', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code, model_name: modelName })
  });

  if (!response.ok) {
    throw new Error(`Backend error: ${response.status} ${response.statusText}`);
  }

  try {
    return await response.json();
  } catch {
    return {
      timeComplexity: 'N/A', spaceComplexity: 'N/A',
      readabilityScore: 50, readabilityGrade: 'C',
      cyclomaticComplexity: 1, securityIssues: [], bugs: [], overallScore: 50
    };
  }
};

const ScoreRing: React.FC<{ score: number; size?: number }> = ({ score, size = 72 }) => {
  const r = (size / 2) - 6;
  const circ = 2 * Math.PI * r;
  const offset = circ - (score / 100) * circ;
  const color = score >= 80 ? '#22c55e' : score >= 60 ? '#f59e0b' : score >= 40 ? '#f97316' : '#ef4444';
  return (
    <svg width={size} height={size} className="score-ring">
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth="5" />
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={color} strokeWidth="5"
        strokeDasharray={circ} strokeDashoffset={offset} strokeLinecap="round"
        transform={`rotate(-90 ${size/2} ${size/2})`} style={{ transition: 'stroke-dashoffset 0.8s ease' }} />
     
        <text x="50%" y="50%" dominantBaseline="middle" textAnchor="middle"
  fill="#111111" fontSize={size * 0.22} fontWeight="700">
  {score}
</text>
    </svg>
  );
};

const SeverityBadge: React.FC<{ severity: string }> = ({ severity }) => (
  <span className={`severity-badge severity-${severity}`}>{severity}</span>
);

const ComplexityBar: React.FC<{ label: string; value: string }> = ({ label, value }) => {
  const level = value.includes('n²') || value.includes('n^2') || value.includes('2^n') ? 'high'
    : value.includes('n log') ? 'medium' : value === 'O(1)' ? 'low' : 'medium';
  return (
    <div className="complexity-bar-item">
      <span className="complexity-label">{label}</span>
      <span className={`complexity-value complexity-${level}`}>{value}</span>
    </div>
  );
};

const ReadabilityMeter: React.FC<{ score: number; grade: string }> = ({ score, grade }) => {
  const color = score >= 80 ? '#22c55e' : score >= 60 ? '#f59e0b' : '#ef4444';
  return (
    <div className="readability-meter">
      <div className="readability-header">
        <span className="readability-label">Readability</span>
        <span className="readability-grade" style={{ color }}>{grade}</span>
      </div>
      <div className="readability-track">
        <div className="readability-fill" style={{ width: `${score}%`, background: color }} />
      </div>
      <span className="readability-score">{score}/100</span>
    </div>
  );
};

const IssueList: React.FC<{ items: (SecurityIssue | BugReport)[]; type: 'security' | 'bug' }> = ({ items, type }) => {
  if (items.length === 0) {
    return (
      <div className="issue-empty">
        <span className="issue-empty-icon">{type === 'security' ? '🔒' : '✅'}</span>
        <span>No {type === 'security' ? 'security issues' : 'bugs'} detected</span>
      </div>
    );
  }
  return (
    <div className="issue-list">
      {items.map((issue, i) => (
        <div key={i} className={`issue-item issue-${issue.severity}`}>
          <div className="issue-header">
            <SeverityBadge severity={issue.severity} />
            <span className="issue-title">{issue.title}</span>
            {issue.line && <span className="issue-line">Line {issue.line}</span>}
          </div>
          <p className="issue-desc">{issue.description}</p>
        </div>
      ))}
    </div>
  );
};

const WinnerBadge: React.FC<{ analysis: CodeAnalysis[] }> = ({ analysis }) => {
  const done = analysis.filter(a => a.analysisStatus === 'done');
  if (done.length < 2) return null;
  const winner = done.reduce((a, b) => a.overallScore > b.overallScore ? a : b);
  return (
    <div className="winner-banner">
      <span className="winner-trophy">🏆</span>
      <span className="winner-text">
        Best overall: <strong>{winner.modelName}</strong>
        <span className="winner-score">({winner.overallScore}/100)</span>
      </span>
    </div>
  );
};

export const CodeCompareArena: React.FC<CodeCompareArenaProps> = ({ isVisible, onClose }) => {
  const { activePanes } = useAppStore();
  const [analyses, setAnalyses] = useState<Record<string, CodeAnalysis>>({});
  const [activeTab, setActiveTab] = useState<'overview' | 'security' | 'bugs' | 'complexity'>('overview');
  const [isRunning, setIsRunning] = useState(false);
  const [selectedPaneIds, setSelectedPaneIds] = useState<string[]>([]);

  const paneList = Object.values(activePanes);

  const togglePane = (id: string) => {
    setSelectedPaneIds(prev => prev.includes(id) ? prev.filter(p => p !== id) : [...prev, id]);
  };

  const runAnalysis = async () => {
    const targets = selectedPaneIds.length > 0
      ? paneList.filter(p => selectedPaneIds.includes(p.id))
      : paneList;
    if (targets.length === 0) return;
    setIsRunning(true);

    const initial: Record<string, CodeAnalysis> = {};
    targets.forEach(pane => {
      const code = extractCodeFromMessages(pane.messages);
      initial[pane.id] = {
        paneId: pane.id, modelName: pane.modelInfo.name, provider: pane.modelInfo.provider,
        code, language: detectLanguage(code), timeComplexity: '—', spaceComplexity: '—',
        readabilityScore: 0, readabilityGrade: '—', securityIssues: [], bugs: [],
        linesOfCode: code.split('\n').filter(l => l.trim()).length,
        cyclomaticComplexity: 1, overallScore: 0,
        analysisStatus: code ? 'analyzing' : 'error',
        errorMessage: code ? undefined : 'No code found in conversation'
      };
    });
    setAnalyses(initial);

    await Promise.all(
      targets.filter(p => initial[p.id].analysisStatus === 'analyzing').map(async pane => {
        try {
          const result = await callClaudeForAnalysis(initial[pane.id].code, pane.modelInfo.name);
          setAnalyses(prev => ({ ...prev, [pane.id]: { ...prev[pane.id], ...result, analysisStatus: 'done' } }));
        } catch (e) {
          setAnalyses(prev => ({
            ...prev,
            [pane.id]: {
              ...prev[pane.id], analysisStatus: 'error',
              errorMessage: `Analysis failed: ${e instanceof Error ? e.message : 'Unknown error'}`
            }
          }));
        }
      })
    );
    setIsRunning(false);
  };

  const analysisResults = useMemo(() => Object.values(analyses), [analyses]);
  const hasResults = analysisResults.some(a => a.analysisStatus === 'done');

  if (!isVisible) return null;

  return (
    <div className="arena-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="arena-modal">
        <div className="arena-header">
          <div className="arena-header-left">
            <span className="arena-icon">⚔️</span>
            <div>
              <h2 className="arena-title">Code Compare Arena</h2>
              <p className="arena-subtitle">AI-powered analysis across all panes</p>
            </div>
          </div>
          <button className="arena-close" onClick={onClose}>×</button>
        </div>

        {paneList.length === 0 ? (
          <div className="arena-empty">
            <div className="arena-empty-icon">💬</div>
            <h3>No active panes</h3>
            <p>Broadcast a coding prompt to multiple models first, then run the Code Arena.</p>
          </div>
        ) : (
          <>
            <div className="arena-pane-selector">
              <span className="selector-label">Analyze panes:</span>
              <div className="selector-chips">
                {paneList.map(pane => (
                  <button key={pane.id}
                    className={`pane-chip ${selectedPaneIds.includes(pane.id) ? 'selected' : ''} ${selectedPaneIds.length === 0 ? 'implicit' : ''}`}
                    onClick={() => togglePane(pane.id)}>
                    <span className="chip-provider">{pane.modelInfo.provider}</span>
                    {pane.modelInfo.name}
                  </button>
                ))}
              </div>
              <button className={`run-btn ${isRunning ? 'running' : ''}`} onClick={runAnalysis} disabled={isRunning}>
                {isRunning ? <><span className="spin">⟳</span> Analyzing…</> : <><span>▶</span> Run Analysis</>}
              </button>
            </div>

            <WinnerBadge analysis={analysisResults} />

            {hasResults && (
              <div className="arena-tabs">
                {(['overview', 'complexity', 'security', 'bugs'] as const).map(tab => (
                  <button key={tab} className={`arena-tab ${activeTab === tab ? 'active' : ''}`} onClick={() => setActiveTab(tab)}>
                    {tab === 'overview' && '📊 '}{tab === 'complexity' && '⏱️ '}
                    {tab === 'security' && '🔐 '}{tab === 'bugs' && '🐛 '}
                    {tab.charAt(0).toUpperCase() + tab.slice(1)}
                  </button>
                ))}
              </div>
            )}

            {analysisResults.length > 0 && (
              <div className="arena-results">
                {analysisResults.map(analysis => (
                  <div key={analysis.paneId} className={`result-card status-${analysis.analysisStatus}`}>
                    <div className="card-header">
                      <div className="card-model-info">
                        <span className="card-provider">{analysis.provider}</span>
                        <span className="card-model">{analysis.modelName}</span>
                        <span className="card-lang">{analysis.language}</span>
                      </div>
                      {analysis.analysisStatus === 'done' && <ScoreRing score={analysis.overallScore} />}
                      {analysis.analysisStatus === 'analyzing' && <div className="card-loading"><div className="loading-ring" /></div>}
                      {analysis.analysisStatus === 'error' && <span className="card-error-icon">⚠️</span>}
                    </div>

                    {analysis.analysisStatus === 'error' && <div className="card-error">{analysis.errorMessage}</div>}
                    {analysis.analysisStatus === 'analyzing' && (
                      <div className="card-analyzing"><div className="analyzing-bar" /><span>Running deep analysis…</span></div>
                    )}

                    {analysis.analysisStatus === 'done' && (
                      <div className="card-body">
                        {activeTab === 'overview' && (
                          <div className="tab-content">
                            <div className="stat-row">
                              <div className="stat-item"><span className="stat-label">Lines of Code</span><span className="stat-value">{analysis.linesOfCode}</span></div>
                              <div className="stat-item"><span className="stat-label">Cyclomatic</span><span className="stat-value">{analysis.cyclomaticComplexity}</span></div>
                              <div className="stat-item"><span className="stat-label">Security Issues</span><span className={`stat-value ${analysis.securityIssues.length > 0 ? 'stat-warn' : 'stat-ok'}`}>{analysis.securityIssues.length}</span></div>
                              <div className="stat-item"><span className="stat-label">Bugs Found</span><span className={`stat-value ${analysis.bugs.length > 0 ? 'stat-warn' : 'stat-ok'}`}>{analysis.bugs.length}</span></div>
                            </div>
                            <ReadabilityMeter score={analysis.readabilityScore} grade={analysis.readabilityGrade} />
                            <ComplexityBar label="Time Complexity" value={analysis.timeComplexity} />
                            <ComplexityBar label="Space Complexity" value={analysis.spaceComplexity} />
                          </div>
                        )}
                        {activeTab === 'complexity' && (
                          <div className="tab-content">
                            <ComplexityBar label="⏱ Time" value={analysis.timeComplexity} />
                            <ComplexityBar label="🗃 Space" value={analysis.spaceComplexity} />
                            <div className="complexity-detail">
                              <span className="complexity-label">Cyclomatic Complexity</span>
                              <span className={`complexity-value complexity-${analysis.cyclomaticComplexity > 10 ? 'high' : analysis.cyclomaticComplexity > 5 ? 'medium' : 'low'}`}>{analysis.cyclomaticComplexity}</span>
                            </div>
                            <ReadabilityMeter score={analysis.readabilityScore} grade={analysis.readabilityGrade} />
                          </div>
                        )}
                        {activeTab === 'security' && <div className="tab-content"><IssueList items={analysis.securityIssues} type="security" /></div>}
                        {activeTab === 'bugs' && <div className="tab-content"><IssueList items={analysis.bugs} type="bug" /></div>}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};
