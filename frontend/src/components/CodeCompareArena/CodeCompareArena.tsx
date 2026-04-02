import React, { useState, useMemo, useCallback } from 'react';
import { useAppStore } from '../../store';
import './CodeCompareArena.css';

// ── Types ─────────────────────────────────────────────────────────────────────

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

interface ExecutionResult {
  success: boolean;
  stdout: string;
  stderr: string;
  compile_output: string;
  status: string;
  time?: number;
  memory?: number;
  engine: string;
}

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
  analysisStatus: 'idle' | 'analyzing' | 'executing' | 'done' | 'error';
  errorMessage?: string;
  executionResult?: ExecutionResult;
  manualWinner?: boolean;
}

interface CodeCompareArenaProps {
  isVisible: boolean;
  onClose: () => void;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const extractCodeFromMessages = (messages: any[]): { code: string; language: string } => {
  const assistantMsgs = [...messages].reverse().filter(m => m.role === 'assistant');
  for (const msg of assistantMsgs) {
    const match = msg.content.match(/```(\w*)\n?([\s\S]*?)```/);
    if (match) return { code: match[2].trim(), language: match[1] || '' };
  }
  const last = assistantMsgs[0];
  return { code: last ? last.content.trim() : '', language: '' };
};

const detectLanguage = (code: string, hint: string): string => {
  if (hint) {
    const h = hint.toLowerCase();
    if (h.includes('python') || h === 'py') return 'Python';
    if (h.includes('javascript') || h === 'js') return 'JavaScript';
    if (h.includes('typescript') || h === 'ts') return 'TypeScript';
    if (h.includes('java')) return 'Java';
    if (h.includes('cpp') || h === 'c++') return 'C++';
    if (h === 'c') return 'C';
    if (h.includes('go')) return 'Go';
    if (h.includes('rust') || h === 'rs') return 'Rust';
  }
  if (/def |import |print\(|:\s*$/.test(code)) return 'Python';
  if (/function |const |let |var |=>/.test(code)) return 'JavaScript';
  if (/public class|System\.out|void main/.test(code)) return 'Java';
  if (/#include|int main|std::/.test(code)) return 'C++';
  if (/func |package main|fmt\./.test(code)) return 'Go';
  if (/fn |let mut|println!/.test(code)) return 'Rust';
  return 'Unknown';
};

const normalizeCode = (code: string): string => {
  const lines = code.split('\n');
  while (lines.length && !lines[0].trim()) lines.shift();
  while (lines.length && !lines[lines.length-1].trim()) lines.pop();
  const indents = lines.filter(l => l.trim()).map(l => l.length - l.trimStart().length);
  const minIndent = indents.length ? Math.min(...indents) : 0;
  return lines.map(l => l.slice(minIndent)).join('\n');
};

// Compute inline diff between two code strings — returns array of {type, text}
const computeDiff = (codeA: string, codeB: string) => {
  const linesA = codeA.split('\n');
  const linesB = codeB.split('\n');
  const result: { type: 'same' | 'add' | 'remove'; text: string; lineA?: number; lineB?: number }[] = [];
  const maxLen = Math.max(linesA.length, linesB.length);
  for (let i = 0; i < maxLen; i++) {
    const a = linesA[i];
    const b = linesB[i];
    if (a === undefined) {
      result.push({ type: 'add', text: b, lineB: i + 1 });
    } else if (b === undefined) {
      result.push({ type: 'remove', text: a, lineA: i + 1 });
    } else if (a === b) {
      result.push({ type: 'same', text: a, lineA: i + 1, lineB: i + 1 });
    } else {
      result.push({ type: 'remove', text: a, lineA: i + 1 });
      result.push({ type: 'add', text: b, lineB: i + 1 });
    }
  }
  return result;
};

// ── Sub-components ────────────────────────────────────────────────────────────

const ScoreRing: React.FC<{ score: number; size?: number }> = ({ score, size = 72 }) => {
  const r = (size / 2) - 6;
  const circ = 2 * Math.PI * r;
  const offset = circ - (score / 100) * circ;
  const color = score >= 80 ? '#22c55e' : score >= 60 ? '#f59e0b' : score >= 40 ? '#f97316' : '#ef4444';
  return (
    <svg width={size} height={size} className="score-ring">
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="rgba(0,0,0,0.08)" strokeWidth="5" />
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={color} strokeWidth="5"
        strokeDasharray={circ} strokeDashoffset={offset} strokeLinecap="round"
        transform={`rotate(-90 ${size/2} ${size/2})`} style={{ transition: 'stroke-dashoffset 0.8s ease' }} />
      <text x="50%" y="50%" dominantBaseline="middle" textAnchor="middle"
        fill="#111111" fontSize={size * 0.22} fontWeight="700">{score}</text>
    </svg>
  );
};

const SeverityBadge: React.FC<{ severity: string }> = ({ severity }) => (
  <span className={`severity-badge severity-${severity}`}>{severity}</span>
);

const ComplexityBar: React.FC<{ label: string; value: string }> = ({ label, value }) => {
  const level = (value.includes('n²') || value.includes('n^2') || value.includes('2^n')) ? 'high'
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

const ExecutionPanel: React.FC<{ result?: ExecutionResult; isExecuting?: boolean }> = ({ result, isExecuting }) => {
  if (isExecuting) {
    return <div className="exec-running"><div className="loading-ring" /><span>Executing code...</span></div>;
  }
  if (!result) {
    return <div className="exec-empty"><span>▶</span><span>Click "Run Code" to execute</span></div>;
  }
  return (
    <div className="exec-result">
      <div className={`exec-status ${result.success ? 'exec-ok' : 'exec-fail'}`}>
        {result.success ? '✅' : '❌'} {result.status}
        {result.time && <span className="exec-meta"> · {result.time}s</span>}
        {result.memory && <span className="exec-meta"> · {result.memory}KB</span>}
        <span className="exec-engine"> via {result.engine}</span>
      </div>
      {result.compile_output && (
        <div className="exec-section">
          <span className="exec-section-label">Compile Output</span>
          <pre className="exec-output exec-compile">{result.compile_output}</pre>
        </div>
      )}
      {result.stdout && (
        <div className="exec-section">
          <span className="exec-section-label">stdout</span>
          <pre className="exec-output exec-stdout">{result.stdout}</pre>
        </div>
      )}
      {result.stderr && (
        <div className="exec-section">
          <span className="exec-section-label">stderr</span>
          <pre className="exec-output exec-stderr">{result.stderr}</pre>
        </div>
      )}
    </div>
  );
};

const DiffViewer: React.FC<{ analyses: CodeAnalysis[]; paneAId: string; paneBId: string }> = ({ analyses, paneAId, paneBId }) => {
  const a = analyses.find(x => x.paneId === paneAId);
  const b = analyses.find(x => x.paneId === paneBId);
  if (!a || !b) return <div className="diff-empty">Select two panes to compare</div>;

  const diff = computeDiff(a.code, b.code);
  const changes = diff.filter(d => d.type !== 'same').length;

  return (
    <div className="diff-container">
      <div className="diff-header-row">
        <div className="diff-col-label">{a.modelName}</div>
        <div className="diff-col-label">{b.modelName}</div>
      </div>
      <div className="diff-stats">
        <span className="diff-stat diff-add">+{diff.filter(d => d.type === 'add').length} lines</span>
        <span className="diff-stat diff-remove">-{diff.filter(d => d.type === 'remove').length} lines</span>
        <span className="diff-stat">{changes} total changes</span>
      </div>
      <div className="diff-body">
        <div className="diff-col">
          {diff.filter(d => d.type !== 'add').map((line, i) => (
            <div key={i} className={`diff-line diff-line-${line.type}`}>
              <span className="diff-lineno">{line.lineA ?? ''}</span>
              <span className="diff-linetext">{line.text}</span>
            </div>
          ))}
        </div>
        <div className="diff-col">
          {diff.filter(d => d.type !== 'remove').map((line, i) => (
            <div key={i} className={`diff-line diff-line-${line.type}`}>
              <span className="diff-lineno">{line.lineB ?? ''}</span>
              <span className="diff-linetext">{line.text}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

// ── Main Component ────────────────────────────────────────────────────────────

export const CodeCompareArena: React.FC<CodeCompareArenaProps> = ({ isVisible, onClose }) => {
  const { activePanes } = useAppStore();
  const [analyses, setAnalyses]           = useState<Record<string, CodeAnalysis>>({});
  const [activeTab, setActiveTab]         = useState<'overview' | 'complexity' | 'security' | 'bugs' | 'execution' | 'diff'>('overview');
  const [isRunning, setIsRunning]         = useState(false);
  const [selectedPaneIds, setSelectedPaneIds] = useState<string[]>([]);
  const [manualWinnerId, setManualWinnerId]   = useState<string | null>(null);
  const [diffPaneA, setDiffPaneA]         = useState<string>('');
  const [diffPaneB, setDiffPaneB]         = useState<string>('');
  const [isExporting, setIsExporting]     = useState(false);
  const [isExecuting, setIsExecuting]     = useState(false);

  const paneList = Object.values(activePanes);

  const togglePane = (id: string) =>
    setSelectedPaneIds(prev => prev.includes(id) ? prev.filter(p => p !== id) : [...prev, id]);

  const runAnalysis = async () => {
    const targets = selectedPaneIds.length > 0
      ? paneList.filter(p => selectedPaneIds.includes(p.id))
      : paneList;
    if (targets.length === 0) return;
    setIsRunning(true);
    setManualWinnerId(null);

    const initial: Record<string, CodeAnalysis> = {};
    targets.forEach(pane => {
      const { code, language } = extractCodeFromMessages(pane.messages);
      const normalizedCode = normalizeCode(code);
      const detectedLang   = detectLanguage(normalizedCode, language);
      initial[pane.id] = {
        paneId: pane.id, modelName: pane.modelInfo.name, provider: pane.modelInfo.provider,
        code: normalizedCode, language: detectedLang,
        timeComplexity: '—', spaceComplexity: '—',
        readabilityScore: 0, readabilityGrade: '—',
        securityIssues: [], bugs: [],
        linesOfCode: normalizedCode.split('\n').filter(l => l.trim()).length,
        cyclomaticComplexity: 1, overallScore: 0,
        analysisStatus: normalizedCode ? 'analyzing' : 'error',
        errorMessage: normalizedCode ? undefined : 'No code found in conversation'
      };
    });
    setAnalyses(initial);

    // Set default diff panes
    const validIds = targets.filter(p => initial[p.id].analysisStatus === 'analyzing').map(p => p.id);
    if (validIds.length >= 2) {
      setDiffPaneA(validIds[0]);
      setDiffPaneB(validIds[1]);
    }

    await Promise.all(
      targets.filter(p => initial[p.id].analysisStatus === 'analyzing').map(async pane => {
        try {
          const resp = await fetch('http://localhost:5000/analyze-code', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              code: initial[pane.id].code,
              model_name: pane.modelInfo.name,
              language: initial[pane.id].language
            })
          });
          if (!resp.ok) throw new Error(`Backend error: ${resp.status}`);
          const result = await resp.json();
          setAnalyses(prev => ({
            ...prev,
            [pane.id]: {
              ...prev[pane.id], ...result,
              linesOfCode: result.linesOfCode || prev[pane.id].linesOfCode,
              cyclomaticComplexity: result.cyclomaticComplexity || prev[pane.id].cyclomaticComplexity,
              analysisStatus: 'done'
            }
          }));
        } catch (e) {
          setAnalyses(prev => ({
            ...prev,
            [pane.id]: {
              ...prev[pane.id], analysisStatus: 'error',
              errorMessage: `Analysis failed: ${e instanceof Error ? e.message : 'Unknown'}`
            }
          }));
        }
      })
    );
    setIsRunning(false);
  };

  const runExecution = async () => {
    const targets = Object.values(analyses).filter(a => a.analysisStatus === 'done' && a.code);
    if (targets.length === 0) return;
    setIsExecuting(true);
    setActiveTab('execution');

    await Promise.all(targets.map(async (analysis) => {
      setAnalyses(prev => ({
        ...prev,
        [analysis.paneId]: { ...prev[analysis.paneId], analysisStatus: 'executing' }
      }));
      try {
        const resp = await fetch('http://localhost:5000/execute-code', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ code: analysis.code, language: analysis.language })
        });
        if (!resp.ok) throw new Error(`Execution error: ${resp.status}`);
        const result: ExecutionResult = await resp.json();
        setAnalyses(prev => ({
          ...prev,
          [analysis.paneId]: { ...prev[analysis.paneId], executionResult: result, analysisStatus: 'done' }
        }));
      } catch (e) {
        setAnalyses(prev => ({
          ...prev,
          [analysis.paneId]: {
            ...prev[analysis.paneId],
            analysisStatus: 'done',
            executionResult: {
              success: false, stdout: '', stderr: String(e),
              compile_output: '', status: 'Error', engine: 'none'
            }
          }
        }));
      }
    }));
    setIsExecuting(false);
  };

  const exportPDF = async () => {
    const results = Object.values(analyses);
    if (!results.length) return;
    setIsExporting(true);
    try {
      const resp = await fetch('http://localhost:5000/export-report', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ results, title: 'Code Compare Arena Report' })
      });
      if (!resp.ok) throw new Error(`Export failed: ${resp.status}`);
      const blob = await resp.blob();
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement('a');
      a.href     = url;
      a.download = `code-compare-${Date.now()}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      alert(`PDF export failed: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setIsExporting(false);
    }
  };

  const analysisResults = useMemo(() => Object.values(analyses), [analyses]);
  const hasResults      = analysisResults.some(a => a.analysisStatus === 'done');
  const doneResults     = analysisResults.filter(a => a.analysisStatus === 'done');

  const winner = useMemo(() => {
    if (manualWinnerId) return analysisResults.find(a => a.paneId === manualWinnerId) || null;
    if (doneResults.length < 2) return null;
    return doneResults.reduce((a, b) => a.overallScore > b.overallScore ? a : b);
  }, [doneResults, manualWinnerId, analysisResults]);

  if (!isVisible) return null;

  const TABS = [
    { id: 'overview',   label: '📊 Overview' },
    { id: 'complexity', label: '⏱️ Complexity' },
    { id: 'security',   label: '🔐 Security' },
    { id: 'bugs',       label: '🐛 Bugs' },
    { id: 'execution',  label: '▶ Execution' },
    { id: 'diff',       label: '🔀 Diff' },
  ] as const;

  return (
    <div className="arena-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="arena-modal">

        {/* Header */}
        <div className="arena-header">
          <div className="arena-header-left">
            <span className="arena-icon">⚔️</span>
            <div>
              <h2 className="arena-title">Code Compare Arena</h2>
              <p className="arena-subtitle">AI-powered analysis across all panes</p>
            </div>
          </div>
          <div className="arena-header-actions">
            {hasResults && (
              <>
                <button className="arena-action-btn exec-btn" onClick={runExecution} disabled={isExecuting || isRunning}>
                  {isExecuting ? '⟳ Running…' : '▶ Run Code'}
                </button>
                <button className="arena-action-btn export-btn" onClick={exportPDF} disabled={isExporting}>
                  {isExporting ? '⟳ Exporting…' : '📄 Export PDF'}
                </button>
              </>
            )}
            <button className="arena-close" onClick={onClose}>×</button>
          </div>
        </div>

        {paneList.length === 0 ? (
          <div className="arena-empty">
            <div className="arena-empty-icon">💬</div>
            <h3>No active panes</h3>
            <p>Broadcast a coding prompt to multiple models first.</p>
          </div>
        ) : (
          <>
            {/* Pane Selector */}
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

            {/* Winner Banner */}
            {winner && (
              <div className="winner-banner">
                <span className="winner-trophy">{manualWinnerId ? '👑' : '🏆'}</span>
                <span className="winner-text">
                  {manualWinnerId ? 'Selected winner' : 'Best overall'}:{' '}
                  <strong>{winner.modelName}</strong>
                  <span className="winner-score">({winner.overallScore}/100)</span>
                </span>
                {manualWinnerId && (
                  <button className="clear-winner-btn" onClick={() => setManualWinnerId(null)}>
                    Clear
                  </button>
                )}
              </div>
            )}

            {/* Tabs */}
            {hasResults && (
              <div className="arena-tabs">
                {TABS.map(tab => (
                  <button key={tab.id}
                    className={`arena-tab ${activeTab === tab.id ? 'active' : ''}`}
                    onClick={() => setActiveTab(tab.id)}>
                    {tab.label}
                  </button>
                ))}
              </div>
            )}

            {/* Diff Tab Controls */}
            {activeTab === 'diff' && hasResults && doneResults.length >= 2 && (
              <div className="diff-controls">
                <label>Compare:</label>
                <select value={diffPaneA} onChange={e => setDiffPaneA(e.target.value)}>
                  {doneResults.map(a => (
                    <option key={a.paneId} value={a.paneId}>{a.modelName}</option>
                  ))}
                </select>
                <span>vs</span>
                <select value={diffPaneB} onChange={e => setDiffPaneB(e.target.value)}>
                  {doneResults.map(a => (
                    <option key={a.paneId} value={a.paneId}>{a.modelName}</option>
                  ))}
                </select>
              </div>
            )}

            {/* Diff View (full width) */}
            {activeTab === 'diff' && hasResults && (
              <div className="arena-diff-panel">
                <DiffViewer analyses={analysisResults} paneAId={diffPaneA} paneBId={diffPaneB} />
              </div>
            )}

            {/* Results Grid */}
            {analysisResults.length > 0 && activeTab !== 'diff' && (
              <div className="arena-results">
                {analysisResults.map(analysis => (
                  <div key={analysis.paneId}
                    className={`result-card status-${analysis.analysisStatus} ${winner?.paneId === analysis.paneId ? 'winner-card' : ''}`}>

                    {/* Card Header */}
                    <div className="card-header">
                      <div className="card-model-info">
                        <span className="card-provider">{analysis.provider}</span>
                        <span className="card-model">{analysis.modelName}</span>
                        {analysis.language !== 'Unknown' && (
                          <span className="card-lang">{analysis.language}</span>
                        )}
                      </div>
                      <div className="card-header-right">
                        {analysis.analysisStatus === 'done' && <ScoreRing score={analysis.overallScore} />}
                        {(analysis.analysisStatus === 'analyzing' || analysis.analysisStatus === 'executing') && (
                          <div className="card-loading"><div className="loading-ring" /></div>
                        )}
                        {analysis.analysisStatus === 'error' && <span className="card-error-icon">⚠️</span>}
                        {analysis.analysisStatus === 'done' && (
                          <button
                            className={`select-winner-btn ${manualWinnerId === analysis.paneId ? 'selected' : ''}`}
                            onClick={() => setManualWinnerId(
                              manualWinnerId === analysis.paneId ? null : analysis.paneId
                            )}
                            title="Select as winner">
                            {manualWinnerId === analysis.paneId ? '👑' : '🏅'}
                          </button>
                        )}
                      </div>
                    </div>

                    {/* Error state */}
                    {analysis.analysisStatus === 'error' && (
                      <div className="card-error">{analysis.errorMessage}</div>
                    )}

                    {/* Analyzing state */}
                    {(analysis.analysisStatus === 'analyzing' || analysis.analysisStatus === 'executing') && (
                      <div className="card-analyzing">
                        <div className="analyzing-bar" />
                        <span>{analysis.analysisStatus === 'executing' ? 'Executing code…' : 'Running deep analysis…'}</span>
                      </div>
                    )}

                    {/* Done state */}
                    {analysis.analysisStatus === 'done' && (
                      <div className="card-body">
                        {activeTab === 'overview' && (
                          <div className="tab-content">
                            <div className="stat-row">
                              <div className="stat-item">
                                <span className="stat-label">Lines of Code</span>
                                <span className="stat-value">{analysis.linesOfCode}</span>
                              </div>
                              <div className="stat-item">
                                <span className="stat-label">Cyclomatic</span>
                                <span className="stat-value">{analysis.cyclomaticComplexity}</span>
                              </div>
                              <div className="stat-item">
                                <span className="stat-label">Security</span>
                                <span className={`stat-value ${analysis.securityIssues.length > 0 ? 'stat-warn' : 'stat-ok'}`}>
                                  {analysis.securityIssues.length}
                                </span>
                              </div>
                              <div className="stat-item">
                                <span className="stat-label">Bugs</span>
                                <span className={`stat-value ${analysis.bugs.length > 0 ? 'stat-warn' : 'stat-ok'}`}>
                                  {analysis.bugs.length}
                                </span>
                              </div>
                            </div>
                            <ReadabilityMeter score={analysis.readabilityScore} grade={analysis.readabilityGrade} />
                            <ComplexityBar label="Time Complexity"  value={analysis.timeComplexity} />
                            <ComplexityBar label="Space Complexity" value={analysis.spaceComplexity} />
                          </div>
                        )}
                        {activeTab === 'complexity' && (
                          <div className="tab-content">
                            <ComplexityBar label="⏱ Time"  value={analysis.timeComplexity} />
                            <ComplexityBar label="🗃 Space" value={analysis.spaceComplexity} />
                            <div className="complexity-detail">
                              <span className="complexity-label">Cyclomatic Complexity</span>
                              <span className={`complexity-value complexity-${
                                analysis.cyclomaticComplexity > 10 ? 'high'
                                : analysis.cyclomaticComplexity > 5 ? 'medium' : 'low'
                              }`}>{analysis.cyclomaticComplexity}</span>
                            </div>
                            <ReadabilityMeter score={analysis.readabilityScore} grade={analysis.readabilityGrade} />
                          </div>
                        )}
                        {activeTab === 'security' && (
                          <div className="tab-content">
                            <IssueList items={analysis.securityIssues} type="security" />
                          </div>
                        )}
                        {activeTab === 'bugs' && (
                          <div className="tab-content">
                            <IssueList items={analysis.bugs} type="bug" />
                          </div>
                        )}
                        {activeTab === 'execution' && (
                          <div className="tab-content">
                            <ExecutionPanel
                              result={analysis.executionResult}
                              isExecuting={analysis.analysisStatus === 'executing'}
                            />
                          </div>
                        )}
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
