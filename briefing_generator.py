# -*- coding: utf-8 -*-
from datetime import datetime

import streamlit as st
import streamlit.components.v1 as components

from core.ai_engine import DEFAULT_MODEL_CHAIN, generate_briefing
from core.parsers import REPORT_TYPES, ParsedReport, parse_report
from core.report_builder import build_html_report
from core.storage import save_briefing

st.title("✨ 새 AI 경영 브리핑 생성")
st.caption(
    "원무통계 · 심사평가 · 인력관리 · 재무제표 보고서(HTML)를 업로드하면, "
    "AI가 4개 시스템 데이터를 교차 분석해 프리미엄 경영 브리핑을 생성합니다."
)

TYPE_LABELS = {k: f"{v['icon']} {v['label']}" for k, v in REPORT_TYPES.items()}
TYPE_LABELS["unknown"] = "❓ 자동 분류 실패 (직접 지정)"

# ────────────────────────────────────────────────────────────────
# STEP 1. 업로드
# ────────────────────────────────────────────────────────────────
st.markdown("### 1️⃣ 기존 보고서 업로드")
uploaded = st.file_uploader(
    "HTML 보고서 파일을 선택하세요 (최대 4개 — 원무통계 / 심사평가 / 인력관리 / 재무제표)",
    type=["html", "htm"],
    accept_multiple_files=True,
)

parsed_reports: list[ParsedReport] = []

if uploaded:
    st.markdown("#### 인식된 보고서")
    cols_per_row = 2
    rows = [uploaded[i : i + cols_per_row] for i in range(0, len(uploaded), cols_per_row)]
    for row in rows:
        cols = st.columns(cols_per_row)
        for col, f in zip(cols, row):
            html_content = f.getvalue().decode("utf-8", errors="ignore")
            pr = parse_report(f.name, html_content)
            with col:
                with st.container(border=True):
                    st.markdown(f"**📄 {f.name}**")
                    default_idx = list(TYPE_LABELS.keys()).index(pr.report_type) if pr.report_type in TYPE_LABELS else 0
                    chosen = st.selectbox(
                        "보고서 유형",
                        options=list(TYPE_LABELS.keys()),
                        format_func=lambda k: TYPE_LABELS[k],
                        index=default_idx,
                        key=f"type_{f.name}",
                    )
                    if chosen != pr.report_type:
                        pr.report_type = chosen
                        pr.label = REPORT_TYPES.get(chosen, {}).get("label", "미분류 보고서")
                    if pr.quick_kpis:
                        st.caption(" · ".join(f"{k}: {v}" for k, v in pr.quick_kpis.items()))
                    else:
                        st.caption(pr.title or "핵심 지표를 자동 인식하지 못했습니다 (AI가 본문에서 직접 분석합니다).")
                    parsed_reports.append(pr)

    missing = [k for k in ["finance", "office", "claims", "hr"] if k not in {p.report_type for p in parsed_reports}]
    if missing:
        st.warning(
            "다음 보고서가 없어도 브리핑 생성은 가능하지만, 교차 분석 품질을 위해 4종 모두 업로드하는 것을 권장합니다: "
            + ", ".join(REPORT_TYPES[m]["label"] for m in missing)
        )
else:
    st.info("먼저 4대 시스템에서 내려받은 HTML 보고서 파일을 업로드해주세요.")

st.divider()

# ────────────────────────────────────────────────────────────────
# STEP 2. 기본 정보
# ────────────────────────────────────────────────────────────────
st.markdown("### 2️⃣ 브리핑 기본 정보")
c1, c2 = st.columns(2)
with c1:
    hospital_name = st.text_input(
        "병원/기관명", value=st.session_state.get("default_hospital_name", "")
    )
with c2:
    period_label = st.text_input(
        "브리핑 기준 기간", placeholder="예: 2026년 7월 경영 브리핑 (전월 대비)"
    )

extra_notes = st.text_area(
    "컨설턴트 추가 메모 (선택)",
    placeholder="예: 이번 달 신환 마케팅 캠페인을 진행했음 / 한방 진료과 삭감 이슈를 중점적으로 다뤄줄 것 등 — AI 분석에 반영됩니다.",
    height=90,
)

st.divider()

# ────────────────────────────────────────────────────────────────
# STEP 3. AI 브리핑 생성
# ────────────────────────────────────────────────────────────────
st.markdown("### 3️⃣ AI 경영 브리핑 생성")

api_key = st.session_state.get("gemini_api_key", "")
if not api_key:
    st.warning("⚠️ Gemini API 키가 설정되지 않았습니다. 좌측 메뉴의 **API · 환경 설정**에서 먼저 등록해주세요.")

generate_disabled = not uploaded or not api_key

if st.button("🧠 AI 경영 브리핑 생성하기", type="primary", disabled=generate_disabled, use_container_width=True):
    context_blocks = [pr.to_ai_context_block() for pr in parsed_reports]

    status_area = st.empty()
    progress = st.progress(0, text="AI 분석 준비 중...")

    def on_attempt(model_name: str, idx: int):
        progress.progress(min(0.15 + idx * 0.25, 0.9), text=f"'{model_name}' 모델로 분석 시도 중...")

    with st.spinner("4개 시스템 데이터를 교차 분석하고 있습니다. 최대 1분 정도 소요될 수 있습니다..."):
        result = generate_briefing(
            api_key=api_key,
            context_blocks=context_blocks,
            hospital_name=hospital_name,
            period_label=period_label,
            extra_notes=extra_notes,
            model_chain=st.session_state.get("model_chain", DEFAULT_MODEL_CHAIN),
            on_attempt=on_attempt,
        )
    progress.progress(1.0, text="완료")

    if not result.ok:
        status_area.error(f"❌ AI 브리핑 생성에 실패했습니다: {result.error}")
    else:
        status_area.success(f"✅ AI 분석 완료 — 사용된 모델: `{result.model_used}`")
        html_report = build_html_report(
            ai_data=result.data,
            parsed_reports=parsed_reports,
            hospital_name=hospital_name,
            period_label=period_label,
            model_used=result.model_used,
            consultant_name=st.session_state.get("default_consultant_name", ""),
            generated_at=datetime.now(),
        )
        st.session_state["last_report_html"] = html_report
        st.session_state["last_ai_data"] = result.data
        st.session_state["last_meta"] = {
            "hospital_name": hospital_name,
            "period_label": period_label,
            "model_used": result.model_used,
        }

st.divider()

# ────────────────────────────────────────────────────────────────
# STEP 4. 결과 미리보기 + 저장/다운로드
# ────────────────────────────────────────────────────────────────
if st.session_state.get("last_report_html"):
    st.markdown("### 4️⃣ 결과 미리보기")
    meta = st.session_state.get("last_meta", {})

    dl_col, save_col, _ = st.columns([1, 1, 3])
    fname = f"AI경영브리핑_{(meta.get('hospital_name') or '병원')}_{datetime.now().strftime('%Y%m%d')}.html"
    with dl_col:
        st.download_button(
            "⬇️ HTML로 저장",
            data=st.session_state["last_report_html"],
            file_name=fname,
            mime="text/html",
            use_container_width=True,
        )
    with save_col:
        if st.button("🗂️ 보관함에 저장", use_container_width=True):
            rec = save_briefing(
                html_content=st.session_state["last_report_html"],
                hospital_name=meta.get("hospital_name", ""),
                period_label=meta.get("period_label", ""),
                ai_data=st.session_state["last_ai_data"],
                model_used=meta.get("model_used", ""),
            )
            st.toast(f"보관함에 저장되었습니다 (ID: {rec.id})", icon="✅")

    components.html(st.session_state["last_report_html"], height=1400, scrolling=True)
