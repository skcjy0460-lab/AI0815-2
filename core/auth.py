# -*- coding: utf-8 -*-
"""
core/auth.py
────────────────────────────────────────────────────────────────
유료 전용 서비스이므로, 라이선스 키(또는 접근 비밀번호) 입력 전까지
전체 앱 사용을 막는 간단한 게이트를 제공한다.

운영 방식
- Streamlit Cloud 배포 시 `.streamlit/secrets.toml` 에 아래 키를 등록:
    LICENSE_KEYS = ["MEDIUM-XXXX-XXXX", "MEDIUM-YYYY-YYYY"]
  (고객사별로 개별 키를 발급해 관리하거나, 단일 키로 통합 운영해도 됨)
- 키가 secrets에 없으면 데모 모드로 간주해 게이트를 건너뛴다(로컬 개발 편의).
"""

from __future__ import annotations

import streamlit as st


def _get_license_keys() -> list[str]:
    try:
        keys = st.secrets.get("LICENSE_KEYS")
        if isinstance(keys, str):
            return [keys]
        if isinstance(keys, (list, tuple)):
            return list(keys)
    except Exception:
        pass
    return []


def require_license():
    """유효한 라이선스 키가 세션에 있을 때까지 입력 폼을 렌더링하고 앱 실행을 중단한다."""
    valid_keys = _get_license_keys()
    if not valid_keys:
        return  # secrets 미설정 = 데모/개발 모드, 게이트 생략

    if st.session_state.get("licensed"):
        return

    st.markdown("## 🔒 MEDIUM AI 경영 브리핑 — 유료 서비스")
    st.caption("본 프로그램은 메디엄(MEDIUM) 유료 컨설팅 고객 전용입니다. 발급받은 라이선스 키를 입력해주세요.")
    with st.form("license_form"):
        key = st.text_input("라이선스 키", type="password", placeholder="MEDIUM-XXXX-XXXX")
        submitted = st.form_submit_button("접속하기", use_container_width=True, type="primary")
    if submitted:
        if key.strip() in valid_keys:
            st.session_state["licensed"] = True
            st.rerun()
        else:
            st.error("유효하지 않은 라이선스 키입니다. 담당 컨설턴트에게 문의해주세요.")
    st.stop()
