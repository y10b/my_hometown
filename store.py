"""중복 알림 방지용 상태 저장 (간단한 JSON 파일).

두 종류의 알림을 따로 추적한다.
  - seen_new      : '신규 공고' 알림을 이미 보낸 공고 uid
  - seen_closing  : '마감 임박' 알림을 이미 보낸 공고 uid
"""
from __future__ import annotations

import json
import os

DEFAULT_PATH = "state.json"


def load(path: str = DEFAULT_PATH) -> dict:
    if not os.path.exists(path):
        return {"seen_new": [], "seen_closing": []}
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    d.setdefault("seen_new", [])
    d.setdefault("seen_closing", [])
    return d


def save(state: dict, path: str = DEFAULT_PATH) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
