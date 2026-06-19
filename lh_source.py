"""LH 분양임대공고문 조회 어댑터.

공공데이터포털 '한국토지주택공사_분양임대공고문 조회 서비스' (lhLeaseNoticeInfo1)
- 엔드포인트: https://apis.data.go.kr/B552555/lhLeaseNoticeInfo1/lhLeaseNoticeInfo1
- REST GET / JSON / serviceKey 인증 / 30 tps

이 어댑터는 '공고 단위' 메타데이터(공고명/지역/유형/마감일/상세링크)를 가져온다.
세대별 '공급 호수'는 이 API에 없고, 같은 PAN_ID로 '분양임대공고별 공급정보 조회' API를
따로 호출해야 한다(supply.py 참고).
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

BASE_URL = "https://apis.data.go.kr/B552555/lhLeaseNoticeInfo1/lhLeaseNoticeInfo1"

# 행복주택이 걸쳐 있는 상위 공고유형코드 (UPP_AIS_TP_CD)
#   06 = 임대주택  → "행복주택"
#   39 = 신혼희망타운 → "행복주택(신혼희망)"
HAPPY_HOUSE_UPP_CODES = ["06", "39"]


def _parse_response(raw: str) -> list[dict]:
    """data.go.kr 응답(블록 리스트)에서 dsList(공고 목록)만 뽑아낸다."""
    data = json.loads(raw)
    rows: list[dict] = []
    for block in data:
        if isinstance(block, dict) and "dsList" in block:
            rows = block["dsList"] or []
    return rows


def fetch_notices(service_key: str, *, page_size: int = 100,
                  lookback_days: int = 60, timeout: int = 25) -> list[dict]:
    """행복주택이 포함된 상위유형(06, 39)을 모두 조회해 원본(raw) 공고 목록을 반환."""
    today = datetime.now()
    start = (today - timedelta(days=lookback_days)).strftime("%Y%m%d")
    end = today.strftime("%Y%m%d")

    all_rows: list[dict] = []
    for upp in HAPPY_HOUSE_UPP_CODES:
        params = {
            "serviceKey": service_key,
            "PG_SZ": str(page_size),
            "PAGE": "1",
            "UPP_AIS_TP_CD": upp,
            "PAN_ST_DT": start,
            "PAN_ED_DT": end,
        }
        url = BASE_URL + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
        all_rows.extend(_parse_response(raw))
    return all_rows


def load_sample(path: str = "sample_response.json") -> list[dict]:
    """오프라인 검증용 — 가이드 샘플 응답을 그대로 읽어 dsList를 반환."""
    with open(path, encoding="utf-8") as f:
        return _parse_response(f.read())
