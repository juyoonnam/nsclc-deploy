"""Supervisor Client v3 — HTTP client to FastAPI server (Phase AQ).

v3 변경:
- 기존 v2의 in-process import 제거
- HTTP/SSE 호출로 전환 (server.py 의 /invoke, /invoke_stream)
- 기존 API 시그니처 100% 보존 (Dash callback 0 수정)

환경변수:
  - SUPERVISOR_URL=http://nsclc-supervisor:8000  (docker compose 내부 통신)
                  =http://localhost:8000          (단일 host dev)
  - NSCLC_SUPERVISOR_MOCK=1  (기존 mock 모드)

threading 패턴은 v2 그대로 유지 — Dash callback 인터페이스 동일.
실제 invoke만 HTTP로 전환.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import re
import threading
import time
import uuid

import requests

log = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════
# 설정
# ════════════════════════════════════════════════════════════
SUPERVISOR_URL = os.environ.get("SUPERVISOR_URL", "http://localhost:8000").rstrip("/")
HTTP_TIMEOUT_SYNC = float(os.environ.get("SUPERVISOR_HTTP_TIMEOUT", "300"))  # sync invoke
HTTP_TIMEOUT_STREAM = float(os.environ.get("SUPERVISOR_STREAM_TIMEOUT", "600"))  # SSE
STREAM_STALL_TIMEOUT = max(
    30.0,
    float(os.environ.get("SUPERVISOR_STREAM_STALL_TIMEOUT", "60")),
)

_CACHE: dict = {}
_DEFAULT_GUARDRAIL_VERSION = os.environ.get("NSCLC_GUARDRAIL_VERSION", "9")

_ACTIVE_JOBS: dict[str, dict] = {}
_JOBS_LOCK = threading.Lock()


def _stream_error_result(message: str) -> dict:
    return {
        "text": f"❌ Supervisor 실패: `{message}`",
        "tools": [], "findings": [], "stats": None,
        "latency_sec": 0.0, "violations": [],
        "backend": "error", "error": message,
    }


def _mark_job_error(job_id: str, message: str, *, enqueue: bool = True) -> bool:
    """Mark a running stream job as failed and optionally enqueue an error chunk."""
    q: queue.Queue | None = None
    with _JOBS_LOCK:
        job = _ACTIVE_JOBS.get(job_id)
        if not job or job.get("status") in ("done", "error"):
            return False
        job["status"] = "error"
        job["result"] = _stream_error_result(message)
        job["last_event_time"] = time.time()
        q = job.get("queue")
    if enqueue and q is not None:
        q.put({"type": "error", "message": message})
    return True


# ════════════════════════════════════════════════════════════
# Sync API (백워드 호환)
# ════════════════════════════════════════════════════════════

def invoke(query: str, use_cache: bool = True) -> dict:
    query = (query or "").strip()
    if not query:
        return _empty_result("질문이 비어있습니다.")

    if use_cache and query in _CACHE:
        return _CACHE[query]

    if os.environ.get("NSCLC_SUPERVISOR_MOCK", "0") == "1":
        return _mock_response(query)

    try:
        r = requests.post(
            f"{SUPERVISOR_URL}/invoke",
            json={"query": query},
            timeout=HTTP_TIMEOUT_SYNC,
        )
        r.raise_for_status()
        resp_dict = r.json()
        result = _build_result_from_dict(resp_dict)
        if use_cache:
            _CACHE[query] = result
        return result
    except requests.exceptions.RequestException as e:
        return {
            "text": (
                f"⚠️ Supervisor HTTP 호출 실패: `{type(e).__name__}: {e}`\n\n"
                f"SUPERVISOR_URL={SUPERVISOR_URL} 확인. "
                f"`curl {SUPERVISOR_URL}/health` 로 점검 가능."
            ),
            "tools": [], "findings": [], "stats": None,
            "latency_sec": 0.0, "violations": [],
            "backend": "error", "error": str(e),
        }
    except Exception as e:
        return {
            "text": f"⚠️ Supervisor 호출 실패: `{type(e).__name__}: {e}`",
            "tools": [], "findings": [], "stats": None,
            "latency_sec": 0.0, "violations": [],
            "backend": "error", "error": str(e),
        }


# ════════════════════════════════════════════════════════════
# Streaming API (SSE → threading.Queue로 변환, Dash callback 호환)
# ════════════════════════════════════════════════════════════

def start_streaming_invoke(query: str) -> dict:
    """비동기 supervisor SSE 호출 시작.

    Returns:
      {"job_id": str, "mock": bool, "cached": bool}
    """
    query = (query or "").strip()
    if not query:
        return {"job_id": "", "error": "empty query"}

    if os.environ.get("NSCLC_SUPERVISOR_MOCK", "0") == "1":
        result = _mock_response(query)
        job_id = str(uuid.uuid4())
        with _JOBS_LOCK:
            _ACTIVE_JOBS[job_id] = {
                "status": "done",
                "result": result,
                "queue": _seed_queue_from_mock(result),
                "start_time": time.time(),
            }
        log.info("stream job seeded mock job_id=%s query_len=%d", job_id, len(query))
        return {"job_id": job_id, "mock": True, "cached": False}

    if query in _CACHE:
        result = _CACHE[query]
        job_id = str(uuid.uuid4())
        with _JOBS_LOCK:
            _ACTIVE_JOBS[job_id] = {
                "status": "done",
                "result": result,
                "queue": _seed_queue_from_cache(result),
                "start_time": time.time(),
            }
        log.info("stream job seeded cache job_id=%s query_len=%d", job_id, len(query))
        return {"job_id": job_id, "mock": False, "cached": True}

    job_id = str(uuid.uuid4())
    q: queue.Queue = queue.Queue()
    with _JOBS_LOCK:
        _ACTIVE_JOBS[job_id] = {
            "status": "running",
            "result": None,
            "queue": q,
            "start_time": time.time(),
            "last_event_time": time.time(),
            "query": query,
        }
    log.info(
        "stream job created job_id=%s supervisor_url=%s timeout=%.1f query_len=%d",
        job_id,
        SUPERVISOR_URL,
        HTTP_TIMEOUT_STREAM,
        len(query),
    )

    def worker():
        chunk_count = 0
        saw_text = False
        try:
            log.info("stream worker start job_id=%s", job_id)
            with requests.post(
                f"{SUPERVISOR_URL}/invoke_stream",
                json={"query": query},
                stream=True,
                timeout=HTTP_TIMEOUT_STREAM,
                headers={"Accept": "text/event-stream"},
            ) as r:
                log.info("stream worker connected job_id=%s status=%s", job_id, r.status_code)
                r.raise_for_status()
                for chunk in _parse_sse_stream(r):
                    chunk_count += 1
                    ctype = chunk.get("type", "?")
                    with _JOBS_LOCK:
                        if job_id in _ACTIVE_JOBS:
                            _ACTIVE_JOBS[job_id]["last_event_time"] = time.time()
                    if ctype != "text_chunk" or not saw_text:
                        log.info("stream worker chunk job_id=%s type=%s", job_id, ctype)
                    if ctype == "text_chunk":
                        saw_text = True
                    q.put(chunk)
                    if chunk.get("type") == "done":
                        response_dict = chunk.get("response", {})
                        # supervisor.invoke_stream의 'done' chunk 안에 response가 dict로 들어옴
                        # (server.py 그대로 forwarding)
                        result = _build_result_from_dict(response_dict)
                        with _JOBS_LOCK:
                            if job_id in _ACTIVE_JOBS:
                                _ACTIVE_JOBS[job_id]["status"] = "done"
                                _ACTIVE_JOBS[job_id]["result"] = result
                        _CACHE[query] = result
                        log.info("stream worker done job_id=%s chunks=%d", job_id, chunk_count)
                        break
                    elif chunk.get("type") == "error":
                        _mark_job_error(
                            job_id,
                            chunk.get("message", "Unknown error"),
                            enqueue=False,
                        )
                        log.info(
                            "stream worker error chunk job_id=%s message=%s",
                            job_id,
                            chunk.get("message", ""),
                        )
                        break
        except Exception as e:
            err_msg = f"{type(e).__name__}: {e}"
            log.exception("stream worker exception job_id=%s", job_id)
            _mark_job_error(job_id, err_msg, enqueue=True)
        finally:
            with _JOBS_LOCK:
                status = _ACTIVE_JOBS.get(job_id, {}).get("status", "missing")
            if status == "running":
                _mark_job_error(
                    job_id,
                    "stream ended without done/error",
                    enqueue=True,
                )
                status = "error"
            log.info(
                "stream worker exit job_id=%s status=%s chunks=%d",
                job_id,
                status,
                chunk_count,
            )

    t = threading.Thread(target=worker, daemon=True, name=f"supervisor-http-{job_id[:8]}")
    t.start()
    return {"job_id": job_id, "mock": False, "cached": False}


def _parse_sse_stream(response):
    """SSE 응답을 chunk dict로 파싱.

    sse-starlette가 보내는 형식:
        event: <type>
        data: <json>
        <blank>
    """
    event_type = None
    data_buf = []

    def emit_buffered_chunk():
        if not data_buf:
            return None
        data_str = "\n".join(data_buf)
        try:
            chunk = json.loads(data_str)
        except json.JSONDecodeError:
            chunk = {"type": event_type or "raw", "raw": data_str}
        if "type" not in chunk and event_type:
            chunk["type"] = event_type
        return chunk

    for raw in response.iter_lines(chunk_size=1, decode_unicode=True):
        if raw is None:
            continue
        line = raw.rstrip("\r")
        if line == "":
            # event 끝 — chunk emit
            chunk = emit_buffered_chunk()
            if chunk is not None:
                yield chunk
            event_type = None
            data_buf = []
            continue
        if line.startswith(":"):
            # SSE 주석/ping
            continue
        if line.startswith("event:"):
            event_type = line[len("event:"):].strip()
        elif line.startswith("data:"):
            data_buf.append(line[len("data:"):].lstrip())
        # 기타 필드 (id:, retry:)는 무시

    chunk = emit_buffered_chunk()
    if chunk is not None:
        yield chunk


def poll_streaming_chunks(job_id: str) -> list[dict]:
    if not job_id:
        return []
    with _JOBS_LOCK:
        job = _ACTIVE_JOBS.get(job_id)
    if not job:
        return []

    if is_job_stale(job_id):
        _mark_job_error(
            job_id,
            f"stream stalled for >{STREAM_STALL_TIMEOUT:.0f}s",
            enqueue=True,
        )
        with _JOBS_LOCK:
            job = _ACTIVE_JOBS.get(job_id)
        if not job:
            return []

    q: queue.Queue = job["queue"]
    chunks = []
    while not q.empty():
        try:
            chunks.append(q.get_nowait())
        except queue.Empty:
            break
    if chunks:
        return chunks

    status = job.get("status")
    if status == "done":
        result = job.get("result") or {}
        return [{
            "type": "done",
            "response": {
                "text": result.get("text", ""),
                "call_log": [
                    {
                        "tool": t.get("tool"),
                        "success": t.get("status") == "완료",
                        "elapsed_sec": t.get("elapsed_sec"),
                        "input": t.get("input"),
                        "output": t.get("output"),
                        "error": t.get("error"),
                        "policy_rejected": t.get("policy_rejected"),
                    }
                    for t in result.get("tools", [])
                ],
                "policy_violations": result.get("violations", []),
                "backend": result.get("backend", "bedrock_converse_stream"),
                "latency_sec": result.get("latency_sec", 0),
                "model_used": result.get("model_used", ""),
                "complexity": result.get("complexity", ""),
            },
        }]
    if status == "error":
        result = job.get("result") or {}
        return [{
            "type": "error",
            "message": result.get("error") or "stream ended with error",
        }]
    return chunks


def is_job_done(job_id: str) -> bool:
    if not job_id:
        return True
    with _JOBS_LOCK:
        job = _ACTIVE_JOBS.get(job_id)
    if not job:
        return True
    return job["status"] in ("done", "error")


def is_job_stale(job_id: str) -> bool:
    if not job_id:
        return False
    with _JOBS_LOCK:
        job = _ACTIVE_JOBS.get(job_id)
        if not job:
            return True
        if job.get("status") != "running":
            return False
        last_event_time = float(job.get("last_event_time") or job.get("start_time") or 0)
    return (time.time() - last_event_time) > STREAM_STALL_TIMEOUT


def get_job_result(job_id: str) -> dict | None:
    if not job_id:
        return None
    with _JOBS_LOCK:
        job = _ACTIVE_JOBS.get(job_id)
    if not job:
        return None
    return job.get("result")


def cleanup_job(job_id: str) -> bool:
    if not job_id:
        return False
    with _JOBS_LOCK:
        if job_id in _ACTIVE_JOBS:
            del _ACTIVE_JOBS[job_id]
            return True
    return False


def active_jobs_count() -> int:
    with _JOBS_LOCK:
        return len(_ACTIVE_JOBS)


# ════════════════════════════════════════════════════════════
# chunk → store updates (v2와 동일)
# ════════════════════════════════════════════════════════════

def chunks_to_store_updates(
    chunks: list[dict],
    current_text: str,
    current_tools: list[dict],
) -> dict:
    text = current_text
    tools = list(current_tools)
    done = False
    error = None
    final_result = None

    for ch in chunks:
        ctype = ch.get("type")
        if ctype == "text_chunk":
            text += ch.get("text", "")
        elif ctype == "replace_text":
            text = ch.get("text", "")
        elif ctype == "tool_start":
            entry = {
                "step": len(tools) + 1,
                "tool": ch.get("tool", "?"),
                "status": "진행 중",
                "detail": "…",
                "input": ch.get("input") or ch.get("params") or ch.get("args"),
                "started_at": time.time(),
            }
            tools.append(entry)
        elif ctype == "tool_result":
            tool_name = ch.get("tool", "?")
            success = ch.get("success", False)
            elapsed = ch.get("elapsed", 0)
            output = ch.get("output") or ch.get("result") or ch.get("response")
            error_msg = ch.get("error") or ch.get("message")
            updated = False
            for t in reversed(tools):
                if t["tool"] == tool_name and t["status"] == "진행 중":
                    t["status"] = "완료" if success else "에러"
                    t["detail"] = f"{elapsed:.2f}s" if success else "lambda exception"
                    t["elapsed_sec"] = elapsed
                    if output is not None:
                        t["output"] = output
                    if error_msg:
                        t["error"] = error_msg
                    updated = True
                    break
            if not updated:
                tools.append({
                    "step": len(tools) + 1,
                    "tool": tool_name,
                    "status": "완료" if success else "에러",
                    "detail": f"{elapsed:.2f}s",
                    "elapsed_sec": elapsed,
                    "output": output,
                    "error": error_msg,
                })
        elif ctype == "turn_end":
            pass
        elif ctype == "done":
            done = True
            final_result = ch.get("response")
            call_log = (final_result or {}).get("call_log", []) if isinstance(final_result, dict) else []
            if call_log:
                tools = _build_tools(call_log)
        elif ctype == "error":
            error = ch.get("message", "Unknown error")
            done = True

    return {
        "text": text,
        "tools": tools,
        "done": done,
        "error": error,
        "final_result": final_result,
    }


def build_findings_from_text(text: str) -> list[dict]:
    findings = []
    if re.search(r"POLICY_REJECT_EXTERNAL|외부 화합물.*거부|policy_reject", text, re.IGNORECASE):
        findings.append({"title": "Phase A 정책 발동",
                         "detail": "외부 화합물 → champion 모델 거부"})
    m = re.search(r"in_library\s*=?\s*(True|False)", text)
    if m:
        val = m.group(1)
        findings.append({"title": "라이브러리 매칭",
                         "detail": f"in_library = {val}" + (" (외부 화합물)" if val == "False" else "")})
    m = re.search(r"Tanimoto\s*[=:]?\s*(0\.\d+)", text)
    if m:
        t_val = float(m.group(1))
        findings.append({"title": "구조 유사도",
                         "detail": f"Tanimoto = {m.group(1)}"
                                   + (" → 거부 (<0.3)" if t_val < 0.3 else " → analog evidence")})
    shap_match = re.search(
        r"(pic50_\w+|morgan_\d+|crispr_ess_\w+|tcga_expr_\w+|phys_\w+)"
        r"[\s\(]+(0\.\d+)", text)
    if shap_match:
        findings.append({"title": "SHAP top feature",
                         "detail": f"{shap_match.group(1)} = {shap_match.group(2)}"})
    m = re.search(r"[Ee]nsemble\s*(?:[Pp]rob(?:ability)?|Score)\s*[:=]?\s*(0\.\d+)", text)
    if m:
        findings.append({"title": "Ensemble probability",
                         "detail": f"{m.group(1)} (E6 30-model)"})
    m = re.search(r"(ACH-\d{6})", text)
    if m:
        findings.append({"title": "Cell line meta", "detail": f"DepMap ID {m.group(1)}"})
    pmids = re.findall(r"PMID\s*[:#]?\s*(\d{7,9})", text)
    if pmids:
        unique = list(dict.fromkeys(pmids))[:3]
        findings.append({"title": "문헌 근거", "detail": f"PMID: {', '.join(unique)}"})

    for i, f in enumerate(findings, 1):
        f["rank"] = i
    return findings[:5]


def build_stats_from_tools(tools: list[dict], has_violations: bool = False) -> dict:
    n_unique = len(set(t["tool"] for t in tools if t.get("status") == "완료"))
    if has_violations:
        confidence = "주의"
    elif n_unique >= 5:
        confidence = "높음"
    elif n_unique >= 2:
        confidence = "중간"
    else:
        confidence = "낮음"
    return {
        "pr_auc": "0.1383",
        "n_sources": f"{n_unique}/22",
        "confidence": confidence,
    }


# ════════════════════════════════════════════════════════════
# result dict builders
# ════════════════════════════════════════════════════════════

def _empty_result(msg: str) -> dict:
    return {
        "text": msg, "tools": [], "findings": [], "stats": None,
        "latency_sec": 0.0, "violations": [], "backend": "noop", "error": None,
    }


def _build_result_from_dict(response_dict: dict) -> dict:
    """server.py가 반환한 SupervisorResponse dict → Dash dict."""
    tools = _build_tools(response_dict.get("call_log", []))
    text = response_dict.get("text", "")
    findings = build_findings_from_text(text)
    has_viol = bool(response_dict.get("policy_violations"))
    return {
        "text": text,
        "tools": tools,
        "findings": findings,
        "stats": build_stats_from_tools(tools, has_violations=has_viol),
        "latency_sec": response_dict.get("latency_sec", 0),
        "violations": response_dict.get("policy_violations", []),
        "backend": response_dict.get("backend", "?"),
        "model_used": response_dict.get("model_used", ""),
        "complexity": response_dict.get("complexity", ""),
        "error": None,
    }


def _build_tools(call_log: list) -> list:
    tools = []
    for i, entry in enumerate(call_log, 1):
        if entry.get("dedup_hit"):
            continue
        tool_name = entry.get("tool", "?")
        success = entry.get("success", False)
        elapsed = entry.get("elapsed_sec", 0.0)
        policy_rejected = entry.get("policy_rejected")
        if policy_rejected:
            status, detail = "거부", "Phase A 정책"
        elif success:
            status, detail = "완료", f"{elapsed:.2f}s"
        else:
            status, detail = "에러", "lambda exception"
        tools.append({
            "step": i,
            "tool": tool_name,
            "status": status,
            "detail": detail,
            "elapsed_sec": elapsed,
            "input": entry.get("input") or entry.get("params") or entry.get("args"),
            "output": entry.get("output") or entry.get("result"),
            "error": entry.get("error") or entry.get("message"),
            "policy_rejected": bool(policy_rejected) if policy_rejected else False,
        })
    return tools


# ════════════════════════════════════════════════════════════
# Seed queue (cache/mock)
# ════════════════════════════════════════════════════════════

def _seed_queue_from_cache(result: dict) -> queue.Queue:
    q = queue.Queue()
    q.put({"type": "text_chunk", "text": result.get("text", "")})
    q.put({"type": "done", "response": {
        "text": result.get("text", ""),
        "call_log": [],
        "policy_violations": result.get("violations", []),
        "backend": result.get("backend", "cached"),
        "n_turns": 0,
        "latency_sec": 0,
    }})
    return q


def _seed_queue_from_mock(result: dict) -> queue.Queue:
    q = queue.Queue()
    q.put({"type": "text_chunk", "text": result.get("text", "")})
    q.put({"type": "done", "response": {
        "text": result.get("text", ""),
        "call_log": [],
        "policy_violations": result.get("violations", []),
        "backend": "mock",
        "n_turns": 0,
        "latency_sec": result.get("latency_sec", 0),
    }})
    return q


# ════════════════════════════════════════════════════════════
# Mock (env NSCLC_SUPERVISOR_MOCK=1)
# ════════════════════════════════════════════════════════════

def _mock_response(query: str) -> dict:
    q = query.lower()
    if "imatinib" in q and "shap" in q:
        return _mock_imatinib(query)
    if "olaparib" in q:
        return _mock_olaparib(query)
    if "h1975" in q:
        return _mock_h1975(query)
    if "egfr" in q and ("l858r" in q or "t790m" in q):
        return _mock_egfr(query)
    return {
        "text": f"[MOCK] '{query}' 응답.",
        "tools": [{"step": 1, "tool": "check_in_library", "status": "완료", "detail": "0.05s"}],
        "findings": [{"rank": 1, "title": "Mock", "detail": "실 호출 비활성"}],
        "stats": {"pr_auc": "0.1383", "n_sources": "1/22", "confidence": "낮음"},
        "latency_sec": 0.1, "violations": [], "backend": "mock", "error": None,
    }


def _mock_imatinib(q):
    return {
        "text": ("[MOCK] Imatinib SHAP:\n- pic50_std (0.387)\n- pic50_mean (0.131)\n"
                 "OOF mean 0.1107, Category C."),
        "tools": [
            {"step": 1, "tool": "check_in_library", "status": "완료", "detail": "0.04s"},
            {"step": 2, "tool": "get_shap_explanation", "status": "완료", "detail": "0.08s"},
        ],
        "findings": [
            {"rank": 1, "title": "라이브러리 매칭", "detail": "in_library = True (Category C)"},
            {"rank": 2, "title": "SHAP top", "detail": "pic50_std = 0.387"},
        ],
        "stats": {"pr_auc": "0.1383", "n_sources": "2/22", "confidence": "중간"},
        "latency_sec": 0.5, "violations": [], "backend": "mock", "error": None,
    }


def _mock_olaparib(q):
    return {
        "text": ("[MOCK] Olaparib Phase A:\n- in_library = False\n- Tanimoto 0.494 vs Niraparib\n"
                 "- POLICY_REJECT_EXTERNAL"),
        "tools": [
            {"step": 1, "tool": "check_in_library", "status": "완료", "detail": "0.04s"},
            {"step": 2, "tool": "compute_tanimoto", "status": "완료", "detail": "0.18s"},
            {"step": 3, "tool": "get_ensemble_probability", "status": "거부", "detail": "Phase A"},
        ],
        "findings": [
            {"rank": 1, "title": "Phase A 정책 발동", "detail": "외부 화합물 → champion 거부"},
            {"rank": 2, "title": "구조 유사도", "detail": "Tanimoto = 0.494"},
        ],
        "stats": {"pr_auc": "0.1383", "n_sources": "3/22", "confidence": "중간"},
        "latency_sec": 1.5, "violations": [], "backend": "mock", "error": None,
    }


def _mock_h1975(q):
    return {
        "text": ("[MOCK] H1975 (NCIH1975, ACH-000587): Lung Adenocarcinoma\n"
                 "Mutations: EGFR, TP53, PIK3CA, CDKN2A"),
        "tools": [
            {"step": 1, "tool": "get_cell_line_meta", "status": "완료", "detail": "0.07s"},
            {"step": 2, "tool": "get_drug_response", "status": "완료", "detail": "0.31s"},
        ],
        "findings": [
            {"rank": 1, "title": "Cell line meta", "detail": "ACH-000587"},
            {"rank": 2, "title": "Mutations", "detail": "EGFR, TP53, PIK3CA, CDKN2A"},
        ],
        "stats": {"pr_auc": "0.1383", "n_sources": "2/22", "confidence": "중간"},
        "latency_sec": 0.4, "violations": [], "backend": "mock", "error": None,
    }


def _mock_egfr(q):
    return {
        "text": ("[MOCK] EGFR L858R+T790M:\n- Osimertinib 0.624, Afatinib 0.857\n"
                 "- PMID 37937763 (FLAURA2)"),
        "tools": [
            {"step": 1, "tool": "list_actionable_genes", "status": "완료", "detail": "0.03s"},
            {"step": 2, "tool": "match_patient_drugs", "status": "완료", "detail": "0.42s"},
            {"step": 3, "tool": "search_drugs", "status": "완료", "detail": "0.06s"},
            {"step": 4, "tool": "get_ensemble_probability", "status": "완료", "detail": "0.05s"},
            {"step": 5, "tool": "search_pubmed", "status": "완료", "detail": "1.45s"},
        ],
        "findings": [
            {"rank": 1, "title": "라이브러리 매칭", "detail": "Osimertinib/Afatinib in_library"},
            {"rank": 2, "title": "Ensemble", "detail": "0.857 (Afatinib top)"},
        ],
        "stats": {"pr_auc": "0.1383", "n_sources": "5/22", "confidence": "높음"},
        "latency_sec": 2.1, "violations": [], "backend": "mock", "error": None,
    }


def clear_cache() -> int:
    global _CACHE
    n = len(_CACHE)
    _CACHE = {}
    return n


def cache_size() -> int:
    return len(_CACHE)
