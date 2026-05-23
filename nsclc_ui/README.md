# NSCLC Insight Engine — UI Shell

비소세포폐암(NSCLC) 약물 재창출 ML 시스템의 사용자 인터페이스.

Plotly Dash + Mantine 기반. 현재는 mock data로 동작하는 UI 셸이며,
백엔드 추론 로직은 별도 작업 예정.

## 빠른 시작

```bash
cd nsclc_ui
pip install -r requirements.txt
python app.py
```

브라우저: http://127.0.0.1:8050

## 구조

```
nsclc_ui/
├── app.py                    # Dash entrypoint, MantineProvider, Pages registry
├── requirements.txt
├── data/
│   └── mock.py              # 모든 mock data (KPI, RANKING, TRIAGE, MODEL_CARD 등)
├── layout/
│   ├── theme.py             # 색상 토큰 + Mantine theme 객체
│   ├── header.py            # 상단 네비
│   ├── sidebar.py           # 좌측 필터
│   └── footer.py
├── components/
│   ├── kpi_card.py          # 메트릭 카드
│   ├── label_badge.py       # Positive/Promoted/Unlabeled/Blocked
│   ├── evidence_chip.py     # NCT/PMID/DC 칩
│   ├── shap_bars.py         # 양수/음수 분기 막대
│   ├── tanimoto_bar.py      # 인라인 유사도 바
│   └── molecule_2d.py       # 2D 구조 placeholder
└── tabs/
    ├── drug_ranking.py      # 33,943개 후보 랭킹
    ├── candidate_explorer.py # 판정 루프 + 로그
    ├── predict.py           # 미지 화합물 트리아지 (핵심)
    ├── model_card.py        # 모델 카드 + 4축 결과
    └── about.py             # 한계 + 면책 + 데이터 소스
```

## 5개 탭

| 탭 | 경로 | 설명 |
|---|---|---|
| Drug Ranking | `/` | E0_tuned 모델의 Top-N 후보 + 상세 패널 |
| Candidate Explorer | `/explorer` | 후보별 판정(Confirm/Defer/Block) + CSV export |
| Predict | `/predict` | 미지 SMILES → 4-state 트리아지 (LIKELY_ACTIVE / REVIEW_REQUIRED / OUT_OF_DOMAIN / NO_EVIDENCE_FOR_UPGRADE) |
| Model Card | `/model-card` | 성능, 4축 탐색 결과, HPO diff, 평가 프로토콜 |
| About | `/about` | 한계 8개, 면책, 데이터 소스, 버전 이력 |

## 기술 스택

- **Frontend**: Plotly Dash + dash-mantine-components + dash-iconify
- **Charts**: Plotly + 커스텀 HTML/SVG
- **Mock data**: Python dict/list (백엔드 분리 예정)
- **배포 (예정)**: AWS Lambda(FastAPI+Mangum) + API Gateway + S3 + CloudFront + DynamoDB + CloudWatch

## 디자인 원칙

- Flat, 0.5px borders, 12~14px font
- Mantine 색상 토큰 일관 적용
- 데이터밀도 우선 (cBioPortal / Open Targets 참고)
- 모든 숫자는 tabular-nums

## 현재 상태 / 한계

- ✅ 5개 탭 전부 렌더링 가능
- ✅ Mock data 기반 인터랙션 (필터, 행 클릭, 판정 버튼, Run triage)
- ⚠️ 백엔드 추론 로직 미연결 — `data/mock.py`의 정적 데이터로만 동작
- ⚠️ AWS 배포 미수행 — 로컬 실행만 가능
- ⚠️ 인증 / 사용자 관리 없음

## 다음 작업

1. `predict.py` 백엔드 연결 (FastAPI `/predict_compound` 엔드포인트)
2. `final/scripts/build_inference_artifacts.py` 실행 → 추론 artifact 생성
3. AWS Lambda 컨테이너 이미지 빌드 + ECR 배포
4. `data/mock.py` → 실제 `final/results/` CSV 로딩으로 교체
5. CI/테스트 (pytest)

## 라이선스

학술 프로젝트 — SKKU AWS Biomedical AI Academy SAY 2기 5조

## 팀

남주윤 (Project Lead)

GitHub: https://github.com/juyoonnam/nsclc-insight-engine
