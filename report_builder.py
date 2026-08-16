# -*- coding: utf-8 -*-
"""
core/report_builder.py
────────────────────────────────────────────────────────────────
AI(Gemini)가 생성한 구조화 JSON + 4대 시스템 원본 파싱 데이터를 결합하여,
단일 파일로 저장/공유 가능한 "AI 경영 브리핑" 프리미엄 HTML 리포트를 만든다.

디자인 방향
- 기존 4개 시스템 리포트의 브랜드 톤(딥 네이비 + 티얼 그린)을 계승하되,
  "AI가 만든 상위 브리핑"이라는 인상을 주기 위해 골드 포인트 컬러와
  글래스모피즘 커버, 도넛 게이지, 인사이트 카드 등 한 단계 더 고급스러운
  비주얼 언어를 사용한다.
- 외부 JS 의존성 없이 순수 SVG/CSS만으로 그려서, 파일 하나로 저장해도
  인터넷 연결 없이 완벽하게 렌더링되도록 한다 (오프라인 열람 · 인쇄 대응).
"""

from __future__ import annotations

import html as _html
import math
from datetime import datetime
from pathlib import Path
from typing import Any

from core.parsers import ParsedReport, REPORT_TYPES

# 리포트에 노출되는 분석 엔진 표기명 (실제 사용된 Gemini 모델명은 내부 로그/보관함
# 메타데이터에만 남기고, 고객에게 보여지는 문서에는 브랜딩된 명칭만 사용한다)
ENGINE_DISPLAY_NAME = "경영 맞춤 AI"

_VENDOR_DIR = Path(__file__).resolve().parent / "vendor"
_HTML2CANVAS_CACHE: str | None = None


def _load_html2canvas_js() -> str:
    """JPG 저장 기능에 쓰이는 html2canvas 라이브러리를 인라인으로 번들링.
    외부 CDN 없이도(오프라인 열람 시에도) 리포트 파일 하나로 완결되도록 한다."""
    global _HTML2CANVAS_CACHE
    if _HTML2CANVAS_CACHE is None:
        try:
            _HTML2CANVAS_CACHE = (_VENDOR_DIR / "html2canvas.min.js").read_text(encoding="utf-8")
        except Exception:
            _HTML2CANVAS_CACHE = ""  # 파일이 없으면 JPG 저장 버튼은 비활성 안내만 표시
    return _HTML2CANVAS_CACHE


MODULE_META = {
    "finance": {"label": "재무제표 분석", "icon": "💰", "color": "#2867b2"},
    "office": {"label": "원무통계", "icon": "🏥", "color": "#0f9a8c"},
    "claims": {"label": "심사평가", "icon": "🩺", "color": "#078d83"},
    "hr": {"label": "인력관리", "icon": "👥", "color": "#7c5cff"},
    "cross": {"label": "교차 분석", "icon": "🔗", "color": "#b8860b"},
}

SEVERITY_META = {
    "high": {"label": "높음", "color": "#c0392b", "bg": "#fdecea"},
    "medium": {"label": "중간", "color": "#b8860b", "bg": "#fff6e0"},
    "low": {"label": "낮음", "color": "#3a7d44", "bg": "#eef8ee"},
}

STATUS_META = {
    "good": {"label": "양호", "color": "#0f9a8c", "bg": "#eafaf6"},
    "warn": {"label": "주의", "color": "#c9860f", "bg": "#fff6e3"},
    "bad": {"label": "위험", "color": "#c0392b", "bg": "#fdecea"},
}

GRADE_COLOR = {
    "우수": "#0f9a8c",
    "양호": "#2867b2",
    "보통": "#c9860f",
    "주의": "#e07a1f",
    "위험": "#c0392b",
}


def esc(x: Any) -> str:
    return _html.escape(str(x)) if x is not None else ""


def _js_str(x: str) -> str:
    """파이썬 문자열을 안전한 JS 문자열 리터럴로 변환."""
    import json as _json

    return _json.dumps(x or "")


def _donut_svg(score: int, grade: str) -> str:
    score = max(0, min(100, int(score)))
    color = GRADE_COLOR.get(grade, "#0f9a8c")
    r = 74
    circumference = 2 * math.pi * r
    offset = circumference * (1 - score / 100)
    return f"""
    <svg viewBox="0 0 180 180" width="180" height="180" class="ai-score-donut">
      <defs>
        <linearGradient id="scoreGrad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="{color}" stop-opacity="0.55"/>
          <stop offset="100%" stop-color="{color}"/>
        </linearGradient>
      </defs>
      <circle cx="90" cy="90" r="{r}" fill="none" stroke="#eef3f4" stroke-width="16"/>
      <circle cx="90" cy="90" r="{r}" fill="none" stroke="url(#scoreGrad)" stroke-width="16"
        stroke-linecap="round" stroke-dasharray="{circumference:.2f}" stroke-dashoffset="{offset:.2f}"
        transform="rotate(-90 90 90)"/>
      <text x="90" y="86" text-anchor="middle" font-size="40" font-weight="900" fill="#0b1f33">{score}</text>
      <text x="90" y="110" text-anchor="middle" font-size="13" font-weight="700" fill="#64748b">/ 100</text>
    </svg>
    """


def _bar(pct: float, color: str, height: int = 10) -> str:
    pct = max(0, min(100, pct))
    return (
        f'<i style="display:block;width:{pct:.1f}%;height:{height}px;border-radius:999px;'
        f'background:{color}"></i>'
    )


def _kpi_snapshot_html(kpis: list[dict]) -> str:
    cards = []
    for k in kpis or []:
        status = STATUS_META.get(k.get("status", "good"), STATUS_META["good"])
        cards.append(f"""
        <article class="kpi-card" style="border-left-color:{status['color']}">
          <small>{esc(k.get('label',''))}</small>
          <b>{esc(k.get('value',''))}</b>
          <span class="kpi-trend" style="color:{status['color']}">{esc(k.get('trend',''))}</span>
          <em class="kpi-badge" style="background:{status['bg']};color:{status['color']}">{status['label']}</em>
        </article>""")
    return f'<div class="kpi-grid">{"".join(cards)}</div>'


def _cross_insights_html(insights: list[dict]) -> str:
    blocks = []
    for ins in insights or []:
        impact = ins.get("impact", "medium")
        sev = SEVERITY_META.get(impact, SEVERITY_META["medium"])
        mod_chips = "".join(
            f'<span class="mod-chip" style="background:{MODULE_META.get(m,{}).get("color","#64748b")}20;'
            f'color:{MODULE_META.get(m,{}).get("color","#64748b")}">'
            f'{MODULE_META.get(m,{}).get("icon","")} {MODULE_META.get(m,{}).get("label",m)}</span>'
            for m in ins.get("modules", [])
        )
        blocks.append(f"""
        <article class="cross-card">
          <div class="cross-card-head">
            <span class="cross-impact" style="background:{sev['bg']};color:{sev['color']}">영향도 {sev['label']}</span>
            <div class="mod-chips">{mod_chips}</div>
          </div>
          <h4>{esc(ins.get('title',''))}</h4>
          <p>{esc(ins.get('detail',''))}</p>
        </article>""")
    return "".join(blocks)


def _strength_risk_html(strengths: list[dict], risks: list[dict]) -> str:
    s_blocks = []
    for s in strengths or []:
        mod = MODULE_META.get(s.get("module", "cross"), MODULE_META["cross"])
        s_blocks.append(f"""
        <div class="sr-item good">
          <span class="sr-tag" style="color:{mod['color']}">{mod['icon']} {mod['label']}</span>
          <b>{esc(s.get('title',''))}</b>
          <p>{esc(s.get('detail',''))}</p>
        </div>""")

    r_blocks = []
    order = {"high": 0, "medium": 1, "low": 2}
    risks_sorted = sorted(risks or [], key=lambda r: order.get(r.get("severity", "low"), 3))
    for r in risks_sorted:
        sev = SEVERITY_META.get(r.get("severity", "medium"), SEVERITY_META["medium"])
        mod = MODULE_META.get(r.get("module", "cross"), MODULE_META["cross"])
        r_blocks.append(f"""
        <div class="sr-item risk" style="border-left-color:{sev['color']}">
          <div class="sr-item-top">
            <span class="sr-tag" style="color:{mod['color']}">{mod['icon']} {mod['label']}</span>
            <em class="sev-badge" style="background:{sev['bg']};color:{sev['color']}">위험도 {sev['label']}</em>
          </div>
          <b>{esc(r.get('title',''))}</b>
          <p>{esc(r.get('detail',''))}</p>
          <p class="evidence">근거: {esc(r.get('evidence',''))}</p>
        </div>""")

    return f"""
    <div class="sr-grid">
      <div class="sr-col">
        <h4 class="sr-col-title good">✅ 핵심 강점</h4>
        {''.join(s_blocks) or '<p class="empty">감지된 강점이 없습니다.</p>'}
      </div>
      <div class="sr-col">
        <h4 class="sr-col-title risk">⚠️ 핵심 리스크</h4>
        {''.join(r_blocks) or '<p class="empty">감지된 리스크가 없습니다.</p>'}
      </div>
    </div>"""


def _module_dive_html(module_deep_dive: dict, parsed_map: dict[str, ParsedReport]) -> str:
    sections = []
    for key in ["finance", "office", "claims", "hr"]:
        meta = MODULE_META[key]
        dd = (module_deep_dive or {}).get(key, {})
        summary = dd.get("summary", "")
        findings = dd.get("key_findings", []) or []
        actions = dd.get("recommended_actions", []) or []
        pr = parsed_map.get(key)

        if not pr and not summary:
            continue  # 업로드되지 않았고 AI도 언급하지 않았으면 섹션 생략

        source_chip = (
            f'<span class="src-chip">원본: {esc(pr.source_filename)}</span>' if pr else
            '<span class="src-chip muted">업로드되지 않음</span>'
        )
        kpi_chips = ""
        if pr and pr.quick_kpis:
            kpi_chips = "".join(
                f'<span class="qk-chip"><b>{esc(v)}</b><small>{esc(k)}</small></span>'
                for k, v in pr.quick_kpis.items()
            )

        findings_html = "".join(f"<li>{esc(f)}</li>" for f in findings)
        actions_html = "".join(f"<li>{esc(a)}</li>" for a in actions)

        sections.append(f"""
        <section class="module-card" style="--mcolor:{meta['color']}">
          <div class="module-head">
            <div class="module-title"><span class="module-icon">{meta['icon']}</span><h3>{meta['label']}</h3></div>
            {source_chip}
          </div>
          {f'<div class="qk-row">{kpi_chips}</div>' if kpi_chips else ''}
          <p class="module-summary">{esc(summary) or '데이터가 제공되지 않았습니다.'}</p>
          <div class="module-split">
            <div>
              <h5>주요 발견사항</h5>
              <ul class="dot-list">{findings_html or '<li class="muted">-</li>'}</ul>
            </div>
            <div>
              <h5>권장 조치</h5>
              <ul class="check-list">{actions_html or '<li class="muted">-</li>'}</ul>
            </div>
          </div>
        </section>""")
    return "".join(sections)


def _roadmap_html(roadmap: list[dict]) -> str:
    icons = {"즉시": "🚨", "1주 이내": "📅", "1개월 이내": "🗓️", "다음 분기": "📈"}
    rows = []
    for r in roadmap or []:
        tf = r.get("timeframe", "")
        icon = icons.get(tf, "▶")
        items = "".join(f"<li>{esc(i)}</li>" for i in r.get("items", []))
        rows.append(f"""
        <div class="road-col">
          <div class="road-col-head">{icon} {esc(tf)}</div>
          <ul>{items}</ul>
        </div>""")
    return f'<div class="road-grid">{"".join(rows)}</div>'


def _checkpoints_html(items: list[str]) -> str:
    lis = "".join(f'<li><span class="chk-box">✓</span>{esc(i)}</li>' for i in items or [])
    return f'<ul class="checkpoint-list">{lis}</ul>'


def build_html_report(
    ai_data: dict,
    parsed_reports: list[ParsedReport],
    hospital_name: str,
    period_label: str,
    model_used: str,
    consultant_name: str = "",
    generated_at: datetime | None = None,
) -> str:
    generated_at = generated_at or datetime.now()
    parsed_map = {pr.report_type: pr for pr in parsed_reports if pr.report_type in MODULE_META}

    score = ai_data.get("hospital_health_score", 0)
    grade = ai_data.get("health_grade", "보통")
    grade_color = GRADE_COLOR.get(grade, "#2867b2")
    headline = ai_data.get("headline", "")
    exec_summary = ai_data.get("executive_summary", "")

    kpi_html = _kpi_snapshot_html(ai_data.get("kpi_snapshot", []))
    cross_html = _cross_insights_html(ai_data.get("cross_module_insights", []))
    sr_html = _strength_risk_html(ai_data.get("strengths", []), ai_data.get("risks", []))
    modules_html = _module_dive_html(ai_data.get("module_deep_dive", {}), parsed_map)
    roadmap_html = _roadmap_html(ai_data.get("action_roadmap", []))
    checkpoints_html = _checkpoints_html(ai_data.get("next_month_checkpoints", []))

    source_badges = "".join(
        f'<span class="source-badge">{MODULE_META.get(pr.report_type, {}).get("icon","📄")} '
        f'{esc(pr.label)}</span>'
        for pr in parsed_reports
    )

    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(hospital_name)} AI 경영 브리핑 · MEDIUM</title>
<style>
{_CSS}
</style>
</head>
<body>
<div class="ai-brief-wrap" id="aiBriefRoot">

  <header class="brief-cover">
    <div class="brief-cover-bg"></div>
    <div class="cover-inner">
      <div class="cover-top">
        <div class="brand">
          <span class="brand-mark">MEDIUM</span><span class="brand-sub">GUIDE · AI BRIEFING</span>
        </div>
        <span class="premium-ribbon">PREMIUM AI REPORT</span>
      </div>
      <h1>AI 경영 브리핑</h1>
      <p class="cover-sub">{esc(hospital_name) or '병원'} · {esc(period_label) or '분석 기간 미지정'}</p>
      <div class="cover-meta">
        <span>생성일 {generated_at.strftime('%Y.%m.%d %H:%M')}</span>
        <span>분석 엔진 : {ENGINE_DISPLAY_NAME}</span>
        {f'<span>담당 컨설턴트 {esc(consultant_name)}</span>' if consultant_name else ''}
      </div>
      <div class="source-badges">{source_badges}</div>
    </div>
  </header>

  <div class="brief-toolbar no-print">
    <button type="button" class="toolbar-btn pdf" onclick="medBriefSavePDF()">🖨️ PDF로 저장</button>
    <button type="button" class="toolbar-btn jpg" id="medBriefJpgBtn" onclick="medBriefSaveJPG()">🖼️ JPG로 저장</button>
  </div>

  <section class="brief-hero-grid">
    <article class="hero-score-card">
      {_donut_svg(score, grade)}
      <span class="grade-pill" style="background:{grade_color}20;color:{grade_color}">{esc(grade)}</span>
      <p class="hero-score-label">AI 종합 경영건전성 점수</p>
    </article>
    <article class="hero-summary-card">
      <span class="eyebrow">EXECUTIVE HEADLINE</span>
      <h2>{esc(headline)}</h2>
      <p>{esc(exec_summary)}</p>
    </article>
  </section>

  <section class="brief-section">
    <h3 class="section-title"><span class="num">01</span>핵심 지표 스냅샷</h3>
    {kpi_html}
  </section>

  <section class="brief-section">
    <h3 class="section-title"><span class="num">02</span>AI 교차 분석 인사이트
      <span class="section-desc">4개 시스템 데이터를 함께 볼 때만 드러나는 통찰</span>
    </h3>
    <div class="cross-grid">{cross_html or '<p class="empty">교차 인사이트가 생성되지 않았습니다.</p>'}</div>
  </section>

  <section class="brief-section">
    <h3 class="section-title"><span class="num">03</span>강점 &amp; 리스크 진단</h3>
    {sr_html}
  </section>

  <section class="brief-section">
    <h3 class="section-title"><span class="num">04</span>시스템별 심층 분석</h3>
    <div class="module-grid">{modules_html}</div>
  </section>

  <section class="brief-section">
    <h3 class="section-title"><span class="num">05</span>실행 로드맵</h3>
    {roadmap_html}
  </section>

  <section class="brief-section">
    <h3 class="section-title"><span class="num">06</span>다음 브리핑 체크포인트</h3>
    {checkpoints_html}
  </section>

  <footer class="brief-footer">
    <p>본 보고서는 MEDIUM GUIDE AI 경영 브리핑 시스템이 업로드된 원무통계 · 심사평가 · 인력관리 ·
      재무제표 데이터를 기반으로 자동 생성한 유료 컨설팅 산출물입니다. 실제 경영 의사결정 전
      원자료와 함께 검토하시기 바랍니다.</p>
    <p class="copyright">ⓒ MEDIUM Co. · 무단 전재 및 재배포를 금지합니다 · 분석 엔진 : {ENGINE_DISPLAY_NAME}</p>
  </footer>

</div>

<script>
{_load_html2canvas_js()}
</script>
<script>
(function () {{
  var FILE_BASE = {_js_str(f"AI경영브리핑_{hospital_name or '병원'}_{generated_at.strftime('%Y%m%d')}")};

  window.medBriefSavePDF = function () {{
    window.print();
  }};

  window.medBriefSaveJPG = function () {{
    var target = document.getElementById('aiBriefRoot');
    var btn = document.getElementById('medBriefJpgBtn');
    var toolbar = document.querySelector('.brief-toolbar');
    if (typeof html2canvas === 'undefined') {{
      alert('JPG 저장 모듈을 불러오지 못했습니다. 인터넷 연결 상태를 확인하거나 PDF로 저장을 이용해주세요.');
      return;
    }}
    var originalText = btn ? btn.textContent : '';
    if (btn) {{ btn.textContent = '⏳ 저장 중...'; btn.disabled = true; }}
    if (toolbar) toolbar.style.visibility = 'hidden';
    html2canvas(target, {{ scale: 2, useCORS: true, backgroundColor: '#eef2f5' }}).then(function (canvas) {{
      if (toolbar) toolbar.style.visibility = 'visible';
      if (btn) {{ btn.textContent = originalText; btn.disabled = false; }}
      var link = document.createElement('a');
      link.download = FILE_BASE + '.jpg';
      link.href = canvas.toDataURL('image/jpeg', 0.95);
      link.click();
    }}).catch(function (err) {{
      if (toolbar) toolbar.style.visibility = 'visible';
      if (btn) {{ btn.textContent = originalText; btn.disabled = false; }}
      alert('JPG 저장 중 오류가 발생했습니다: ' + err);
    }});
  }};
}})();
</script>
</body>
</html>"""


_CSS = """
@page { size: A4; margin: 14mm; }
* { box-sizing: border-box; }
body {
  margin: 0; background: #eef2f5; color: #0b1f33;
  font-family: Pretendard, 'Noto Sans KR', 'Malgun Gothic', Arial, sans-serif;
  font-size: 13px; line-height: 1.62;
}
.ai-brief-wrap { max-width: 1320px; width: 96%; margin: 0 auto; padding: 22px 0 46px; }

/* ---------- Floating toolbar (PDF/JPG 저장) ---------- */
.brief-toolbar {
  display: flex; justify-content: flex-end; gap: 8px; margin: 10px 0 4px;
}
.toolbar-btn {
  font-family: inherit; font-size: 12.5px; font-weight: 800; color: #0b1f33;
  background: #fff; border: 1px solid #d8e3e5; border-radius: 999px; padding: 8px 16px;
  cursor: pointer; box-shadow: 0 6px 16px rgba(11,31,51,.08); transition: transform .12s ease;
}
.toolbar-btn:hover { transform: translateY(-1px); }
.toolbar-btn.pdf { border-color: #0f6e63; color: #0f6e63; }
.toolbar-btn.jpg { border-color: #b8860b; color: #8a6408; }
.toolbar-btn:disabled { opacity: .6; cursor: progress; transform: none; }

/* ---------- Cover ---------- */
.brief-cover {
  position: relative; overflow: hidden; border-radius: 18px;
  background: linear-gradient(135deg,#061a2e 0%,#0a3a52 45%,#0f6e63 100%);
  color: #fff; padding: 40px 38px 34px; box-shadow: 0 24px 60px rgba(6,26,46,.35);
}
.brief-cover-bg {
  position: absolute; inset: 0; opacity: .5; pointer-events: none;
  background:
    radial-gradient(circle at 85% 10%, rgba(212,175,55,.35), transparent 45%),
    radial-gradient(circle at 10% 90%, rgba(15,154,140,.45), transparent 50%);
}
.cover-inner { position: relative; z-index: 1; }
.cover-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 22px; }
.brand-mark { font-weight: 900; font-size: 15px; letter-spacing: .12em; }
.brand-sub { margin-left: 8px; font-size: 10px; color: #bfe9e2; letter-spacing: .1em; }
.premium-ribbon {
  font-size: 10px; font-weight: 900; letter-spacing: .08em; color: #1c1204;
  background: linear-gradient(90deg,#f6d98a,#d4af37); padding: 6px 12px; border-radius: 999px;
}
.brief-cover h1 { font-size: 34px; margin: 4px 0 6px; letter-spacing: -.5px; }
.cover-sub { margin: 0 0 16px; color: #d7f3ee; font-size: 14px; font-weight: 600; }
.cover-meta { display: flex; gap: 18px; flex-wrap: wrap; font-size: 11.5px; color: #b9d8d2; margin-bottom: 16px; }
.source-badges { display: flex; gap: 8px; flex-wrap: wrap; }
.source-badge {
  font-size: 11px; font-weight: 700; background: rgba(255,255,255,.14);
  border: 1px solid rgba(255,255,255,.25); padding: 5px 11px; border-radius: 999px;
}

/* ---------- Hero grid ---------- */
.brief-hero-grid { display: grid; grid-template-columns: 240px 1fr; gap: 14px; margin: 16px 0; }
.hero-score-card, .hero-summary-card {
  background: #fff; border: 1px solid #dde7ea; border-radius: 14px;
  box-shadow: 0 10px 30px rgba(11,31,51,.06);
}
.hero-score-card {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 18px; gap: 8px;
}
.grade-pill { font-weight: 900; font-size: 13px; padding: 5px 16px; border-radius: 999px; }
.hero-score-label { margin: 2px 0 0; font-size: 11.5px; color: #64748b; font-weight: 700; }
.hero-summary-card { padding: 24px 26px; display: flex; flex-direction: column; justify-content: center; }
.eyebrow { font-size: 10.5px; font-weight: 900; letter-spacing: .12em; color: #b8860b; }
.hero-summary-card h2 { margin: 8px 0 10px; font-size: 21px; color: #0b1f33; letter-spacing: -.3px; }
.hero-summary-card p { margin: 0; color: #3a4a58; font-size: 13.5px; }

/* ---------- Sections ---------- */
.brief-section { margin: 26px 0; }
.section-title {
  display: flex; align-items: baseline; gap: 10px; font-size: 17px; font-weight: 900;
  color: #0b1f33; border-bottom: 2px solid #0f6e63; padding-bottom: 9px; margin-bottom: 14px;
}
.section-title .num {
  font-size: 12px; background: #0b1f33; color: #fff; border-radius: 6px; padding: 3px 7px;
}
.section-desc { font-size: 11.5px; font-weight: 600; color: #94a3b8; margin-left: auto; }

/* ---------- KPI grid ---------- */
.kpi-grid { display: grid; grid-template-columns: repeat(4,1fr); gap: 10px; }
.kpi-card {
  background: #fff; border: 1px solid #e2eaec; border-left: 4px solid #0f9a8c; border-radius: 10px;
  padding: 13px 14px; box-shadow: 0 6px 16px rgba(11,31,51,.04); position: relative;
}
.kpi-card small { display: block; color: #64748b; font-weight: 700; font-size: 11px; }
.kpi-card b { display: block; font-size: 19px; color: #0b1f33; margin: 4px 0 2px; }
.kpi-trend { font-size: 11px; font-weight: 700; }
.kpi-badge {
  position: absolute; top: 10px; right: 10px; font-size: 9.5px; font-weight: 900;
  padding: 2px 7px; border-radius: 999px;
}

/* ---------- Cross insights ---------- */
.cross-grid { display: grid; grid-template-columns: repeat(2,1fr); gap: 12px; }
.cross-card {
  background: linear-gradient(180deg,#fff,#f7fbfa); border: 1px solid #dcecea; border-radius: 12px;
  padding: 16px 18px; box-shadow: 0 8px 22px rgba(11,31,51,.05);
}
.cross-card-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.cross-impact { font-size: 10.5px; font-weight: 900; padding: 3px 9px; border-radius: 999px; }
.mod-chips { display: flex; gap: 5px; flex-wrap: wrap; }
.mod-chip { font-size: 10px; font-weight: 800; padding: 3px 8px; border-radius: 999px; }
.cross-card h4 { margin: 0 0 6px; font-size: 14.5px; color: #0b1f33; }
.cross-card p { margin: 0; color: #45566a; font-size: 12.5px; }

/* ---------- Strength / Risk ---------- */
.sr-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.sr-col-title { font-size: 13.5px; margin: 0 0 10px; }
.sr-col-title.good { color: #0f9a8c; }
.sr-col-title.risk { color: #c0392b; }
.sr-item {
  background: #fff; border: 1px solid #e6eef0; border-left: 4px solid #0f9a8c; border-radius: 10px;
  padding: 12px 14px; margin-bottom: 10px; box-shadow: 0 4px 12px rgba(11,31,51,.03);
}
.sr-item.risk { border-left-color: #c0392b; }
.sr-item-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
.sr-tag { font-size: 10.5px; font-weight: 900; }
.sev-badge { font-size: 9.5px; font-weight: 900; padding: 2px 7px; border-radius: 999px; }
.sr-item b { display: block; font-size: 13px; color: #0b1f33; margin: 3px 0; }
.sr-item p { margin: 2px 0 0; color: #4b5b6a; font-size: 12px; }
.sr-item p.evidence { color: #8592a0; font-size: 11px; font-style: normal; margin-top: 4px; }

/* ---------- Module deep dive ---------- */
.module-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.module-card {
  background: #fff; border: 1px solid #e2eaec; border-top: 4px solid var(--mcolor,#0f9a8c);
  border-radius: 12px; padding: 18px 20px; box-shadow: 0 10px 26px rgba(11,31,51,.05);
}
.module-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.module-title { display: flex; align-items: center; gap: 8px; }
.module-icon { font-size: 18px; }
.module-title h3 { margin: 0; font-size: 15.5px; color: #0b1f33; }
.src-chip { font-size: 10px; font-weight: 700; color: #64748b; background: #f1f5f7; padding: 4px 9px; border-radius: 999px; }
.src-chip.muted { color: #b0bac2; }
.qk-row { display: flex; gap: 8px; flex-wrap: wrap; margin: 6px 0 10px; }
.qk-chip { background: #f6faf9; border: 1px solid #e2eeec; border-radius: 8px; padding: 6px 10px; text-align: center; }
.qk-chip b { display: block; font-size: 13px; color: #0b1f33; }
.qk-chip small { display: block; font-size: 9.5px; color: #7c8b98; }
.module-summary { color: #3a4a58; font-size: 12.5px; margin: 4px 0 12px; }
.module-split { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.module-split h5 { margin: 0 0 6px; font-size: 11.5px; color: #64748b; letter-spacing: .03em; }
.dot-list, .check-list { margin: 0; padding-left: 0; list-style: none; }
.dot-list li { padding-left: 14px; position: relative; margin-bottom: 5px; font-size: 12px; color: #33424f; }
.dot-list li::before { content: ""; position: absolute; left: 0; top: 6px; width: 5px; height: 5px; border-radius: 50%; background: var(--mcolor,#0f9a8c); }
.check-list li { padding-left: 18px; position: relative; margin-bottom: 5px; font-size: 12px; color: #33424f; }
.check-list li::before { content: "✔"; position: absolute; left: 0; top: 0; font-size: 10px; color: var(--mcolor,#0f9a8c); }
li.muted { color: #b0bac2; }

/* ---------- Roadmap ---------- */
.road-grid { display: grid; grid-template-columns: repeat(4,1fr); gap: 10px; }
.road-col { background: #fff; border: 1px solid #e2eaec; border-radius: 12px; overflow: hidden; box-shadow: 0 8px 20px rgba(11,31,51,.04); }
.road-col-head { background: #0b1f33; color: #fff; font-weight: 900; font-size: 12px; padding: 10px 12px; }
.road-col ul { margin: 0; padding: 12px 16px; list-style: disc; }
.road-col li { font-size: 11.8px; color: #33424f; margin-bottom: 6px; }

/* ---------- Checkpoints ---------- */
.checkpoint-list { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.checkpoint-list li {
  display: flex; align-items: center; gap: 9px; background: #fff; border: 1px solid #e2eaec;
  border-radius: 10px; padding: 10px 13px; font-size: 12.5px; color: #33424f;
}
.chk-box {
  width: 18px; height: 18px; border-radius: 5px; background: #0f9a8c; color: #fff; font-size: 11px;
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}

/* ---------- Footer ---------- */
.brief-footer { margin-top: 34px; border-top: 1px solid #dde7ea; padding-top: 14px; color: #7c8b98; font-size: 11px; }
.brief-footer .copyright { margin-top: 4px; font-weight: 700; color: #94a3b8; }
.empty { color: #94a3b8; font-size: 12px; }

@media print {
  body { background: #fff; }
  .ai-brief-wrap { max-width: 100%; width: 100%; padding: 0; }
  .brief-cover { box-shadow: none; }
  .no-print, .brief-toolbar { display: none !important; }
  .kpi-grid, .cross-grid, .sr-grid, .module-grid, .road-grid { break-inside: avoid; }
  .module-card, .cross-card, .sr-item { break-inside: avoid; }
}
@media (max-width: 800px) {
  .brief-hero-grid, .sr-grid, .module-grid, .cross-grid { grid-template-columns: 1fr; }
  .kpi-grid { grid-template-columns: repeat(2,1fr); }
  .road-grid { grid-template-columns: 1fr 1fr; }
  .checkpoint-list { grid-template-columns: 1fr; }
  .brief-toolbar { justify-content: center; }
}
"""
