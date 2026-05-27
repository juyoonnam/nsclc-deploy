"""FastAPI server — NSCLCSupervisor HTTP wrapper.

엔드포인트:
  GET  /health              → {"status": "ok", "supervisor_initialized": bool}
  GET  /tools               → TOOL_REGISTRY 메타 (디버그)
  POST /invoke              → sync. body={query}, returns SupervisorResponse dict
  POST /invoke_stream       → SSE. body={query}, yields chunks as SSE events

실행:
  uvicorn server:app --host 0.0.0.0 --port 8000 --workers 1

환경변수:
  - DATA_MODE=s3                     (or local)
  - LOCAL_ONLY_LAMBDAS=drug_library_lambda
  - S3_DATA_BUCKET=say2-5team-use1
  - S3_DATA_PREFIX=nsclc-insight-engine
  - BEDROCK_KB_ID=PHZTHHSMZC
  - BEDROCK_REGION=us-east-1
  - AWS_REGION=us-east-1
  - GUARDRAIL_ID=19ys87squ5mz
  - GUARDRAIL_VERSION=9
  - SUPERVISOR_LOCAL_MODE=false      (true면 모든 Lambda local invoke. EC2면 false 권장)
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

# sys.path 보강 — supervisor.py가 같은 디렉토리, lambdas가 자매 디렉토리
HERE = Path(__file__).resolve().parent
LAMBDAS_DIR = HERE.parent / "lambdas"
for p in (str(HERE), str(LAMBDAS_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from supervisor import NSCLCSupervisor  # noqa: E402
from tool_schemas import TOOL_REGISTRY  # noqa: E402

# ===== 로깅 =====
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("nsclc-server")

# ===== Supervisor singleton (lazy) =====
_SUPERVISOR: NSCLCSupervisor | None = None


def get_supervisor() -> NSCLCSupervisor:
    global _SUPERVISOR
    if _SUPERVISOR is None:
        local_mode = os.environ.get("SUPERVISOR_LOCAL_MODE", "false").lower() == "true"
        guardrail_id = os.environ.get("GUARDRAIL_ID", "19ys87squ5mz")
        guardrail_version = os.environ.get("GUARDRAIL_VERSION", "9")
        region = os.environ.get("AWS_REGION", "us-east-1")
        log.info(
            f"Initializing NSCLCSupervisor: local_mode={local_mode}, "
            f"guardrail={guardrail_id}/v{guardrail_version}, region={region}"
        )
        _SUPERVISOR = NSCLCSupervisor(
            local_mode=local_mode,
            region=region,
            guardrail_id=guardrail_id,
            guardrail_version=guardrail_version,
        )
        log.info("Supervisor initialized.")
    return _SUPERVISOR


# ===== App =====
app = FastAPI(
    title="NSCLC Insight Engine — Supervisor API",
    version="1.0.0",
    description="HTTP wrapper around NSCLCSupervisor (Strands + 22 MCP tools).",
)

# CORS: Dash UI(같은 EC2 다른 컨테이너)에서 호출 가능하게
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===== Request/Response models =====
class InvokeRequest(BaseModel):
    query: str


# ===== Endpoints =====
@app.get("/health")
def health():
    return {
        "status": "ok",
        "supervisor_initialized": _SUPERVISOR is not None,
        "data_mode": os.environ.get("DATA_MODE", "local"),
        "local_only_lambdas": os.environ.get("LOCAL_ONLY_LAMBDAS", "drug_library_lambda"),
        "bedrock_region": os.environ.get("BEDROCK_REGION", "us-east-1"),
    }


@app.get("/tools")
def list_tools():
    """TOOL_REGISTRY 노출 — 22 tool의 이름/카테고리/lambda."""
    return {
        "count": len(TOOL_REGISTRY),
        "tools": [
            {
                "name": name,
                "category": getattr(schema, "category", ""),
                "lambda_name": getattr(schema, "lambda_name", ""),
                "description": getattr(schema, "description", "")[:200],
            }
            for name, schema in TOOL_REGISTRY.items()
        ],
    }


@app.post("/invoke")
def invoke(req: InvokeRequest):
    """Sync invoke. SupervisorResponse를 dict로 직렬화."""
    query = (req.query or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="empty query")
    request_start = time.time()
    req_id = f"{int(request_start * 1000)}-{id(req):x}"
    log.info("invoke request start req_id=%s query_len=%d", req_id, len(query))
    try:
        sup = get_supervisor()
        resp = sup.invoke(query)
        log.info(
            "invoke request complete req_id=%s elapsed_sec=%.3f backend=%s turns=%s tools=%d dedup_hits=%s",
            req_id,
            time.time() - request_start,
            resp.backend,
            resp.n_turns,
            len(resp.tools_called),
            resp.n_dedup_hits,
        )
        return asdict(resp)
    except Exception as e:
        log.exception("invoke failed req_id=%s elapsed_sec=%.3f", req_id, time.time() - request_start)
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@app.post("/invoke_stream")
async def invoke_stream(req: InvokeRequest):
    """SSE streaming. supervisor.invoke_stream()의 각 chunk를 SSE event로 emit.

    SSE event 형식:
      event: <chunk_type>   (routing, text_chunk, tool_start, tool_result, turn_end, done, error)
      data: <chunk_json>
    """
    query = (req.query or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="empty query")
    request_start = time.time()
    req_id = f"{int(request_start * 1000)}-{id(req):x}"
    log.info("invoke_stream request start req_id=%s query_len=%d", req_id, len(query))

    async def event_generator() -> AsyncIterator[dict]:
        chunk_count = 0
        last_ctype = ""
        saw_text = False
        loop = asyncio.get_running_loop()
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"sse-{req_id[:8]}")
        end_of_stream = object()

        def next_chunk(iterator):
            try:
                return next(iterator)
            except StopIteration:
                return end_of_stream

        try:
            sup = get_supervisor()
            # supervisor.invoke_stream is a sync generator backed by blocking boto3 calls.
            stream_iter = sup.invoke_stream(query)
            while True:
                chunk = await loop.run_in_executor(executor, next_chunk, stream_iter)
                if chunk is end_of_stream:
                    break
                ctype = chunk.get("type", "message")
                chunk_count += 1
                last_ctype = ctype
                if ctype != "text_chunk" or not saw_text:
                    log.info(
                        "invoke_stream chunk type=%s count=%d req_id=%s query_len=%d",
                        ctype,
                        chunk_count,
                        req_id,
                        len(query),
                    )
                if ctype == "text_chunk":
                    saw_text = True
                if ctype in ("done", "error"):
                    log.info(
                        "invoke_stream terminal_emit type=%s chunks=%d req_id=%s elapsed_sec=%.3f",
                        ctype,
                        chunk_count,
                        req_id,
                        time.time() - request_start,
                    )
                yield {
                    "event": ctype,
                    "data": json.dumps(chunk, ensure_ascii=False, default=str),
                }
                await asyncio.sleep(0)
                if ctype in ("done", "error"):
                    log.info(
                        "invoke_stream terminal_emitted type=%s chunks=%d req_id=%s elapsed_sec=%.3f",
                        ctype,
                        chunk_count,
                        req_id,
                        time.time() - request_start,
                    )
                    break
        except Exception as e:
            log.exception("invoke_stream failed req_id=%s elapsed_sec=%.3f", req_id, time.time() - request_start)
            last_ctype = "error"
            yield {
                "event": "error",
                "data": json.dumps(
                    {"type": "error", "message": f"{type(e).__name__}: {e}"},
                    ensure_ascii=False,
                ),
            }
        finally:
            log.info(
                "invoke_stream generator exit chunks=%d last=%s req_id=%s query_len=%d elapsed_sec=%.3f",
                chunk_count,
                last_ctype,
                req_id,
                len(query),
                time.time() - request_start,
            )
            executor.shutdown(wait=False)

    return EventSourceResponse(event_generator())


# ===== uvicorn 직접 실행 =====
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
        workers=1,  # supervisor stateful — multi-worker 금지
        log_level=os.environ.get("LOG_LEVEL", "info").lower(),
    )
