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
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

BASE_URL = "https://apis.data.go.kr/B552555/lhLeaseNoticeInfo1/lhLeaseNoticeInfo1"

# 우리가 보는 유형이 걸쳐 있는 상위 공고유형코드 (UPP_AIS_TP_CD)
#   06 = 임대주택   → "행복주택"(AIS_TP 10) 등
#   13 = 매입임대   → "매입임대"(AIS_TP 26) — 청년/신혼·신생아/든든전세가 제목으로만 구분됨
#   39 = 신혼희망타운 → "행복주택(신혼희망)" (현재 필터에서 제외)
# 세부 선별(행복주택 / 청년매입임대)은 filters.py 의 programs 규칙이 담당한다.
TARGET_UPP_CODES = ["06", "13", "39"]

# 하위호환 별칭 (예전 이름으로 import 하는 코드 대비)
HAPPY_HOUSE_UPP_CODES = TARGET_UPP_CODES


def _decode(body: bytes) -> str:
    """LH 응답을 견고하게 디코딩.

    정상은 UTF-8 JSON이지만, 서버 장애 시 간헐적으로 EUC-KR(CP949) 에러 응답을
    내려주며 0xc7 같은 바이트에서 UnicodeDecodeError가 난다. UTF-8 → CP949 순으로
    시도하고, 둘 다 실패하면 손상 문자를 치환해 최소한 진단은 가능하게 한다.
    """
    for enc in ("utf-8", "cp949"):
        try:
            return body.decode(enc)
        except UnicodeDecodeError:
            continue
    return body.decode("utf-8", errors="replace")


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
    """대상 상위유형(06 임대주택, 13 매입임대, 39 신혼희망)을 모두 조회해 원본 목록 반환."""
    today = datetime.now()
    start = (today - timedelta(days=lookback_days)).strftime("%Y%m%d")
    end = today.strftime("%Y%m%d")

    all_rows: list[dict] = []
    for upp in TARGET_UPP_CODES:
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
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read()
            all_rows.extend(_parse_response(_decode(body)))
        except (urllib.error.URLError, OSError, ValueError) as ex:
            # ValueError ⊇ json.JSONDecodeError. LH 일시 장애(에러 페이지/타임아웃 등)는
            # 이 요청만 건너뛰고 봇은 계속 진행 → 30분 뒤 정상 응답에서 자연 회복.
            snippet = body[:80] if "body" in dir() else b""
            print(f"[lh] UPP_AIS_TP_CD={upp} 수집 실패(건너뜀): {repr(ex)[:120]} / 본문앞: {snippet!r}")
            continue
    return all_rows


def load_sample(path: str = "sample_response.json") -> list[dict]:
    """오프라인 검증용 — 가이드 샘플 응답을 그대로 읽어 dsList를 반환."""
    with open(path, encoding="utf-8") as f:
        return _parse_response(f.read())
