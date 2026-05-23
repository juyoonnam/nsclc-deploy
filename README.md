# NSCLC Insight Engine — Deploy

비소세포폐암(NSCLC) 약물 재창출 + 임상 판단 지원 플랫폼의 운영 stack.

ML champion 모델(E6, PR-AUC_w 0.1383±0.0054)을 supervisor agent가 wrap하여
22개 MCP-style tool을 통해 LLM 응답에 정량 근거를 강제 박는 구조.

---

## 아키텍처

```
[Browser]
     │
     ▼ http://EC2:8050
┌─────────────────┐   HTTP+SSE   ┌──────────────────┐
│  nsclc-ui       │ ───────────▶ │  nsclc-supervisor│
│  (Dash, 8050)   │              │  (FastAPI, 8000) │
└─────────────────┘              └────────┬─────────┘
                                          │
                            ┌─────────────┼──────────────┐
                            ▼             ▼              ▼
                    6× AWS Lambda   local rdkit    Bedrock
                    (us-east-1)     drug_library   - Sonnet/Haiku
                    + S3 data       (in-process)   - KB (FDA labels)
                                                   - Guardrail v9
```

### 컴포넌트

- **`supervisor/`** — FastAPI server. NSCLCSupervisor wraps Strands SDK agent.
  - `/health` `/tools` `/invoke` `/invoke_stream` (SSE)
  - hybrid routing: simple query → Haiku, complex → Sonnet
  - tool 22개 ToolInvoker로 라우팅 (AWS Lambda or local)

- **`lambdas/`** — 7 MCP tool 함수 (6개 AWS 배포, drug_library만 local)
  - drug_cell_response, drug_library, guardrail, knowledge_base,
    model_inference, patient, schema_discovery

- **`ui/`** — Dash 챗봇 + 보조 패널 (Pathway map, Simulator 등)

---

## 사전 조건 (one-time setup)

### AWS 측

- IAM role `NSCLCLambdaExecutionRole` (Lambda execution, S3/Bedrock 권한)
- IAM role `NSCLCSupervisorEC2Role` + instance profile (EC2가 Lambda invoke + Bedrock 호출)
- S3 bucket `say2-5team-use1` (region us-east-1) — parquet 데이터 sync 완료
- Bedrock Knowledge Base `PHZTHHSMZC` (FDA labels + ESMO 5 PDFs)
- Bedrock Guardrail `19ys87squ5mz` v9 (Contextual grounding)
- 6 AWS Lambda 배포 (`nsclc-*`, `--tags project=pre-5team`)

### EC2 측

- 인스턴스: t3.large+ 권장 (4 vCPU 8GB), AL2023
- Instance profile: `NSCLCSupervisorEC2Profile`
- Security group: 8050 (Dash UI) 외부 공개, 8000은 localhost only
- Docker + docker compose 설치

---

## 실행

```bash
# 1. clone
git clone <repo-url> nsclc
cd nsclc

# 2. .env 작성 (AWS_ACCESS_KEY는 EC2 instance profile 사용 시 생략)
cp .env.example .env

# 3. build (첫 회 5~10분 — supervisor 이미지에 rdkit 등 무거움)
docker compose build

# 4. 실행
docker compose up -d

# 5. 로그
docker compose logs -f --tail 50

# 6. 헬스체크
curl http://localhost:8000/health
curl -I http://localhost:8050/

# 7. 종료
docker compose down
```

브라우저: `http://<EC2-public-ip>:8050`

---

## 환경변수 (요약)

| 변수 | 기본값 | 설명 |
|---|---|---|
| `AWS_REGION` | us-east-1 | AWS region |
| `BEDROCK_REGION` | us-east-1 | Bedrock + KB |
| `BEDROCK_KB_ID` | PHZTHHSMZC | KB ID |
| `GUARDRAIL_ID` | 19ys87squ5mz | Guardrail ID |
| `GUARDRAIL_VERSION` | 9 | Guardrail version |
| `DATA_MODE` | s3 | local 시 NSCLC_PROJECT_ROOT 사용 |
| `S3_DATA_BUCKET` | say2-5team-use1 | parquet 데이터 bucket |
| `SUPERVISOR_LOCAL_MODE` | false | true 시 모든 lambda local invoke |
| `LOCAL_ONLY_LAMBDAS` | drug_library_lambda | hybrid routing 시 local 강제 |
| `SUPERVISOR_URL` | http://supervisor:8000 | UI → supervisor (compose 내부) |
| `NSCLC_SUPERVISOR_MOCK` | 0 | 1 시 Bedrock 호출 안 함 |

상세 명세: `.env.example`

---

## 운영 메모

### 로그
```bash
docker compose logs supervisor --tail 100
docker compose logs ui --tail 100
```

### supervisor만 재시작 (코드 변경 후)
```bash
docker compose build supervisor && docker compose up -d supervisor
```

### invoke 직접 테스트 (Dash 거치지 않고)
```bash
curl -X POST http://localhost:8000/invoke \
  -H "Content-Type: application/json" \
  -d '{"query":"List the actionable NSCLC genes."}' \
  --max-time 120 | python3 -m json.tool
```

### tool 목록
```bash
curl http://localhost:8000/tools | python3 -m json.tool
```

### SSE stream 확인
```bash
curl -N -X POST http://localhost:8000/invoke_stream \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{"query":"List the actionable NSCLC genes."}'
```

---

## 알려진 한계 (§1.4 약점 먼저)

1. **drug_library_lambda는 AWS Lambda 미배포** — rdkit 의존 zip이 Lambda
   unzipped 250MB 한도 초과. supervisor 컨테이너 내 local invoke로 처리.
   → AgentCore Runtime 이전 시 container image lambda 옵션 검토.

2. **AgentCore Gateway 미사용** — IAM 권한 차단으로 D-day까지 미적용.
   `supervisor_client.py`가 HTTP/SSE 추상화 완료 — admin 권한 확보 시
   supervisor 호출 endpoint만 Gateway URL로 교체하면 됨.

3. **supervisor worker=1 고정** — `_TOOL_INVOKER` 전역 + dedup cache가
   stateful. 멀티 worker로 가려면 redis 등 외부 cache 도입 필요.

4. **STRICT Spearman 0.18** — 신규 화합물 일반화는 computational
   chemistry의 알려진 난제. RELAXED metric 병기 (Spearman 0.36).

---

## 다음 단계

- [ ] AgentCore Runtime + Gateway 이전 (admin policy 확보 후)
- [ ] container image lambda로 drug_library AWS 배포
- [ ] supervisor + UI 분리 → 각 컨테이너 별도 health/metrics
- [ ] CloudWatch dashboard (Lambda invocation, Bedrock token, latency)
- [ ] CI/CD (GitHub Actions: build → ECR push → EC2 redeploy)

---

## License & Credits

SKKU AWS 바이오헬스케어 AI 아카데미 SAY 2기 5팀.
Model: champion E6 (XGB+LGB ensemble, 947 features, scaffold CV PR-AUC_w 0.1383±0.0054)
