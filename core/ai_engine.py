# -*- coding: utf-8 -*-
"""
core/ai_engine.py
────────────────────────────────────────────────────────────────
Google Gemini API를 이용해 4대 시스템 데이터를 교차 분석하고, 구조화된
"AI 경영 브리핑" JSON을 생성한다.

- 기본 모델: gemini-3.6-flash
- 사용량 초과(429/RESOURCE_EXHAUSTED) 시 자동 폴백: gemini-3.5-flash-lite
- 그 이하 폴백(gemini-2.5-flash, gemini-2.0-flash)도 옵션으로 유지해
  완전한 서비스 중단을 최대한 방지한다 (메디엄 기존 앱들과 동일한 패턴).
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Callable

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:  # pragma: no cover
    genai = None
    genai_types = None


DEFAULT_MODEL_CHAIN = [
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
]

RETRYABLE_MARKERS = [
    "429",
    "resource_exhausted",
    "quota",
    "rate limit",
    "unavailable",
    "internal error",
    "503",
]


@dataclass
class AIResult:
    ok: bool
    data: dict | None = None
    raw_text: str = ""
    model_used: str = ""
    attempts: list[str] = field(default_factory=list)
    error: str = ""


SYSTEM_INSTRUCTION = """\
당신은 한국 병원 경영 컨설팅 회사 '메디엄(MEDIUM)'의 수석 병원 경영분석가 AI입니다.
아래에 제공되는 4대 시스템(원무통계 / 심사평가 / 인력관리 / 재무제표) 데이터를 근거로,
병원장(원장/이사장)이 즉시 의사결정에 활용할 수 있는 "AI 경영 브리핑"을 작성합니다.

작성 원칙:
1. 반드시 제공된 수치 데이터에 근거하여 서술하고, 데이터에 없는 사실을 추측해서 만들어내지 않습니다.
2. 단일 시스템 요약에 그치지 않고, 여러 시스템 데이터를 "교차 분석"하여 다른 곳에서는 보이지 않는
   인사이트를 최소 2개 이상 도출합니다.
   (예: 원무통계의 환자 수 감소 + 재무제표의 매출 정체가 동시에 나타나는지,
    인력관리의 인건비율 상승 + 재무제표의 인건비 비율 초과가 같은 방향인지,
    심사평가의 삭감 위험이 특정 진료과·보험자에 집중되어 원무통계 상 해당 과 환자 구성과
    연결되는지 등)
3. 리스크는 반드시 심각도(high/medium/low)와 함께 "무엇을, 왜, 어떻게" 형식으로 구체적으로 적습니다.
4. 실행 로드맵은 즉시/1주 이내/1개월 이내/분기 단위로 나누어 현장에서 바로 실행 가능한 수준으로 적습니다.
5. 어조는 전문적이고 간결하되, 병원장이 바쁜 와중에도 30초 안에 핵심을 파악할 수 있도록 씁니다.
6. 반드시 순수 JSON만 출력합니다. 코드펜스(```), 설명 문구, 마크다운을 절대 포함하지 마세요.
"""

JSON_SCHEMA_HINT = """\
다음 JSON 스키마를 정확히 따라 응답하세요 (키 이름 변경 금지, 값은 모두 한국어):

{
  "hospital_health_score": 0-100 사이 정수 (4개 시스템 데이터를 종합한 경영건전성 점수),
  "health_grade": "우수" | "양호" | "보통" | "주의" | "위험" 중 하나,
  "headline": "한 줄 종합 총평 (40자 이내)",
  "executive_summary": "3~5문장의 경영진 요약 (병원장이 가장 먼저 읽는 부분)",
  "kpi_snapshot": [
    {"label": "지표명", "value": "표시값", "trend": "전월/전기 대비 변화 설명", "status": "good"|"warn"|"bad"}
    // 4~8개, 4개 시스템에서 고르게 선정
  ],
  "cross_module_insights": [
    {"title": "인사이트 제목", "modules": ["finance","office","claims","hr"] 중 관련된 것들,
     "detail": "왜 이것이 여러 데이터를 연결해야만 보이는 인사이트인지 구체적 수치와 함께 서술",
     "impact": "high"|"medium"|"low"}
    // 최소 2개 이상, 이 리포트의 핵심 가치
  ],
  "strengths": [
    {"title": "강점 제목", "detail": "구체적 근거", "module": "finance|office|claims|hr|cross"}
  ],
  "risks": [
    {"title": "리스크 제목", "severity": "high"|"medium"|"low",
     "detail": "무엇이 문제이고 왜 발생했는지", "evidence": "근거 수치",
     "module": "finance|office|claims|hr|cross"}
  ],
  "module_deep_dive": {
    "finance": {"summary": "요약", "key_findings": ["...", "..."], "recommended_actions": ["...", "..."]},
    "office": {"summary": "요약", "key_findings": ["...", "..."], "recommended_actions": ["...", "..."]},
    "claims": {"summary": "요약", "key_findings": ["...", "..."], "recommended_actions": ["...", "..."]},
    "hr": {"summary": "요약", "key_findings": ["...", "..."], "recommended_actions": ["...", "..."]}
    // 업로드되지 않은 모듈은 {"summary": "업로드되지 않음", "key_findings": [], "recommended_actions": []} 로 표기
  },
  "action_roadmap": [
    {"timeframe": "즉시", "items": ["...", "..."]},
    {"timeframe": "1주 이내", "items": ["...", "..."]},
    {"timeframe": "1개월 이내", "items": ["...", "..."]},
    {"timeframe": "다음 분기", "items": ["...", "..."]}
  ],
  "next_month_checkpoints": ["다음 브리핑에서 반드시 재확인해야 할 지표", "..."]
}
"""


def build_prompt(context_blocks: list[str], hospital_name: str, period_label: str, extra_notes: str) -> str:
    joined = "\n\n".join(context_blocks)
    notes = f"\n\n[컨설턴트 추가 메모]\n{extra_notes}\n" if extra_notes.strip() else ""
    return f"""{SYSTEM_INSTRUCTION}

[분석 대상]
병원/기관명: {hospital_name or "미지정"}
브리핑 기준 기간: {period_label or "업로드 자료 기준"}
{notes}
[제공 데이터 — 4대 시스템 원본 보고서 발췌]
{joined}

{JSON_SCHEMA_HINT}
"""


def _extract_json(raw_text: str) -> dict | None:
    text = raw_text.strip()
    text = re.sub(r"^```(?:json)?", "", text.strip())
    text = re.sub(r"```$", "", text.strip())
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    # 중괄호 균형으로 첫 JSON 블록만 추출 시도
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except Exception:
                    return None
    return None


def _is_retryable(err: Exception) -> bool:
    msg = str(err).lower()
    return any(marker in msg for marker in RETRYABLE_MARKERS)


def generate_briefing(
    api_key: str,
    context_blocks: list[str],
    hospital_name: str = "",
    period_label: str = "",
    extra_notes: str = "",
    model_chain: list[str] | None = None,
    max_output_tokens: int = 8192,
    on_attempt: Callable[[str, int], None] | None = None,
) -> AIResult:
    """Gemini에 브리핑 생성을 요청. 모델을 순서대로 시도하며 실패 시 자동 폴백."""
    if genai is None:
        return AIResult(ok=False, error="google-genai 패키지가 설치되어 있지 않습니다. `pip install google-genai`")
    if not api_key:
        return AIResult(ok=False, error="Gemini API 키가 설정되지 않았습니다.")

    chain = model_chain or DEFAULT_MODEL_CHAIN
    prompt = build_prompt(context_blocks, hospital_name, period_label, extra_notes)

    client = genai.Client(api_key=api_key)
    attempts: list[str] = []
    last_error = ""

    for idx, model_name in enumerate(chain):
        attempts.append(model_name)
        if on_attempt:
            on_attempt(model_name, idx)
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    temperature=0.4,
                    max_output_tokens=max_output_tokens,
                    response_mime_type="application/json",
                ),
            )
            raw_text = (response.text or "").strip()
            if not raw_text:
                raise RuntimeError("빈 응답")
            data = _extract_json(raw_text)
            if data is None:
                raise RuntimeError("JSON 파싱 실패 — 모델이 스키마를 따르지 않음")
            return AIResult(ok=True, data=data, raw_text=raw_text, model_used=model_name, attempts=attempts)
        except Exception as e:
            last_error = f"{model_name}: {e}"
            if _is_retryable(e) or "json" in str(e).lower():
                time.sleep(0.6)
                continue
            # 재시도 불가능한 에러(키 오류 등)는 즉시 중단
            return AIResult(ok=False, error=last_error, attempts=attempts, model_used=model_name)

    return AIResult(ok=False, error=f"모든 모델 시도 실패. 마지막 오류: {last_error}", attempts=attempts)
