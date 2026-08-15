# -*- coding: utf-8 -*-
import streamlit as st

from core.ai_engine import DEFAULT_MODEL_CHAIN, generate_briefing

st.title("⚙️ API · 환경 설정")
st.caption("Gemini API 키와 모델 폴백 체인, 기본 컨설턴트 정보를 설정합니다. 이 설정은 현재 브라우저 세션에만 저장됩니다.")

st.divider()

# ── Gemini API 키 ──────────────────────────────────────────────
st.subheader("🔑 Gemini API 키")

secret_key = None
try:
    secret_key = st.secrets.get("GEMINI_API_KEY")
except Exception:
    secret_key = None

if secret_key:
    st.success("Streamlit Secrets에 등록된 API 키를 사용 중입니다. (`GEMINI_API_KEY`)")
    st.session_state.setdefault("gemini_api_key", secret_key)
else:
    api_key_input = st.text_input(
        "Gemini API 키",
        value=st.session_state.get("gemini_api_key", ""),
        type="password",
        placeholder="AIza...",
        help="Google AI Studio에서 발급받은 API 키를 입력하세요. 배포 시에는 .streamlit/secrets.toml의 GEMINI_API_KEY를 권장합니다.",
    )
    if api_key_input:
        st.session_state["gemini_api_key"] = api_key_input

st.divider()

# ── 모델 폴백 체인 ──────────────────────────────────────────────
st.subheader("🔁 모델 자동 폴백 체인")
st.caption("첫 번째 모델의 사용량이 초과(429/RESOURCE_EXHAUSTED)되면 다음 모델로 자동 전환합니다.")

default_chain = st.session_state.get("model_chain", DEFAULT_MODEL_CHAIN)
chain_text = st.text_area(
    "모델 순서 (한 줄에 하나씩, 위에서부터 우선순위)",
    value="\n".join(default_chain),
    height=130,
)
new_chain = [m.strip() for m in chain_text.splitlines() if m.strip()]
if new_chain:
    st.session_state["model_chain"] = new_chain

cols = st.columns(len(st.session_state.get("model_chain", DEFAULT_MODEL_CHAIN)))
for c, m in zip(cols, st.session_state.get("model_chain", DEFAULT_MODEL_CHAIN)):
    c.markdown(f"<div style='text-align:center;padding:8px;border:1px solid #e2eaec;border-radius:8px;'>"
               f"<b>{m}</b></div>", unsafe_allow_html=True)

if st.button("🧪 API 키 연결 테스트", type="secondary"):
    api_key = st.session_state.get("gemini_api_key", "")
    if not api_key:
        st.error("먼저 API 키를 입력해주세요.")
    else:
        with st.spinner("Gemini API 연결을 확인하는 중..."):
            result = generate_briefing(
                api_key=api_key,
                context_blocks=["### 테스트\n연결 테스트용 더미 데이터입니다. hospital_health_score는 88로 응답하세요."],
                hospital_name="연결 테스트",
                period_label="테스트",
                model_chain=st.session_state.get("model_chain", DEFAULT_MODEL_CHAIN),
            )
        if result.ok:
            st.success(f"✅ 연결 성공 — 사용된 모델: `{result.model_used}` (시도: {', '.join(result.attempts)})")
        else:
            st.error(f"❌ 연결 실패: {result.error}")

st.divider()

# ── 기본 정보 ──────────────────────────────────────────────────
st.subheader("🏥 기본 정보")
col1, col2 = st.columns(2)
with col1:
    st.session_state["default_hospital_name"] = st.text_input(
        "기본 병원/기관명", value=st.session_state.get("default_hospital_name", "")
    )
with col2:
    st.session_state["default_consultant_name"] = st.text_input(
        "담당 컨설턴트명 (선택)", value=st.session_state.get("default_consultant_name", "")
    )

st.info(
    "💡 배포 시에는 `.streamlit/secrets.toml`에 아래와 같이 등록하면 사용자가 매번 키를 입력할 필요가 없습니다.\n\n"
    "```toml\n"
    'GEMINI_API_KEY = "AIza..."\n'
    'LICENSE_KEYS = ["MEDIUM-XXXX-XXXX"]\n'
    "```"
)
