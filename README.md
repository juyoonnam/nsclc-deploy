# NSCLC Insight Engine — Deploy

비소세포폐암(NSCLC) 약물 재창출 및 임상 판단 보조 플랫폼의 운영 스택입니다.

Supervisor agent가 ML 챔피언 모델(E6, scaffold CV PR-AUC_w 0.1383 ± 0.0054)을 래핑하고,
22개 MCP 도구를 통해 모든 LLM 응답에 정량 근거(SHAP, in-library 매칭, Tanimoto
유사도, PR-AUC, provenance)를 부착합니다.

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

- **`supervisor/`** — FastAPI 서버. `NSCLCSupervisor`가 Strands SDK agent를 래핑합니다.
  - 엔드포인트: `/health`, `/tools`, `/invoke`, `/invoke_stream` (SSE)
  - Hybrid routing — 단순 질의는 Haiku, 복잡 질의는 Sonnet으로 분기
  - 22개 도구를 `ToolInvoker`로 라우팅 (AWS Lambda 또는 in-process)

- **`lambdas/`** — 7개 MCP 도구 함수. 6개는 AWS Lambda에 배포되어 있으며,
  `drug_library`만 supervisor 컨테이너 내부에서 in-process로 실행됩니다.
  - `drug_cell_response`, `drug_library`, `guardrail`, `knowledge_base`,
    `model_inference`, `patient`, `schema_discovery`

- **`ui/`** — Dash 챗봇 + 보조 패널 (Pathway Map, Simulator, Candidate Explorer,
  Drug Ranking, Model Card).

---

## 사전 조건 (one-time setup)

### AWS

- IAM role `NSCLCLambdaExecutionRole` — Lambda 실행 권한, S3/Bedrock 접근
- IAM role `NSCLCSupervisorEC2Role` + instance profile — EC2의 Lambda invoke,
  Bedrock 호출 권한
- S3 bucket `say2-5team-use1` (us-east-1) — Parquet 데이터 sync 완료
- Bedrock Knowledge Base `PHZTHHSMZC` (FDA labels + ESMO PAGA 등 5 PDFs)
- Bedrock Guardrail `19ys87squ5mz` v9 (Contextual grounding 포함)
- 6개 AWS Lambda 배포 (`nsclc-*`, tag `project=pre-5team`)

### EC2

- 인스턴스: t3.large 이상 권장 (4 vCPU / 8 GB RAM), Amazon Linux 2023
- Instance profile: `NSCLCSupervisorEC2Profile`
- Security group: 8050 (Dash UI) 외부 공개, 8000 (supervisor)은 localhost only
- Docker + docker compose 설치

---

## 실행

```bash
# 1. clone
git clone <repo-url> nsclc
cd nsclc

# 2. .env 작성 (EC2 instance profile 사용 시 AWS 키 항목은 생략 가능)
cp .env.example .env

# 3. build (최초 5~10분 — supervisor 이미지에 rdkit 포함)
docker compose build

# 4. 실행
docker compose up -d

# 5. 로그 확인
docker compose logs -f --tail 50

# 6. 헬스체크
curl http://localhost:8000/health
curl -I http://localhost:8050/

# 7. 종료
docker compose down
```

브라우저에서 `http://<EC2-public-ip>:8050` 접속.

---

## 환경변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `AWS_REGION` | `us-east-1` | AWS 기본 region |
| `BEDROCK_REGION` | `us-east-1` | Bedrock 및 Knowledge Base region |
| `BEDROCK_KB_ID` | `PHZTHHSMZC` | Knowledge Base ID |
| `GUARDRAIL_ID` | `19ys87squ5mz` | Bedrock Guardrail ID |
| `GUARDRAIL_VERSION` | `9` | Guardrail 버전 |
| `DATA_MODE` | `s3` | `local` 지정 시 `NSCLC_PROJECT_ROOT` 사용 |
| `S3_DATA_BUCKET` | `say2-5team-use1` | Parquet 데이터 버킷 |
| `SUPERVISOR_LOCAL_MODE` | `false` | `true` 지정 시 모든 lambda를 local invoke |
| `LOCAL_ONLY_LAMBDAS` | `drug_library_lambda` | hybrid routing에서 local 강제할 lambda |
| `SUPERVISOR_URL` | `http://supervisor:8000` | UI → supervisor (compose 네트워크 내부) |
| `NSCLC_SUPERVISOR_MOCK` | `0` | `1` 지정 시 Bedrock 호출 비활성화 (오프라인 테스트) |

상세 명세는 `.env.example` 참고.

---

## 운영

### 로그

```bash
docker compose logs supervisor --tail 100
docker compose logs ui --tail 100
```

### Supervisor만 재시작 (코드 변경 후)

```bash
docker compose build supervisor && docker compose up -d supervisor
```

### Invoke 직접 호출 (UI 우회)

```bash
curl -X POST http://localhost:8000/invoke \
  -H "Content-Type: application/json" \
  -d '{"query":"List the actionable NSCLC genes."}' \
  --max-time 120 | python3 -m json.tool
```

### 도구 목록 조회

```bash
curl http://localhost:8000/tools | python3 -m json.tool
```

### SSE 스트림 확인

```bash
curl -N -X POST http://localhost:8000/invoke_stream \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{"query":"List the actionable NSCLC genes."}'
```

---

## 알려진 한계

1. **`drug_library_lambda`는 AWS Lambda에 배포되지 않습니다.** rdkit 의존성으로
   인해 zip 패키지가 Lambda unzipped 250 MB 한도를 초과하므로, supervisor 컨테이너
   내부에서 in-process로 호출합니다. 향후 container image lambda로 전환 시 AWS
   배포 가능합니다.

2. **AgentCore Gateway는 미적용 상태입니다.** 발표 시점까지 적용하지 못해 향후
   과제로 남겨두었습니다. HTTP/SSE 추상화는 `supervisor_client.py`에 이미 완료되어
   있어, supervisor 호출 엔드포인트를 Gateway URL로 교체하면 이전 가능합니다.

3. **Supervisor는 worker=1로 고정되어 있습니다.** `_TOOL_INVOKER` 컨텍스트와
   dedup 캐시가 stateful이므로, 멀티 워커 확장 시 Redis 등 외부 캐시 도입이
   필요합니다.

4. **신규 화합물 일반화 한계.** STRICT scaffold Spearman 0.18 / RELAXED 0.36.
   computational chemistry의 알려진 난제이며, 두 지표를 병기하여 정직하게
   보고합니다.

---

## 향후 계획

- [ ] AgentCore Runtime + Gateway 이전
- [ ] `drug_library`를 container image lambda로 AWS 배포
- [ ] Supervisor / UI 분리 → 컨테이너별 별도 health & metrics
- [ ] CloudWatch 대시보드 (Lambda invocation, Bedrock token 사용량, latency)
- [ ] CI/CD 파이프라인 (GitHub Actions → ECR push → EC2 redeploy)

---

## License & Credits

SKKU AWS 바이오헬스케어 AI 아카데미 SAY 2기 5팀.

Champion model: E6 (XGBoost + LightGBM ensemble, 947 features, scaffold CV
PR-AUC_w 0.1383 ± 0.0054).
