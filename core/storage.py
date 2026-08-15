# -*- coding: utf-8 -*-
"""
core/storage.py
────────────────────────────────────────────────────────────────
생성된 AI 경영 브리핑을 로컬 파일 시스템에 보관하는 경량 저장소.
(별도 DB 없이도 바로 배포 가능하도록 JSON 인덱스 + HTML 파일 방식 사용.
 추후 Supabase 등으로 교체하고 싶다면 이 모듈의 함수 시그니처만 유지하면 됨.)
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "briefings"
INDEX_FILE = DATA_DIR / "index.json"


@dataclass
class BriefingRecord:
    id: str
    hospital_name: str
    period_label: str
    health_score: int
    health_grade: str
    headline: str
    model_used: str
    created_at: str
    filename: str


def _ensure_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not INDEX_FILE.exists():
        INDEX_FILE.write_text("[]", encoding="utf-8")


def _load_index() -> list[dict]:
    _ensure_dirs()
    try:
        return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_index(records: list[dict]):
    _ensure_dirs()
    INDEX_FILE.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


def save_briefing(html_content: str, hospital_name: str, period_label: str, ai_data: dict, model_used: str) -> BriefingRecord:
    _ensure_dirs()
    rec_id = uuid.uuid4().hex[:10]
    safe_name = (hospital_name or "briefing").replace(" ", "_")
    filename = f"{rec_id}_{safe_name}.html"
    (DATA_DIR / filename).write_text(html_content, encoding="utf-8")

    record = BriefingRecord(
        id=rec_id,
        hospital_name=hospital_name or "미지정",
        period_label=period_label or "",
        health_score=int(ai_data.get("hospital_health_score", 0)),
        health_grade=ai_data.get("health_grade", ""),
        headline=ai_data.get("headline", ""),
        model_used=model_used,
        created_at=datetime.now().isoformat(timespec="seconds"),
        filename=filename,
    )
    records = _load_index()
    records.insert(0, asdict(record))
    _save_index(records)
    return record


def list_briefings() -> list[dict]:
    return _load_index()


def load_briefing_html(filename: str) -> str | None:
    path = DATA_DIR / filename
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def delete_briefing(rec_id: str) -> bool:
    records = _load_index()
    target = next((r for r in records if r["id"] == rec_id), None)
    if not target:
        return False
    path = DATA_DIR / target["filename"]
    if path.exists():
        path.unlink()
    records = [r for r in records if r["id"] != rec_id]
    _save_index(records)
    return True
