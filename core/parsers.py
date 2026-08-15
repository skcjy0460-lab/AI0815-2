# -*- coding: utf-8 -*-
"""
core/parsers.py
────────────────────────────────────────────────────────────────
기존 4대 시스템(원무통계 / 심사평가 / 인력관리 / 재무제표) HTML 보고서를
업로드 받아 AI(Gemini)가 분석할 수 있는 구조화된 텍스트 + 표 + 원본 JSON
데이터로 변환하는 파서 모듈.

설계 원칙
- 각 보고서는 버전에 따라 마크업이 조금씩 달라질 수 있으므로, "완벽한 필드
  매핑"보다는 "손실 없이 최대한 많은 신호를 텍스트/표 형태로 뽑아 AI에게
  넘기는 것"을 목표로 한다.
- 재무제표 리포트처럼 <script> 안에 원본 JSON(payload)이 박혀 있으면 그것을
  최우선으로 사용한다 (가장 정확).
- 인력관리 리포트처럼 Plotly.newPlot(...) 형태로 차트 데이터가 들어있으면
  base64 바이너리(bdata)까지 디코딩해서 숫자 시계열을 복원한다.
- 심사평가/원무통계처럼 순수 정적 HTML(표+텍스트)이면 표를 markdown으로,
  본문은 정제된 텍스트로 추출한다.
"""

from __future__ import annotations

import base64
import json
import re
import struct
from dataclasses import dataclass, field
from typing import Any

from bs4 import BeautifulSoup

try:
    import pandas as pd
except ImportError:  # pragma: no cover
    pd = None


# ────────────────────────────────────────────────────────────────
# 보고서 유형 분류
# ────────────────────────────────────────────────────────────────

REPORT_TYPES = {
    "finance": {
        "label": "재무제표 분석",
        "icon": "💰",
        "keywords": ["재무제표", "의료수익", "의료이익", "FSA_REPORT", "당기순이익", "재무 건전성"],
    },
    "claims": {
        "label": "심사평가(청구심사)",
        "icon": "🩺",
        "keywords": ["심사평가", "삭감", "청구심사", "심사결정", "보험자별"],
    },
    "office": {
        "label": "원무통계",
        "icon": "🏥",
        "keywords": ["원무통계", "내원환자", "신환", "재진", "내원경로", "주상병"],
    },
    "hr": {
        "label": "인력관리",
        "icon": "👥",
        "keywords": ["인력관리", "정원", "이직률", "인건비율", "초과근무", "연차 사용률", "부서별 인력"],
    },
}


def classify_report(filename: str, html: str) -> str:
    """파일명 + 본문 키워드 점수로 보고서 유형을 추정한다."""
    name = (filename or "").lower()
    score: dict[str, int] = {k: 0 for k in REPORT_TYPES}

    filename_hints = {
        "finance": ["재무", "손익", "fsa", "financial"],
        "claims": ["심사", "청구", "삭감", "claim"],
        "office": ["원무", "내원", "office"],
        "hr": ["인력", "인사", "hr", "노무"],
    }
    for rtype, hints in filename_hints.items():
        for h in hints:
            if h in name:
                score[rtype] += 5

    text_sample = html[:20000]
    for rtype, meta in REPORT_TYPES.items():
        for kw in meta["keywords"]:
            score[rtype] += text_sample.count(kw)

    best = max(score, key=lambda k: score[k])
    if score[best] == 0:
        return "unknown"
    return best


# ────────────────────────────────────────────────────────────────
# 텍스트 / 표 추출
# ────────────────────────────────────────────────────────────────

def strip_to_text(html: str, max_len: int = 12000) -> str:
    """스타일/스크립트를 제거하고 사람이 읽는 본문 텍스트만 정제해서 반환."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text(separator=" | ")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"(\s*\|\s*){2,}", " | ", text).strip()
    if len(text) > max_len:
        text = text[:max_len] + " …(이하 생략)"
    return text


def extract_tables_markdown(html: str, max_tables: int = 12) -> list[str]:
    """<table> 요소들을 마크다운 표로 변환 (AI 프롬프트에 넣기 좋은 형태)."""
    out: list[str] = []
    if pd is None:
        return out
    try:
        import io

        dfs = pd.read_html(io.StringIO(html))
    except Exception:
        return out
    for i, df in enumerate(dfs[:max_tables]):
        try:
            df = df.fillna("")
            out.append(df.to_markdown(index=False))
        except Exception:
            continue
    return out


def extract_balanced_json(html: str, var_pattern: str) -> dict | None:
    """`const XXX_PAYLOAD = { ... };` 형태에서 중괄호 균형을 맞춰 JSON 블록을 추출.
    정규식만으로는 중첩 객체를 안전하게 자를 수 없어 괄호 카운팅으로 처리한다."""
    m = re.search(var_pattern, html)
    if not m:
        return None
    start = html.find("{", m.end() - 1)
    if start == -1:
        return None
    depth = 0
    for i in range(start, min(len(html), start + 200000)):
        ch = html[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                blob = html[start : i + 1]
                try:
                    return json.loads(blob)
                except Exception:
                    return None
    return None


def _decode_plotly_bdata(y: Any) -> Any:
    """Plotly가 {'dtype': 'f8', 'bdata': base64...} 형태로 압축한 숫자 배열을 복원."""
    if not isinstance(y, dict) or "bdata" not in y:
        return y
    dtype = y.get("dtype", "f8")
    fmt_map = {
        "f8": ("d", 8),
        "f4": ("f", 4),
        "i1": ("b", 1),
        "u1": ("B", 1),
        "i2": ("h", 2),
        "u2": ("H", 2),
        "i4": ("i", 4),
        "u4": ("I", 4),
    }
    fmt, size = fmt_map.get(dtype, ("d", 8))
    try:
        raw = base64.b64decode(y["bdata"])
        n = len(raw) // size
        vals = struct.unpack(f"<{n}{fmt}", raw)
        return list(vals)
    except Exception:
        return []


def extract_plotly_series(html: str, max_charts: int = 10) -> list[dict]:
    """Plotly.newPlot("id", [traces...], {...}) 블록에서 이름/축/데이터를 복원."""
    charts: list[dict] = []
    for m in re.finditer(r'Plotly\.newPlot\(\s*"([^"]+)"\s*,\s*(\[.*?\])\s*,\s*(\{.*?\})\s*,?\s*\{', html, re.S):
        if len(charts) >= max_charts:
            break
        chart_id, traces_raw, layout_raw = m.group(1), m.group(2), m.group(3)
        try:
            traces = json.loads(traces_raw)
        except Exception:
            continue
        title = None
        tmatch = re.search(r'"title"\s*:\s*\{\s*"text"\s*:\s*"([^"]*)"', layout_raw)
        if tmatch:
            title = tmatch.group(1)
        simple_traces = []
        for tr in traces:
            x = tr.get("x")
            y = _decode_plotly_bdata(tr.get("y"))
            simple_traces.append(
                {
                    "name": tr.get("name", ""),
                    "type": tr.get("type", ""),
                    "x": x,
                    "y": y,
                }
            )
        charts.append({"id": chart_id, "title": title, "traces": simple_traces})
    return charts


# ────────────────────────────────────────────────────────────────
# 보고서별 payload 변수명 (알려진 패턴들 — 향후 신규 시스템 추가 시 여기에 등록)
# ────────────────────────────────────────────────────────────────

PAYLOAD_PATTERNS = {
    "finance": r"const\s+FSA_REPORT_PAYLOAD\s*=\s*",
    "claims": r"const\s+(?:REVIEW|CLAIM)_[A-Z_]*PAYLOAD\s*=\s*",
    "office": r"const\s+OFFICE_[A-Z_]*PAYLOAD\s*=\s*",
    "hr": r"const\s+HR_[A-Z_]*PAYLOAD\s*=\s*",
}


# ────────────────────────────────────────────────────────────────
# 통합 결과 객체
# ────────────────────────────────────────────────────────────────

@dataclass
class ParsedReport:
    source_filename: str
    report_type: str
    label: str
    title: str = ""
    period_hint: str = ""
    text: str = ""
    tables_md: list[str] = field(default_factory=list)
    payload: dict | None = None
    plotly_series: list[dict] = field(default_factory=list)
    quick_kpis: dict[str, str] = field(default_factory=dict)

    def to_ai_context_block(self) -> str:
        """Gemini 프롬프트에 그대로 삽입할 수 있는 컨텍스트 블록 생성."""
        parts = [f"### [{self.label}] 원본 파일: {self.source_filename}"]
        if self.title:
            parts.append(f"문서 제목: {self.title}")
        if self.period_hint:
            parts.append(f"기간 정보: {self.period_hint}")
        if self.quick_kpis:
            kv = " / ".join(f"{k}: {v}" for k, v in self.quick_kpis.items())
            parts.append(f"핵심 수치 요약: {kv}")
        if self.payload:
            parts.append("원본 구조화 데이터(JSON, 정확한 수치 근거로 사용):")
            parts.append("```json\n" + json.dumps(self.payload, ensure_ascii=False)[:8000] + "\n```")
        if self.plotly_series:
            parts.append("차트 원본 시계열 데이터:")
            for s in self.plotly_series[:6]:
                parts.append(f"- {s.get('title') or s['id']}")
                for tr in s["traces"][:6]:
                    xs = tr["x"][:12] if isinstance(tr["x"], list) else tr["x"]
                    ys = tr["y"][:12] if isinstance(tr["y"], list) else tr["y"]
                    parts.append(f"  · {tr['name']}: x={xs} y={ys}")
        if self.tables_md:
            parts.append("표 데이터:")
            for t in self.tables_md[:8]:
                parts.append(t)
        parts.append("본문 텍스트 발췌:")
        parts.append(self.text[:4000])
        return "\n".join(parts)


def _guess_title(html: str) -> str:
    m = re.search(r"<title>(.*?)</title>", html, re.S)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip()
    m = re.search(r"<h[12][^>]*>(.*?)</h[12]>", html, re.S)
    if m:
        return re.sub(r"<[^>]+>", "", m.group(1)).strip()
    return ""


def _guess_period(text: str) -> str:
    m = re.search(r"(\d{4}\s*년\s*\d{1,2}\s*월[^|,\.]{0,20})", text)
    if m:
        return m.group(1).strip()
    m = re.search(r"(제\s*\d+\s*\(?[당전]\)?기)", text)
    if m:
        return m.group(1).strip()
    return ""


def _quick_kpis_for(rtype: str, text: str) -> dict[str, str]:
    """보고서 유형별로 자주 나오는 KPI 문구를 가볍게 잡아낸다(있으면 좋고, 없어도 무방)."""
    hints: dict[str, str] = {}

    def grab(label: str, pattern: str):
        m = re.search(pattern, text)
        if m:
            hints[label] = m.group(1).strip()

    if rtype == "finance":
        grab("의료수익", r"의료수익\s*\|\s*([0-9.,]+\s*[억만]?원)")
        grab("의료이익률", r"의료이익률\s*\|\s*([0-9.]+%)")
        grab("당기순이익률", r"당기순이익률\s*\|\s*([0-9.]+%)")
        grab("재무 건전성 점수", r"재무 건전성\s*\|\s*(\d+)\s*\|\s*/100")
    elif rtype == "claims":
        grab("총 청구금액", r"총 청구금액\s*\|\s*([0-9.,]+\s*[억만]?\s*원)")
        grab("총 삭감률", r"총 삭감률\s*\|\s*([0-9.]+%)")
        grab("총 삭감액", r"총 삭감액\s*\|?\s*([0-9.,]+\s*[억만]?\s*원)")
    elif rtype == "office":
        grab("총 내원환자", r"총 내원환자\s*\|\s*(\d+\s*명)")
        grab("신환·초진", r"신환[ㆍ·]초진\s*\|\s*(\d+\s*명)")
        grab("재진", r"재진\s*\|\s*(\d+\s*명)")
    elif rtype == "hr":
        grab("전체 직원 수", r"전체 직원 수\s*\|\s*(\d+)\s*\|?\s*명")
        grab("인건비율", r"인건비율\(?매출대비\)?\s*\|\s*([0-9.]+)\s*\|?\s*%")
        grab("이직률(연환산)", r"이직률\(연환산\)\s*\|\s*([0-9.]+)\s*\|?\s*%")

    return hints


def parse_report(filename: str, html: str) -> ParsedReport:
    rtype = classify_report(filename, html)
    label = REPORT_TYPES.get(rtype, {}).get("label", "미분류 보고서")
    text = strip_to_text(html)
    title = _guess_title(html)
    period = _guess_period(text)

    payload = None
    pattern = PAYLOAD_PATTERNS.get(rtype)
    if pattern:
        payload = extract_balanced_json(html, pattern)
    if payload is None:
        # 알려지지 않은 변수명이라도 *_PAYLOAD 형태면 시도
        payload = extract_balanced_json(html, r"const\s+[A-Z0-9_]*PAYLOAD\s*=\s*")

    plotly_series = extract_plotly_series(html) if "Plotly.newPlot" in html else []
    tables_md = extract_tables_markdown(html)
    quick_kpis = _quick_kpis_for(rtype, text)

    return ParsedReport(
        source_filename=filename,
        report_type=rtype,
        label=label,
        title=title,
        period_hint=period,
        text=text,
        tables_md=tables_md,
        payload=payload,
        plotly_series=plotly_series,
        quick_kpis=quick_kpis,
    )


def parse_uploaded_files(files: dict[str, str]) -> list[ParsedReport]:
    """{filename: html_content} 딕셔너리를 받아 ParsedReport 리스트로 변환."""
    results = []
    for fname, html in files.items():
        try:
            results.append(parse_report(fname, html))
        except Exception as e:  # 개별 파일 파싱 실패가 전체를 막지 않도록
            results.append(
                ParsedReport(
                    source_filename=fname,
                    report_type="unknown",
                    label=f"파싱 실패 ({e})",
                    text=strip_to_text(html) if html else "",
                )
            )
    return results
