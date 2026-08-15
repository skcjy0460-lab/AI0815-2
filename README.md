# 🧠 MEDIUM AI 경영 브리핑

원무통계 · 심사평가 · 인력관리 · 재무제표 4대 시스템의 HTML 보고서를 업로드하면,
Gemini AI가 데이터를 **교차 분석**하여 병원장이 바로 볼 수 있는 프리미엄
"AI 경영 브리핑" 리포트를 자동 생성하는 유료 전용 Streamlit 애플리케이션입니다.

---

## ✨ 핵심 가치

기존 4개 시스템이 각각 "자기 데이터"만 보여주는 것과 달리, 이 프로그램은
**여러 데이터를 함께 봐야만 보이는 인사이트**를 AI가 찾아냅니다.

- 원무통계의 환자 감소가 재무제표의 매출 변화와 같은 방향인가?
- 인력관리의 인건비율 상승이 재무제표의 인건비 비율 초과와 맞물리는가?
- 심사평가의 삭감이 특정 진료과에 집중되고, 그 진료과의 원무통계 비중은 어떤가?

이런 교차 분석 결과를 포함한 결과물은 **오프라인에서도 완벽하게 열리는 단일
HTML 파일**로 저장되어, 인쇄(PDF 저장)해서 원장님께 바로 보고할 수 있습니다.

---

## 📂 프로젝트 구조

```
ai_briefing_app/
├── app.py                      # 진입점 (st.navigation)
├── requirements.txt
├── .streamlit/
│   └── config.toml             # 테마 설정
├── core/
│   ├── parsers.py              # 4대 시스템 HTML → 구조화 데이터 파싱
│   ├── ai_engine.py            # Gemini API 연동 (모델 자동 폴백 체인)
│   ├── report_builder.py       # 프리미엄 HTML 브리핑 리포트 생성
│   ├── storage.py              # 브리핑 보관함 (파일 기반)
│   └── auth.py                 # 유료 라이선스 키 게이트
├── views/
│   ├── briefing_generator.py   # 새 브리핑 생성 페이지
│   ├── archive.py              # 보관함 페이지
│   ├── settings.py             # API/환경 설정 페이지
│   └── guide.py                # 사용 가이드 페이지
└── data/briefings/             # 생성된 브리핑 저장 위치 (자동 생성)
```

---

## 🚀 실행 방법

```bash
pip install -r requirements.txt
streamlit run app.py
```

### Gemini API 키 설정
좌측 메뉴 **API · 환경 설정**에서 직접 입력하거나, 배포 시에는
`.streamlit/secrets.toml`에 아래처럼 등록하세요.

```toml
GEMINI_API_KEY = "AIza..."

# 유료 서비스 게이트 (등록하지 않으면 게이트가 비활성화되어 누구나 접근 가능)
LICENSE_KEYS = ["MEDIUM-XXXX-XXXX", "MEDIUM-YYYY-YYYY"]
```

### 모델 자동 폴백
기본 체인은 `gemini-3.6-flash → gemini-3.5-flash-lite` 이며, 1순위 모델의
사용량이 초과되면(429/RESOURCE_EXHAUSTED) 자동으로 다음 모델로 전환됩니다.
**API · 환경 설정** 페이지에서 순서를 자유롭게 편집할 수 있습니다
(`gemini-2.5-flash`, `gemini-2.0-flash` 등 추가 폴백도 기본 제공).

---

## 🔍 4대 시스템 보고서 인식 방식

| 유형 | 인식 키워드(예) | 데이터 추출 방식 |
|---|---|---|
| 재무제표 | 의료수익, 당기순이익, FSA_REPORT | `<script>`에 내장된 `FSA_REPORT_PAYLOAD` JSON 직접 파싱 |
| 원무통계 | 내원환자, 신환, 재진, 내원경로 | 본문 텍스트 정제 + `<table>` → 마크다운 변환 |
| 심사평가 | 심사평가, 삭감, 청구심사 | 본문 텍스트 정제 + `<table>` → 마크다운 변환 |
| 인력관리 | 정원, 이직률, 인건비율, 초과근무 | 본문 텍스트 + `Plotly.newPlot(...)` 내 base64 시계열 디코딩 |

파일명·본문 키워드로 자동 분류하되, 업로드 화면에서 언제든 수동으로
유형을 재지정할 수 있습니다. 시스템 버전이 달라 필드가 안 잡혀도, 정제된
본문 텍스트 전체가 함께 AI에 전달되므로 분석 품질에는 큰 영향이 없습니다.

---

## 🗂️ 보관함

생성된 브리핑은 `data/briefings/`에 HTML 파일 + `index.json`(메타데이터
인덱스) 형태로 저장됩니다. 별도 DB 없이 바로 배포 가능하도록 설계했으며,
추후 Supabase 등으로 교체하려면 `core/storage.py`의 함수 4개
(`save_briefing`, `list_briefings`, `load_briefing_html`, `delete_briefing`)
시그니처만 유지한 채 내부 구현을 바꾸면 됩니다.

> ⚠️ 업로드된 **원본 4대 보고서 자체는 저장하지 않습니다.** 분석에만 사용되고
> 세션 종료 시 폐기됩니다. 저장되는 것은 AI가 생성한 브리핑 결과물뿐입니다.

---

## 🎨 리포트 디자인 톤

기존 4개 시스템 리포트의 브랜드 톤(딥 네이비 + 티얼 그린, Pretendard)을
계승하되, "AI가 만든 상위 브리핑"이라는 인상을 위해 골드 포인트 컬러,
글래스모피즘 커버, SVG 도넛 게이지, 교차 인사이트 카드 등을 추가해 한 단계
더 고급스러운 톤으로 구성했습니다. 외부 JS 의존성 없이 순수 SVG/CSS로만
그려 오프라인에서도 완벽하게 열립니다.

---

## ⚠️ 참고 사항

- 이 저장소에는 실제 Gemini API 키가 포함되어 있지 않습니다. 반드시 본인의
  키를 발급받아 설정하세요.
- `core/ai_engine.py`는 `google-genai` SDK를 사용합니다
  (`pip install google-genai`).
- 라이선스 게이트(`core/auth.py`)는 간단한 키 대조 방식입니다. 실제 결제
  연동이 필요하면 이 모듈을 확장하세요.
