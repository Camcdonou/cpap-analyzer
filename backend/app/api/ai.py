"""AI API routes — report generation and Q&A."""

import json
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..models.database import NightSession, Event, AIReport, Upload, SignalData
from ..models.schemas import (
    ReportRequest,
    ReportResponse,
    QuestionRequest,
    QuestionResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def get_db(request: Request):
    factory = request.app.state.db_session_factory
    session = factory()
    try:
        yield session
    finally:
        session.close()


# ── Helpers ───────────────────────────────────────────────────────────────

import re

def _strip_thinking(text: str) -> str:
    """
    Strip leaked chain-of-thought from model output.
    
    Some reasoning models dump their thinking into content instead of
    the reasoning field. Detect and strip it.
    """
    if not text or not text.strip():
        return text

    # If the text starts with <think> tag, strip everything up to </think>
    if '<think>' in text:
        end = text.find('</think>')
        if end >= 0:
            text = text[end + 8:]  # after </think>
        else:
            text = text.replace('<think>', '')

    # Strip leading reasoning patterns like:
    # "The user wants to know..."
    # "Let me look at..."  
    # "I need to..."
    # "Looking at the data..."
    # These typically appear before the actual answer
    lines = text.strip().split('\n')
    
    # Find the first line that looks like an actual answer (not reasoning)
    reasoning_starters = [
        'the user ', 'let me ', 'i need to ', 'i should ',
        'looking at the', 'checking the', 'first, i',
        'i\'ll ', 'i will ', 'wait,', 'actually,',
        'let\'s ', 'so the ', 'hmm,', 'well, the user',
        'to answer this', 'the question is',
    ]
    
    # Find first non-reasoning line
    first_answer_line = 0
    for i, line in enumerate(lines):
        stripped = line.strip().lower()
        if not stripped:
            continue
        # Check if this line is reasoning
        is_reasoning = any(stripped.startswith(s) for s in reasoning_starters)
        # Also check for lines that are just data analysis (e.g., "April 8: 2.7")
        if is_reasoning:
            first_answer_line = i + 1
            continue
        # If we've seen reasoning lines and hit a non-reasoning line, stop
        if first_answer_line > 0:
            break
        # First non-reasoning line from the start
        if not is_reasoning:
            break

    # If most of the text looks like reasoning, look for the actual answer
    # which often starts with a bold statement or direct answer
    if first_answer_line > len(lines) // 2:
        # More than half is reasoning — look for answer patterns
        for i, line in enumerate(lines):
            stripped = line.strip()
            # Answers often start with **bold** or a direct statement
            if stripped.startswith('**') or stripped.startswith('Over ') or stripped.startswith('Your '):
                first_answer_line = i
                break

    if first_answer_line > 0 and first_answer_line < len(lines):
        text = '\n'.join(lines[first_answer_line:])

    return text.strip()


# ── AI Service ────────────────────────────────────────────────────────────

SYSTEM_PROMPT_REPORT = """You are a sleep medicine AI assistant analyzing CPAP data from a ResMed AirSense 11 device. Generate a patient-friendly but medically accurate report.

CRITICAL: Respond ONLY with the final JSON report. Do NOT show your reasoning, thinking process, or chain of thought. Do NOT narrate your analysis steps.

REPORT STRUCTURE (respond in JSON only):
{
  "summary": "2-3 paragraph narrative of the night in plain language",
  "findings": [
    "Specific clinical observations with severity assessment",
    "Pattern analysis (event clustering, timing, correlations)"
  ],
  "recommendations": [
    "Evidence-based suggestions for the patient",
    "When to consult a sleep specialist"
  ]
}

GUIDELINES:
- AHI classification: <5 normal, 5-15 mild, 15-30 moderate, >30 severe
- Explain patterns in plain language (e.g., "Your breathing events tended to cluster in the early morning hours, which may indicate REM-related apnea")
- Suggest concrete actions (mask fit check, humidity adjustment, discuss with doctor)
- Flag concerning findings (very high AHI, persistent high leaks, central apneas)
- Be empathetic but factual — CPAP therapy is challenging and progress matters
- Note: You are NOT diagnosing. Always recommend consulting a sleep specialist for medical decisions.
"""

SYSTEM_PROMPT_QA = """You are a CPAP data Q&A assistant. Answer questions about CPAP therapy based ONLY on the provided data context.

CRITICAL: Respond ONLY with your final answer. Do NOT show your reasoning, thinking process, chain of thought, or step-by-step analysis. Give the answer directly.

CAPABILITIES:
- Explain what specific events mean (obstructive vs central apnea, hypopnea)
- Compare tonight's data to trends
- Suggest mask fitting tips
- Explain pressure adjustments
- Interpret leak patterns
- Discuss AHI trends and what they mean

LIMITATIONS:
- Do NOT diagnose medical conditions
- Do NOT suggest medication changes
- Do NOT replace professional medical advice
- Always encourage consulting a sleep specialist for serious concerns

RESPONSE FORMAT:
- Direct answer first, in plain language
- Supporting evidence from the data
- When to seek professional help (if relevant)
"""


async def generate_report_with_ai(
    session_data: dict,
    openai_api_key: str,
    openai_base_url: str = "https://api.synthetic.new/openai/v1",
    model: str = "hf:moonshotai/Kimi-K2.6",
) -> dict:
    """Generate AI report using OpenAI-compatible API."""
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=openai_api_key, base_url=openai_base_url)

        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_REPORT},
                {"role": "user", "content": json.dumps(session_data, indent=2, default=str)},
            ],
            max_tokens=8000,
        )

        msg = response.choices[0].message
        content = msg.content or getattr(msg, 'reasoning', None) or ''

        # Strip any leaked chain-of-thought
        content = _strip_thinking(content)

        # Try JSON parse, fall back to plain text
        # Handle markdown-wrapped JSON (```json ... ```)
        content_stripped = content.strip()
        if content_stripped.startswith('```'):
            lines = content_stripped.split('\n')
            # Remove first and last lines (```json and ```)
            lines = [l for l in lines if not l.strip().startswith('```')]
            content_stripped = '\n'.join(lines)

        try:
            result = json.loads(content_stripped)
        except json.JSONDecodeError:
            # Try to find JSON object in the text
            import re
            json_match = re.search(r'\{[\s\S]*\}', content_stripped)
            if json_match:
                try:
                    result = json.loads(json_match.group())
                except json.JSONDecodeError:
                    result = {"summary": content, "findings": [], "recommendations": []}
            else:
                result = {"summary": content, "findings": [], "recommendations": []}
        result["tokens_used"] = response.usage.total_tokens
        result["model"] = model
        return result

    except Exception as e:
        logger.error(f"AI report generation failed: {e}")
        raise


async def answer_question_with_ai(
    question: str,
    context: str,
    openai_api_key: str,
    openai_base_url: str = "https://api.synthetic.new/openai/v1",
    model: str = "hf:moonshotai/Kimi-K2.6",
) -> dict:
    """Answer a question about CPAP data using OpenAI-compatible API."""
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=openai_api_key, base_url=openai_base_url)

        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_QA},
                {"role": "user", "content": f"CPAP Data Context:\n{context}\n\nQuestion: {question}"},
            ],
            max_tokens=4000,
        )

        raw = response.choices[0].message.content or ''

        # Strip leaked chain-of-thought: if response starts with reasoning patterns,
        # find where the actual answer begins
        answer = _strip_thinking(raw)

        # Fall back to reasoning field if content is empty after stripping
        if not answer.strip():
            answer = getattr(response.choices[0].message, 'reasoning', '') or 'No response'

        return {
            "answer": answer,
            "tokens_used": response.usage.total_tokens if response.usage else 0,
            "model": model,
        }

    except Exception as e:
        logger.error(f"AI Q&A failed: {e}")
        raise


# ── Routes ───────────────────────────────────────────────────────────────

@router.post("/report", response_model=ReportResponse)
async def generate_report(
    request: ReportRequest,
    req: Request,
    db: Session = Depends(get_db),
):
    """Generate an AI analysis report for a session or upload."""
    settings = req.app.state.settings

    if not settings.openai_api_key:
        raise HTTPException(
            status_code=503,
            detail="OpenAI API key not configured. Set OPENAI_API_KEY in .env",
        )

    # Build context data
    if request.session_id:
        session = db.query(NightSession).filter(NightSession.id == request.session_id).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        context = _build_session_context(db, session)
    elif request.upload_id:
        sessions = db.query(NightSession).filter(
            NightSession.upload_id == request.upload_id
        ).order_by(NightSession.session_date).all()  # ALL sessions — 256k context
        context = _build_trend_context(sessions)
    else:
        raise HTTPException(status_code=400, detail="Provide session_id or upload_id")

    # Check for cached report
    existing = db.query(AIReport).filter(
        AIReport.session_id == request.session_id,
        AIReport.report_type == request.report_type,
    ).first()
    if existing:
        return ReportResponse(
            id=existing.id,
            session_id=existing.session_id,
            report_type=existing.report_type,
            summary_text=existing.summary_text,
            key_findings=existing.key_findings or [],
            recommendations=existing.recommendations or [],
            model_version=existing.model_version,
        )

    # Generate report
    result = await generate_report_with_ai(
        context,
        settings.openai_api_key,
        openai_base_url=settings.openai_base_url,
        model=settings.openai_model,
    )

    # Store report
    report = AIReport(
        session_id=request.session_id,
        upload_id=request.upload_id,
        report_type=request.report_type,
        summary_text=result.get("summary", ""),
        key_findings=result.get("findings", []),
        recommendations=result.get("recommendations", []),
        tokens_used=result.get("tokens_used", 0),
        model_version=result.get("model", ""),
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    return ReportResponse(
        id=report.id,
        session_id=report.session_id,
        report_type=report.report_type,
        summary_text=report.summary_text,
        key_findings=report.key_findings or [],
        recommendations=report.recommendations or [],
        model_version=report.model_version,
    )


@router.post("/ask", response_model=QuestionResponse)
async def ask_question(
    request: QuestionRequest,
    req: Request,
    db: Session = Depends(get_db),
):
    """Ask a question about CPAP data."""
    settings = req.app.state.settings

    if not settings.openai_api_key:
        raise HTTPException(
            status_code=503,
            detail="OpenAI API key not configured",
        )

    # Build context from referenced sessions
    context_parts = []
    source_dates = []

    if request.context_session_ids:
        # Specific sessions — send full detail
        for sid in request.context_session_ids:
            session = db.query(NightSession).filter(NightSession.id == sid).first()
            if session:
                context_parts.append(json.dumps(_build_session_context(db, session), default=str))
                source_dates.append(str(session.session_date))
    else:
        # No specific sessions — send ALL sessions as a compact trend table (256k context)
        all_sessions = db.query(NightSession).order_by(
            NightSession.session_date
        ).all()
        trend_ctx = _build_trend_context(all_sessions)
        context_parts.append(json.dumps(trend_ctx, default=str))
        source_dates = [str(s.session_date) for s in all_sessions]

    context = "\n---\n".join(context_parts)

    result = await answer_question_with_ai(
        request.question,
        context,
        settings.openai_api_key,
        openai_base_url=settings.openai_base_url,
        model=settings.openai_model,
    )

    return QuestionResponse(
        answer=result["answer"],
        sources=source_dates,
    )


# ── Helpers ───────────────────────────────────────────────────────────────

def _build_session_context(db: Session, session: NightSession) -> dict:
    """Build a context dict from a single session for AI consumption."""
    events = db.query(Event).filter(Event.session_id == session.id).all()

    # Group events by type — include ALL events (256k context can handle it)
    events_by_type = {}
    event_details = []
    for e in events:
        events_by_type[e.event_type] = events_by_type.get(e.event_type, 0) + 1
        event_details.append({
            "type": e.event_type,
            "onset_minutes": round(e.onset_seconds / 60, 1),
            "duration_seconds": round(e.duration_seconds, 1),
        })

    # Also pull signal-level stats for richer context
    signal_records = db.query(SignalData).filter(SignalData.session_id == session.id).all()
    signal_stats = {}
    for sr in signal_records:
        # Use whichever resolution has data
        data = sr.data_1min or sr.data_json or []
        if data and len(data) > 0:
            import numpy as np
            arr = np.array(data)
            valid = arr[arr >= 0]  # filter out sentinel values
            if len(valid) > 0:
                signal_stats[sr.signal_name] = {
                    "unit": sr.unit,
                    "median": round(float(np.median(valid)), 2),
                    "mean": round(float(np.mean(valid)), 2),
                    "p95": round(float(np.percentile(valid, 95)), 2),
                    "max": round(float(np.max(valid)), 2),
                    "min": round(float(np.min(valid)), 2),
                    "std": round(float(np.std(valid)), 2),
                }

    return {
        "date": str(session.session_date),
        "duration_hours": round(session.duration_hours, 1),
        "ahi": session.ahi,
        "oai": session.oai,
        "cai": session.cai,
        "hi": session.hi,
        "leak": {
            "median_Lmin": round(session.leak_50, 1),
            "95th_percentile_Lmin": round(session.leak_95, 1),
            "max_Lmin": round(session.leak_max, 1),
        },
        "pressure": {
            "median_cmH2O": round(session.pressure_50, 1),
            "95th_percentile_cmH2O": round(session.pressure_95, 1),
            "max_cmH2O": round(session.pressure_max, 1),
            "epap_95_cmH2O": round(session.epap_95, 1),
        },
        "respiratory": {
            "rr_median": round(session.rr_50, 1),
            "mv_median_Lmin": round(session.mv_50, 1),
            "tv_median_mL": round(session.tv_50, 1),
        },
        "settings": {
            "min_pressure_cmH2O": session.min_pressure,
            "max_pressure_cmH2O": session.max_pressure,
            "set_pressure_cmH2O": session.set_pressure,
            "epr_level": session.epr_level,
        },
        "events_by_type": events_by_type,
        "event_details": event_details,  # ALL events — 256k can handle it
        "signal_statistics": signal_stats,
        "csr_percent": session.csr_percent,
    }


def _build_trend_context(sessions: list) -> dict:
    """Build trend context from multiple sessions — compact per-night table."""
    nights = []
    for s in sessions:
        nights.append({
            "date": str(s.session_date),
            "duration_hours": round(s.duration_hours, 1),
            "ahi": round(s.ahi, 1),
            "oai": round(s.oai, 1),
            "cai": round(s.cai, 1),
            "hi": round(s.hi, 1),
            "leak_95_Lmin": round(s.leak_95, 1),
            "pressure_95_cmH2O": round(s.pressure_95, 1),
            "event_counts": s.event_counts or {},
            "mask_on_min": round(s.mask_on_seconds / 60, 0) if s.mask_on_seconds > 0 else None,
            "mask_off_min": round(s.mask_off_seconds / 60, 0) if s.mask_off_seconds > 0 else None,
        })

    # Calculate aggregates
    ahi_vals = [s.ahi for s in sessions if s.ahi > 0]
    dur_vals = [s.duration_hours for s in sessions if s.duration_hours > 0]

    return {
        "report_type": "all_sessions_overview",
        "num_nights": len(sessions),
        "date_range": f"{sessions[0].session_date} to {sessions[-1].session_date}" if sessions else "",
        "summary": {
            "avg_ahi": round(sum(ahi_vals) / len(ahi_vals), 1) if ahi_vals else 0,
            "median_ahi": round(sorted(ahi_vals)[len(ahi_vals)//2], 1) if ahi_vals else 0,
            "avg_duration_hours": round(sum(dur_vals) / len(dur_vals), 1) if dur_vals else 0,
            "compliance_pct": round(sum(1 for d in dur_vals if d >= 4) / len(dur_vals) * 100, 0) if dur_vals else 0,
            "nights_ahi_under_5": sum(1 for a in ahi_vals if a < 5),
            "nights_ahi_5_to_15": sum(1 for a in ahi_vals if 5 <= a < 15),
            "nights_ahi_over_15": sum(1 for a in ahi_vals if a >= 15),
        },
        "settings": {
            "min_pressure_cmH2O": sessions[0].min_pressure if sessions else 0,
            "max_pressure_cmH2O": sessions[0].max_pressure if sessions else 0,
            "epr_level": sessions[0].epr_level if sessions else 0,
        },
        "nights": nights,
    }
