"""
Multi-LLM Broadcast Workspace Backend
FastAPI application with WebSocket support for real-time LLM streaming
"""

import asyncio
import ast
import json
import logging
import os
import re
import subprocess
import tempfile
from datetime import datetime
import sys
import io
import uuid
import base64

# Force UTF-8 encoding for standard streams to prevent Windows crash on emojis
if isinstance(sys.stdout, io.TextIOWrapper) and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
if isinstance(sys.stderr, io.TextIOWrapper) and sys.stderr.encoding.lower() != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8')

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, UploadFile, File, Form, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import uvicorn
from dotenv import load_dotenv
import httpx

load_dotenv()


from models import (
    BroadcastRequest, BroadcastResponse, SendToRequest, SendToResponse,
    SummaryRequest, SummaryResponse, HealthResponse, Session, ChatPane,
    Message, StreamEvent, ModelSelection, ProvenanceInfo
)
from adapters.registry import registry
from broadcast_orchestrator import BroadcastOrchestrator
from session_manager import SessionManager
from error_handler import error_handler
from websocket_manager import connection_manager
from web_search import search_web, should_search_web
from knowledge_manager import knowledge_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

google_key = os.getenv("GOOGLE_API_KEY")
groq_key = os.getenv("GROQ_API_KEY")
print(f"🔑 Google API Key: {'✅ Loaded' if google_key else '❌ Missing'}")
print(f"🔑 Groq API Key: {'✅ Loaded' if groq_key else '❌ Missing'}")

app = FastAPI(
    title="Multi-LLM Broadcast Workspace API",
    description="Backend API for broadcasting prompts to multiple LLM providers",
    version="0.2.0"
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global instances
session_manager = SessionManager()
broadcast_orchestrator = BroadcastOrchestrator(registry, session_manager)
manager               = connection_manager


# ── Helpers ───────────────────────────────────────────────────────────────────

def _python_static_analysis(code: str) -> dict:
    """Run real Python static analysis using ast + basic checks."""
    result = {
        "linesOfCode": len([l for l in code.splitlines() if l.strip()]),
        "cyclomaticComplexity": 1,
        "staticIssues": [],
    }

    # AST-based cyclomatic complexity
    try:
        tree = ast.parse(code)
        decision_nodes = sum(
            1 for node in ast.walk(tree)
            if isinstance(node, (ast.If, ast.For, ast.While, ast.ExceptHandler,
                                  ast.With, ast.Assert, ast.comprehension))
        )
        result["cyclomaticComplexity"] = 1 + decision_nodes

        # Check for common issues via AST
        for node in ast.walk(tree):
            # Bare except
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                result["staticIssues"].append({
                    "severity": "medium",
                    "title": "Bare except clause",
                    "description": "Catching all exceptions silently can hide bugs.",
                    "line": node.lineno
                })
            # Use of eval
            if isinstance(node, ast.Call):
                func = node.func
                name = ""
                if isinstance(func, ast.Name):
                    name = func.id
                elif isinstance(func, ast.Attribute):
                    name = func.attr
                if name == "eval":
                    result["staticIssues"].append({
                        "severity": "high",
                        "title": "Use of eval()",
                        "description": "eval() is a security risk — avoid executing dynamic strings.",
                        "line": node.lineno
                    })
                if name == "exec":
                    result["staticIssues"].append({
                        "severity": "high",
                        "title": "Use of exec()",
                        "description": "exec() can execute arbitrary code — use with caution.",
                        "line": node.lineno
                    })

    except SyntaxError as e:
        result["staticIssues"].append({
            "severity": "critical",
            "title": "Syntax Error",
            "description": str(e),
            "line": e.lineno
        })

    # Regex-based checks (fast, no deps)
    lines = code.splitlines()
    for i, line in enumerate(lines, 1):
        if re.search(r'password\s*=\s*["\'][^"\']+["\']', line, re.IGNORECASE):
            result["staticIssues"].append({
                "severity": "critical",
                "title": "Hardcoded password",
                "description": "Password appears to be hardcoded in source code.",
                "line": i
            })
        if re.search(r'(secret|api_key|token)\s*=\s*["\'][^"\']{8,}["\']', line, re.IGNORECASE):
            result["staticIssues"].append({
                "severity": "high",
                "title": "Hardcoded secret/token",
                "description": "Secret or API key appears hardcoded — use environment variables.",
                "line": i
            })

    return result


def _js_static_analysis(code: str) -> dict:
    """Basic JS/TS static analysis using regex (no eslint dependency)."""
    result = {
        "linesOfCode": len([l for l in code.splitlines() if l.strip()]),
        "cyclomaticComplexity": 1,
        "staticIssues": [],
    }

    decision_keywords = re.findall(r'\b(if|else if|for|while|switch|catch|\?)\b', code)
    result["cyclomaticComplexity"] = 1 + len(decision_keywords)

    lines = code.splitlines()
    for i, line in enumerate(lines, 1):
        if re.search(r'\beval\s*\(', line):
            result["staticIssues"].append({
                "severity": "high", "title": "Use of eval()",
                "description": "eval() executes arbitrary code — major security risk.", "line": i
            })
        if re.search(r'innerHTML\s*=', line):
            result["staticIssues"].append({
                "severity": "medium", "title": "innerHTML assignment",
                "description": "Direct innerHTML assignment can lead to XSS attacks.", "line": i
            })
        if re.search(r'document\.write\s*\(', line):
            result["staticIssues"].append({
                "severity": "medium", "title": "document.write()",
                "description": "document.write() is deprecated and can cause XSS.", "line": i
            })
        if re.search(r'(password|secret|apiKey|api_key)\s*[:=]\s*["\'][^"\']{4,}["\']', line, re.IGNORECASE):
            result["staticIssues"].append({
                "severity": "critical", "title": "Hardcoded credential",
                "description": "Credential appears hardcoded — use environment variables.", "line": i
            })
        if re.search(r'==(?!=)', line) and not re.search(r'===', line):
            result["staticIssues"].append({
                "severity": "low", "title": "Loose equality (==)",
                "description": "Use === for strict equality to avoid type coercion bugs.", "line": i
            })

    return result


def _normalize_code(code: str) -> str:
    """Normalize code: strip leading/trailing blank lines, consistent indentation."""
    lines = code.splitlines()
    # Remove leading/trailing blank lines
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    # Detect minimum indentation and strip it
    indents = [len(l) - len(l.lstrip()) for l in lines if l.strip()]
    min_indent = min(indents) if indents else 0
    normalized = [l[min_indent:] if len(l) >= min_indent else l for l in lines]
    return "\n".join(normalized)


# Judge0 language ID map
JUDGE0_LANG_MAP = {
    "python": 71,
    "javascript": 63,
    "typescript": 74,
    "java": 62,
    "c": 50,
    "c++": 54,
    "go": 60,
    "rust": 73,
}

JUDGE0_BASE = "https://judge0-ce.p.rapidapi.com"


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"message": "Multi-LLM Broadcast Workspace API v0.2"}


@app.post("/analyze-code")
async def analyze_code(request: Request):
    """
    Analyze code using:
    1. Real AST/regex static analysis (Python/JS)
    2. LLM (Groq) for complexity + readability + overall score
    """
    body      = await request.json()
    code      = body.get("code", "")
    model_name = body.get("model_name", "unknown")
    language  = body.get("language", "").lower()

    # Normalize code first
    code = _normalize_code(code)

    # Run real static analysis
    if "python" in language:
        static = _python_static_analysis(code)
    elif any(x in language for x in ["javascript", "typescript", "js", "ts"]):
        static = _js_static_analysis(code)
    else:
        # Fallback: basic line count + regex for all languages
        static = {
            "linesOfCode": len([l for l in code.splitlines() if l.strip()]),
            "cyclomaticComplexity": 1 + len(re.findall(r'\b(if|else|for|while|switch|catch)\b', code)),
            "staticIssues": [],
        }

    # LLM analysis for complexity, readability, bugs, overall score
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY not set in .env")

    prompt = f"""You are a senior software engineer. Analyze this {language or 'code'} and return ONLY a valid JSON object.

Code from {model_name}:
{code}

Return exactly this JSON (no markdown, no extra text):
{{
  "timeComplexity": "O(?)",
  "spaceComplexity": "O(?)",
  "readabilityScore": 0,
  "readabilityGrade": "A",
  "securityIssues": [
    {{"severity": "low", "title": "example", "description": "example", "line": null}}
  ],
  "bugs": [
    {{"severity": "low", "title": "example", "description": "example", "line": null}}
  ],
  "overallScore": 0
}}

Rules:
- readabilityScore 0-100, readabilityGrade A/B/C/D/F (must be consistent: 80+ = A, 60-79 = B, 40-59 = C, 20-39 = D, <20 = F)
- overallScore 0-100 combining complexity, readability, security, bugs
- If no issues found, return empty arrays (not example items)
- Return ONLY the JSON"""

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.1-8b-instant",
                "max_tokens": 1000,
                "temperature": 0.1,
                "messages": [{"role": "user", "content": prompt}]
            }
        )

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Groq error: {resp.text}")

    text = resp.json()["choices"][0]["message"]["content"]
    clean = re.sub(r'```(?:json)?', '', text).replace('```', '').strip()

    try:
        llm_result = json.loads(clean)
    except Exception:
        llm_result = {
            "timeComplexity": "N/A", "spaceComplexity": "N/A",
            "readabilityScore": 50, "readabilityGrade": "C",
            "securityIssues": [], "bugs": [], "overallScore": 50
        }

    # Merge static analysis issues into LLM result
    all_security = llm_result.get("securityIssues", []) + static.get("staticIssues", [])

    return {
        **llm_result,
        "linesOfCode": static["linesOfCode"],
        "cyclomaticComplexity": static["cyclomaticComplexity"],
        "securityIssues": all_security,
    }


@app.post("/execute-code")
async def execute_code(request: Request):
    """
    Execute code via Judge0 CE (free, cloud-based, 50+ languages).
    Falls back to local Python subprocess for Python code if Judge0 is unavailable.
    """
    body     = await request.json()
    code     = body.get("code", "")
    language = body.get("language", "python").lower()
    stdin    = body.get("stdin", "")

    if not code.strip():
        raise HTTPException(status_code=400, detail="No code provided")

    # Normalize code
    code = _normalize_code(code)

    # Try Judge0 first
    lang_id = None
    for key, lid in JUDGE0_LANG_MAP.items():
        if key in language:
            lang_id = lid
            break

    if lang_id:
        try:
            headers = {
                "Content-Type": "application/json",
                "X-RapidAPI-Host": "judge0-ce.p.rapidapi.com",
            }
            if judge0_key:
                headers["X-RapidAPI-Key"] = judge0_key

            import base64
            async with httpx.AsyncClient(timeout=15) as client:
                # Submit
                sub_resp = await client.post(
                    f"{JUDGE0_BASE}/submissions?base64_encoded=true&wait=false",
                    headers=headers,
                    json={
                        "source_code": base64.b64encode(code.encode()).decode(),
                        "language_id": lang_id,
                        "stdin": base64.b64encode(stdin.encode()).decode() if stdin else "",
                    }
                )
                if sub_resp.status_code not in (200, 201):
                    raise Exception(f"Judge0 submit failed: {sub_resp.status_code}")

                token = sub_resp.json().get("token")
                if not token:
                    raise Exception("No token from Judge0")

                # Poll for result (max 10s)
                for _ in range(10):
                    await asyncio.sleep(1)
                    res_resp = await client.get(
                        f"{JUDGE0_BASE}/submissions/{token}?base64_encoded=true",
                        headers=headers
                    )
                    result = res_resp.json()
                    status_id = result.get("status", {}).get("id", 0)
                    if status_id >= 3:  # Done (3=Accepted, 4+=error)
                        def dec(val):
                            if val:
                                try:
                                    return base64.b64decode(val).decode("utf-8", errors="replace")
                                except Exception:
                                    return val
                            return ""

                        return {
                            "success": status_id == 3,
                            "stdout": dec(result.get("stdout", "")),
                            "stderr": dec(result.get("stderr", "")),
                            "compile_output": dec(result.get("compile_output", "")),
                            "status": result.get("status", {}).get("description", "Unknown"),
                            "time": result.get("time"),
                            "memory": result.get("memory"),
                            "engine": "judge0"
                        }

                return {"success": False, "stdout": "", "stderr": "Execution timed out", "status": "Timeout", "engine": "judge0"}

        except Exception as e:
            logger.warning(f"Judge0 failed, falling back to local: {e}")

    # Local Python fallback
    if "python" in language:
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(code)
                tmp_path = f.name

            proc = subprocess.run(
                ["python", tmp_path],
                capture_output=True, text=True, timeout=10
            )
            os.unlink(tmp_path)
            return {
                "success": proc.returncode == 0,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "compile_output": "",
                "status": "Accepted" if proc.returncode == 0 else "Runtime Error",
                "time": None,
                "memory": None,
                "engine": "local_python"
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "stdout": "", "stderr": "Execution timed out (10s limit)", "status": "Timeout", "engine": "local_python"}
        except Exception as e:
            return {"success": False, "stdout": "", "stderr": str(e), "status": "Error", "engine": "local_python"}

    return {"success": False, "stdout": "", "stderr": f"Language '{language}' not supported for local execution. Add a Judge0 API key for full language support.", "status": "Unsupported", "engine": "none"}


@app.post("/export-report")
async def export_report(request: Request):
    """Generate a PDF report from Code Compare Arena analysis results."""
    body    = await request.json()
    results = body.get("results", [])
    title   = body.get("title", "Code Compare Arena Report")

    if not results:
        raise HTTPException(status_code=400, detail="No results to export")

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
            HRFlowable, PageBreak
        )

        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            tmp_path = f.name

        doc    = SimpleDocTemplate(tmp_path, pagesize=A4,
                                   leftMargin=2*cm, rightMargin=2*cm,
                                   topMargin=2*cm, bottomMargin=2*cm)
        styles = getSampleStyleSheet()
        story  = []

        # Title
        title_style = ParagraphStyle('Title', parent=styles['Title'],
                                     fontSize=22, textColor=colors.HexColor('#1a1a2e'),
                                     spaceAfter=6)
        sub_style   = ParagraphStyle('Sub', parent=styles['Normal'],
                                     fontSize=11, textColor=colors.HexColor('#666666'),
                                     spaceAfter=20)
        h2_style    = ParagraphStyle('H2', parent=styles['Heading2'],
                                     fontSize=14, textColor=colors.HexColor('#2d3748'),
                                     spaceBefore=14, spaceAfter=6)
        h3_style    = ParagraphStyle('H3', parent=styles['Heading3'],
                                     fontSize=11, textColor=colors.HexColor('#4a5568'),
                                     spaceBefore=8, spaceAfter=4)
        body_style  = ParagraphStyle('Body', parent=styles['Normal'],
                                     fontSize=9, textColor=colors.HexColor('#333333'),
                                     spaceAfter=4)

        story.append(Paragraph("⚔️ Code Compare Arena", title_style))
        story.append(Paragraph(f"Generated: {datetime.now().strftime('%B %d, %Y at %H:%M')}", sub_style))
        story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#6366f1')))
        story.append(Spacer(1, 0.4*cm))

        # Winner
        done = [r for r in results if r.get("analysisStatus") == "done"]
        if done:
            winner = max(done, key=lambda r: r.get("overallScore", 0))
            story.append(Paragraph(
                f"🏆 Best Overall: <b>{winner['modelName']}</b> — {winner['overallScore']}/100",
                ParagraphStyle('Winner', parent=styles['Normal'],
                               fontSize=13, textColor=colors.HexColor('#b7791f'),
                               backColor=colors.HexColor('#fffbeb'),
                               borderPadding=8, spaceAfter=16)
            ))

        # Summary table
        table_data = [["Model", "Provider", "Score", "Lines", "Cyclomatic", "Security", "Bugs", "Readability"]]
        for r in results:
            if r.get("analysisStatus") == "done":
                table_data.append([
                    r.get("modelName", ""),
                    r.get("provider", ""),
                    str(r.get("overallScore", 0)),
                    str(r.get("linesOfCode", 0)),
                    str(r.get("cyclomaticComplexity", 0)),
                    str(len(r.get("securityIssues", []))),
                    str(len(r.get("bugs", []))),
                    f"{r.get('readabilityGrade','?')} ({r.get('readabilityScore',0)}/100)",
                ])

        if len(table_data) > 1:
            story.append(Paragraph("Summary", h2_style))
            t = Table(table_data, hAlign='LEFT',
                      colWidths=[3.5*cm, 2.5*cm, 1.5*cm, 1.5*cm, 2*cm, 2*cm, 1.5*cm, 3*cm])
            t.setStyle(TableStyle([
                ('BACKGROUND',    (0,0), (-1,0), colors.HexColor('#6366f1')),
                ('TEXTCOLOR',     (0,0), (-1,0), colors.white),
                ('FONTSIZE',      (0,0), (-1,0), 9),
                ('FONTNAME',      (0,0), (-1,0), 'Helvetica-Bold'),
                ('ROWBACKGROUNDS',(0,1), (-1,-1), [colors.HexColor('#f8f9ff'), colors.white]),
                ('FONTSIZE',      (0,1), (-1,-1), 8),
                ('GRID',          (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
                ('ALIGN',         (2,0), (-1,-1), 'CENTER'),
                ('VALIGN',        (0,0), (-1,-1), 'MIDDLE'),
                ('TOPPADDING',    (0,0), (-1,-1), 5),
                ('BOTTOMPADDING', (0,0), (-1,-1), 5),
            ]))
            story.append(t)
            story.append(Spacer(1, 0.5*cm))

        # Per-model detail
        for r in results:
            if r.get("analysisStatus") != "done":
                continue

            story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#e2e8f0')))
            story.append(Paragraph(f"{r['modelName']} ({r['provider']})", h2_style))

            # Metrics row
            metrics = [
                ["Time Complexity", r.get("timeComplexity","N/A")],
                ["Space Complexity", r.get("spaceComplexity","N/A")],
                ["Readability", f"{r.get('readabilityGrade','?')} ({r.get('readabilityScore',0)}/100)"],
                ["Overall Score", f"{r.get('overallScore',0)}/100"],
            ]
            mt = Table(metrics, colWidths=[4*cm, 6*cm])
            mt.setStyle(TableStyle([
                ('FONTSIZE',  (0,0), (-1,-1), 9),
                ('TEXTCOLOR', (0,0), (0,-1), colors.HexColor('#6366f1')),
                ('FONTNAME',  (0,0), (0,-1), 'Helvetica-Bold'),
                ('GRID',      (0,0), (-1,-1), 0.3, colors.HexColor('#e2e8f0')),
                ('TOPPADDING',(0,0), (-1,-1), 4),
                ('BOTTOMPADDING',(0,0), (-1,-1), 4),
            ]))
            story.append(mt)
            story.append(Spacer(1, 0.3*cm))

            # Security issues
            sec = r.get("securityIssues", [])
            story.append(Paragraph(f"Security Issues ({len(sec)})", h3_style))
            if sec:
                for issue in sec:
                    line_info = f" — Line {issue['line']}" if issue.get('line') else ""
                    story.append(Paragraph(
                        f"<b>[{issue['severity'].upper()}]</b> {issue['title']}{line_info}: {issue['description']}",
                        body_style
                    ))
            else:
                story.append(Paragraph("✅ No security issues detected.", body_style))

            # Bugs
            bugs = r.get("bugs", [])
            story.append(Paragraph(f"Bugs ({len(bugs)})", h3_style))
            if bugs:
                for bug in bugs:
                    line_info = f" — Line {bug['line']}" if bug.get('line') else ""
                    story.append(Paragraph(
                        f"<b>[{bug['severity'].upper()}]</b> {bug['title']}{line_info}: {bug['description']}",
                        body_style
                    ))
            else:
                story.append(Paragraph("✅ No bugs detected.", body_style))

            # Execution result
            exec_result = r.get("executionResult")
            if exec_result:
                story.append(Paragraph("Execution Result", h3_style))
                status = exec_result.get("status","Unknown")
                story.append(Paragraph(f"Status: <b>{status}</b>", body_style))
                if exec_result.get("stdout"):
                    story.append(Paragraph(f"Output: {exec_result['stdout'][:500]}", body_style))
                if exec_result.get("stderr"):
                    story.append(Paragraph(f"Error: {exec_result['stderr'][:300]}", body_style))

            story.append(Spacer(1, 0.4*cm))

        doc.build(story)

        return FileResponse(
            tmp_path,
            media_type="application/pdf",
            filename=f"code-compare-report-{datetime.now().strftime('%Y%m%d-%H%M%S')}.pdf",
            background=None
        )

    except ImportError:
        raise HTTPException(status_code=500, detail="reportlab not installed. Run: pip install reportlab")
    except Exception as e:
        logger.error(f"PDF export error: {e}")
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")


@app.get("/health", response_model=HealthResponse)
async def health_check():
    try:
        provider_health  = await registry.health_check()
        connection_stats = manager.get_connection_stats()
        healthy_providers = sum(1 for s in provider_health.values() if s)
        total_providers   = len(provider_health)
        overall_status = "healthy" if healthy_providers == total_providers else (
            "unhealthy" if healthy_providers == 0 else "degraded"
        )
        return HealthResponse(status=overall_status, service="multi-llm-broadcast-workspace")
    except Exception as e:
        return HealthResponse(status="unhealthy", service="multi-llm-broadcast-workspace")



@app.post("/broadcast", response_model=BroadcastResponse)
async def create_broadcast(request: BroadcastRequest):
    """Create a broadcast request to multiple LLM providers"""
    try:
        logger.info(f"Creating broadcast for session {request.session_id} with {len(request.models)} models")
        print(f"🎯 Broadcast request: {request.models}")

        for model_selection in request.models:
            model_id = f"{model_selection.provider_id}:{model_selection.model_id}"
            print(f"🔍 Validating model: {model_id}")
            is_valid = await registry.validate_model(model_id)
            print(f"✅ Model {model_id} valid: {is_valid}")
            if not is_valid:
                raise HTTPException(status_code=400, detail=f"Invalid model: {model_id}")

        print(f"📝 Creating/getting session: {request.session_id}")
        session = session_manager.get_or_create_session(request.session_id)
        print(f"✅ Session created: {session.id}")

        pane_ids = []
        user_message_ids = {}

        for model_selection in request.models:
            model_id = f"{model_selection.provider_id}:{model_selection.model_id}"
            print(f"🔍 Getting model info for: {model_id}")
            model_info = await registry.get_model_info(model_id)
            print(f"📋 Model info: {model_info}")

            if model_info:
                user_message = Message(role="user", content=request.prompt, images=request.images)
                print(f"📝 Created user message with ID: {user_message.id}")
                pane = ChatPane(model_info=model_info, messages=[user_message])
                session.panes.append(pane)
                pane_ids.append(pane.id)
                user_message_ids[pane.id] = user_message.id

        session_manager.update_session(session)
        asyncio.create_task(broadcast_orchestrator.broadcast(request, pane_ids, connection_manager))
        # Extract facts from first message
        session = session_manager.get_session(request.session_id)
        if session and session.panes and session.panes[0].messages:
            background_tasks.add_task(
                knowledge_manager.extract_and_store_facts,
                session.panes[0].messages.copy(),
                broadcast_orchestrator.registry
            )

        return BroadcastResponse(
            session_id=request.session_id,
            pane_ids=pane_ids,
            status="started",
            user_message_ids=user_message_ids
        )
    except Exception as e:
        logger.error(f"Broadcast error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat/{pane_id}")
async def send_chat_message(pane_id: str, request: dict):
    """Send a message to a specific existing pane"""
    try:
        session_id = request.get("session_id")
        message = request.get("message")

        if not session_id or not message:
            raise HTTPException(status_code=400, detail="Missing session_id or message")

        session = session_manager.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        pane = next((p for p in session.panes if p.id == pane_id), None)
        if not pane:
            raise HTTPException(status_code=404, detail="Pane not found")

        logger.info(f"🔍 CHAT REQUEST DEBUG: Model ID: {pane.model_info.id} (Provider: {pane.model_info.provider})")
        images = request.get("images")

        user_message = Message(role="user", content=message, images=images)
        pane.messages.append(user_message)
        session_manager.update_session(session)

        if ':' in pane.model_info.id:
            provider_id, model_id = pane.model_info.id.split(':', 1)
        else:
            provider_id = pane.model_info.provider
            model_id = pane.model_info.id

        model_selection = ModelSelection(provider_id=provider_id, model_id=model_id, temperature=0.7, max_tokens=1000)
        broadcast_request = BroadcastRequest(session_id=session_id, prompt=message, images=images, models=[model_selection])

        asyncio.create_task(broadcast_orchestrator._stream_to_pane(broadcast_request, model_selection, pane_id, manager))

        return {"success": True, "pane_id": pane_id}
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/send-to", response_model=SendToResponse)
async def send_to_pane(request: SendToRequest):
    try:
        session = session_manager.get_session(request.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        source_pane = next((p for p in session.panes if p.id == request.source_pane_id), None)
        target_pane = next((p for p in session.panes if p.id == request.target_pane_id), None)

        if not source_pane:
            raise HTTPException(status_code=404, detail=f"Source pane {request.source_pane_id} not found")
        if not target_pane:
            raise HTTPException(status_code=404, detail=f"Target pane {request.target_pane_id} not found")

        selected_messages = [msg for msg_id in request.message_ids
                             for msg in source_pane.messages if msg.id == msg_id]
        if not selected_messages:
            raise HTTPException(status_code=400, detail="No valid messages found")

        messages_to_transfer = []
        if request.additional_context and request.additional_context.strip():
            messages_to_transfer.append(Message(
                role="system", content=request.additional_context.strip(),
                provenance=ProvenanceInfo(source_model="user-context",
                    source_pane_id=request.source_pane_id,
                    transfer_timestamp=datetime.now(),
                    content_hash=str(hash(request.additional_context)))
            ))

        if request.transfer_mode == "summarize":
            conversation_text = "\n\n".join([f"{m.role.upper()}: {m.content}" for m in selected_messages])
            summary_prompt = (
                f"{request.summary_instructions.strip()}\n\n" if request.summary_instructions else
                "Please provide a concise summary of the following conversation:\n\n"
            ) + conversation_text

            adapter = registry.get_adapter(source_pane.model_info.provider)
            if not adapter:
                raise HTTPException(status_code=500, detail="No adapter available")

            summary_content = ""
            async for event in adapter.stream(
                [Message(role="user", content=summary_prompt)],
                source_pane.model_info.id.split(':')[-1],
                f"summary-{request.source_pane_id}", temperature=0.3, max_tokens=500
            ):
                if event.type == "token":
                    summary_content += event.data.token
                elif event.type == "final":
                    summary_content = event.data.content
                    break

            if not summary_content.strip():
                raise HTTPException(status_code=500, detail="Empty summary response")

            messages_to_transfer.append(Message(
                role="user", content=summary_content.strip(),
                provenance=ProvenanceInfo(source_model=source_pane.model_info.id,
                    source_pane_id=request.source_pane_id,
                    transfer_timestamp=datetime.now(),
                    content_hash=str(hash(summary_content)))
            ))
        else:
            for msg in selected_messages:
                messages_to_transfer.append(Message(
                    role=msg.role if request.preserve_roles else "user",
                    content=msg.content,
                    provenance=ProvenanceInfo(source_model=source_pane.model_info.id,
                        source_pane_id=request.source_pane_id,
                        transfer_timestamp=datetime.now(),
                        content_hash=str(hash(msg.content)))
                ))

        if request.transfer_mode == "replace":
            target_pane.messages.clear()

        target_pane.messages.extend(messages_to_transfer)
        session_manager.update_session(session)

        return SendToResponse(success=True,
                              transferred_count=len(messages_to_transfer),
                              target_pane_id=request.target_pane_id)
    except Exception as e:
        import traceback
        logger.error(f"Send-to error: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Send-to error: {str(e)}")


@app.post("/summarize", response_model=SummaryResponse)
async def generate_summary(request: SummaryRequest):
    try:
        session = session_manager.get_session(request.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        content_parts = []
        for pane_id in request.pane_ids:
            pane = next((p for p in session.panes if p.id == pane_id), None)
            if pane:
                pane_content = "\n".join([f"{m.role}: {m.content}" for m in pane.messages])
                content_parts.append(f"=== {pane.model_info.name} ===\n{pane_content}")

        summaries    = {}
        summary_pane = ChatPane(model_info=session.panes[0].model_info if session.panes else None, messages=[])

        for summary_type in request.summary_types:
            summaries[summary_type] = f"{summary_type.title()} summary of {len(request.pane_ids)} conversations"
            summary_pane.messages.append(Message(role="assistant", content=summaries[summary_type]))

        session.panes.append(summary_pane)
        session_manager.update_session(session)
        return SummaryResponse(summary_pane_id=summary_pane.id, summaries=summaries, source_panes=request.pane_ids)
    except Exception as e:
        logger.error(f"Summarization error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/session/{session_id}/upload")
async def upload_session_file(session_id: str, file: UploadFile = File(...)):
    """Upload a file to the current session"""
    try:
        content = await file.read()
        file_id = str(uuid.uuid4())
        mime_type = file.content_type or "application/octet-stream"
        file_info = session_file_manager.add_file(session_id, file_id, file.filename, mime_type, content)
        return file_info
    except ValueError as e:
        logger.error(f"Upload error: {e}")
        raise HTTPException(status_code=413, detail=str(e))
    except Exception as e:
        logger.error(f"Upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/session/{session_id}/files")
async def get_session_files(session_id: str):
    """Get list of files for the current session"""
    return {"files": session_file_manager.get_files(session_id)}

@app.get("/sessions/{session_id}")
async def get_session(session_id: str):
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@app.get("/sessions")
async def list_sessions(limit: int = 50, offset: int = 0):
    sessions    = session_manager.list_sessions(limit, offset)
    total_count = len(session_manager.sessions)
    return {"sessions": sessions, "total_count": total_count, "limit": limit, "offset": offset}


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    success = session_manager.delete_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"success": True, "message": "Session deleted"}


@app.get("/models")
async def get_available_models():
    try:
        models_by_provider = await registry.discover_models()
        all_models = []
        for provider, models in models_by_provider.items():
            for model in models:
                all_models.append({
                    "id": model.id, "name": model.name, "provider": provider,
                    "max_tokens": model.max_tokens,
                    "cost_per_1k_tokens": model.cost_per_1k_tokens,
                    "supports_streaming": model.supports_streaming
                })
        return {"models": all_models, "providers": list(models_by_provider.keys()), "total_count": len(all_models)}
    except Exception as e:
        logger.error(f"Error getting models: {e}")
        raise HTTPException(status_code=500, detail="Error retrieving models")


@app.get("/providers/health")
async def get_provider_health():
    try:
        health_status = await registry.health_check()
        return {
            "providers": health_status,
            "healthy_count": sum(1 for s in health_status.values() if s),
            "total_count": len(health_status)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error checking provider health")


@app.get("/stats")
async def get_system_stats():
    try:
        return {
            "sessions":   session_manager.get_session_stats(),
            "broadcasts": {
                "active_broadcasts": sum(1 for b in broadcast_orchestrator.active_broadcasts.values() if b["status"] == "running"),
                "total_broadcasts":  len(broadcast_orchestrator.active_broadcasts)
            },
            "websocket_connections": manager.get_connection_stats(),
            "error_handler": {"provider_health": error_handler.get_provider_health()}
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error retrieving statistics")


@app.get("/system/health/detailed")
async def get_detailed_health():
    try:
        return {
            "providers": {"registry_health": await registry.health_check()},
            "websockets": manager.get_connection_stats(),
            "system": {
                "active_sessions":   len(session_manager.sessions),
                "active_broadcasts": len([b for b in broadcast_orchestrator.active_broadcasts.values() if b["status"] == "running"])
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error retrieving detailed health")


@app.post("/system/reset-circuit-breakers")
async def reset_circuit_breakers():
    try:
        reset_count = 0
        for _, cb in error_handler.circuit_breakers.items():
            if cb.state != "closed":
                cb.failure_count = 0
                cb.state         = "closed"
                cb.last_failure_time = None
                reset_count += 1
        return {"success": True, "reset_count": reset_count}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error resetting circuit breakers")


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    connection_id = None
    try:
        session_manager.get_or_create_session(session_id)
        connection_id = await manager.connect(websocket, session_id)

        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                try:
                    message = json.loads(data)
                    if message.get("type") == "ping":
                        await manager.send_to_connection(connection_id, {"type": "pong", "timestamp": datetime.now().isoformat()})
                    elif message.get("type") == "heartbeat":
                        if connection_id in manager.connections:
                            manager.connections[connection_id].last_ping = datetime.now()
                except json.JSONDecodeError:
                    pass
            except asyncio.TimeoutError:
                try:
                    await websocket.send_text('{"type":"ping"}')
                except Exception:
                    break
                if not await manager.ping_connection(connection_id):
                    break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        if connection_id:
            manager.disconnect(connection_id, "endpoint_cleanup")


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=5000,
        reload=True,
        log_level="info"
    )