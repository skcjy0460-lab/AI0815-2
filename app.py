# -*- coding: utf-8 -*-
"""
app.py
────────────────────────────────────────────────────────────────
MEDIUM AI 경영 브리핑 — 진입점

기존 4대 시스템(원무통계 / 심사평가 / 인력관리 / 재무제표) 보고서(HTML)를
업로드하면, 경영 맞춤 AI가 교차 분석하여 병원장이 바로 볼 수 있는 프리미엄
'AI 경영 브리핑' 리포트를 생성하는 유료 전용 Streamlit 애플리케이션.
"""

import streamlit as st

from core.auth import require_license

st.set_page_config(
    page_title="MEDIUM AI 경영 브리핑",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 전역 스타일 (사이드바 브랜딩 등) ──────────────────────────────
st.markdown(
    """
    <style>
      #MainMenu {visibility: hidden;}
      footer {visibility: hidden;}
      [data-testid="stSidebarNav"] { padding-top: 6px; }
      .medium-sidebar-brand {
        padding: 14px 6px 10px; border-bottom: 1px solid #e2eaec; margin-bottom: 10px;
      }
      .medium-sidebar-brand b { font-size: 17px; color: #0b1f33; letter-spacing: -.3px; }
      .medium-sidebar-brand span { display:block; font-size: 11px; color: #0f9a8c; font-weight: 800; letter-spacing: .06em; margin-top: 2px;}
    </style>
    <div class="medium-sidebar-brand">
      <b>🧠 MEDIUM AI 경영 브리핑</b>
      <span>PREMIUM · POWERED BY 경영 맞춤 AI</span>
    </div>
    """,
    unsafe_allow_html=True,
)

# ── 유료 라이선스 게이트 ──────────────────────────────────────────
require_license()

# ── 페이지 구성 ───────────────────────────────────────────────────
pages = {
    "브리핑": [
        st.Page("views/briefing_generator.py", title="새 브리핑 생성", icon="✨", default=True),
        st.Page("views/archive.py", title="브리핑 보관함", icon="🗂️"),
    ],
    "관리": [
        st.Page("views/settings.py", title="API · 환경 설정", icon="⚙️"),
        st.Page("views/guide.py", title="사용 가이드", icon="📘"),
    ],
}

nav = st.navigation(pages)
nav.run()
