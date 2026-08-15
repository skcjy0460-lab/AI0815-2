# -*- coding: utf-8 -*-
from datetime import datetime

import streamlit as st
import streamlit.components.v1 as components

from core.storage import delete_briefing, list_briefings, load_briefing_html

st.title("🗂️ 브리핑 보관함")
st.caption("생성된 AI 경영 브리핑을 다시 열람하거나 다운로드할 수 있습니다.")

records = list_briefings()

if not records:
    st.info("아직 저장된 브리핑이 없습니다. **새 브리핑 생성** 메뉴에서 먼저 브리핑을 만들어 보관함에 저장해보세요.")
else:
    grade_color = {"우수": "#0f9a8c", "양호": "#2867b2", "보통": "#c9860f", "주의": "#e07a1f", "위험": "#c0392b"}

    q = st.text_input("🔍 병원명으로 검색", placeholder="예: 서울참편한한방병원")
    filtered = [r for r in records if q.strip() in r["hospital_name"]] if q.strip() else records

    for rec in filtered:
        color = grade_color.get(rec.get("health_grade", ""), "#64748b")
        with st.container(border=True):
            top = st.columns([3, 1, 1, 1])
            with top[0]:
                st.markdown(f"**🏥 {rec['hospital_name']}** · {rec.get('period_label') or '기간 미지정'}")
                st.caption(rec.get("headline", ""))
            with top[1]:
                st.markdown(
                    f"<div style='text-align:center'><span style='background:{color}20;color:{color};"
                    f"font-weight:900;padding:4px 12px;border-radius:999px;font-size:12px'>"
                    f"{rec.get('health_grade','-')} · {rec.get('health_score','-')}점</span></div>",
                    unsafe_allow_html=True,
                )
            with top[2]:
                created = rec.get("created_at", "")
                try:
                    created = datetime.fromisoformat(created).strftime("%Y.%m.%d %H:%M")
                except Exception:
                    pass
                st.caption(f"🕒 {created}")
            with top[3]:
                st.caption(f"🤖 {rec.get('model_used','-')}")

            btn_cols = st.columns([1, 1, 1, 5])
            with btn_cols[0]:
                view = st.button("열람", key=f"view_{rec['id']}", use_container_width=True)
            with btn_cols[1]:
                html_data = load_briefing_html(rec["filename"]) or ""
                st.download_button(
                    "다운로드", data=html_data, file_name=rec["filename"], mime="text/html",
                    key=f"dl_{rec['id']}", use_container_width=True,
                )
            with btn_cols[2]:
                if st.button("삭제", key=f"del_{rec['id']}", use_container_width=True):
                    delete_briefing(rec["id"])
                    st.rerun()

            if view:
                components.html(html_data, height=1400, scrolling=True)
