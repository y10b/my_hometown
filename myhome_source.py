"""마이홈포털 공공주택 모집공고 통합 어댑터 (SH/GH/민간 + 지자체 도시공사).

국토교통부_마이홈포털 공공주택 모집공고 조회 서비스
  data.go.kr/data/15108420  (REST/JSON, 무료, 자동승인, org=1613000)
  → 공공임대 + 공공지원 민간임대를 '통합' 제공 (LH 외 SH·GH·민간을 한 번에).

LH는 전용 API(lh_source + supply + detail)가 더 풍부하므로 그대로 두고,
이 어댑터는 LH 외 공급기관(SH/GH/민간)만 보강하는 용도로 쓴다.

⚠️ 미완성: 아래 ENDPOINT/필드명은 '활용신청 후 참고문서(요청 파라미터 코드 xlsx)'로
   확정해야 한다. 값이 비어있으면 fetch()는 즉시 빈 목록을 반환(다른 소스에 영향 없음).
   참고문서 확보 후 ENDPOINT 와 FIELD 매핑만 채우면 동작한다.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

from model import Notice, _parse_date

# TODO(가이드): 정확한 오퍼레이션 경로 확정 (예: https://apis.data.go.kr/1613000/HWSPR0X/...)
ENDPOINT = ""

# TODO(가이드): 참고문서의 실제 응답 필드명으로 교체
FIELD = {
    "notice_id": "panId",        # 공고 고유 id
    "title": "panNm",            # 공고명
    "supplier": "suplyInsttNm",  # 공급기관 (LH/SH/GH/민간 구분)
    "house_type": "houseTyNm",   # 주택유형 (행복주택 구분)
    "region": "brtcNm",          # 지역(시도)
    "accept_start": "rceptBgnde",
    "accept_close": "rceptEndde",
    "status": "panSttusNm",      # 공고상태
    "supply_units": "suplyHshldco",  # 공급세대수
    "url": "panUrl",             # 상세링크
}


def _g(row: dict, key: str):
    return row.get(FIELD[key])


def normalize(row: dict) -> Notice:
    supplier = (_g(row, "supplier") or "").strip()
    src = supplier or "MYHOME"
    units = None
    try:
        units = int(str(_g(row, "supply_units")).replace(",", ""))
    except (TypeError, ValueError):
        pass
    return Notice(
        source=src,
        notice_id=str(_g(row, "notice_id") or "").strip(),
        title=(_g(row, "title") or "").strip(),
        region=(_g(row, "region") or "").strip(),
        house_type=(_g(row, "house_type") or "").strip(),
        status=(_g(row, "status") or "").strip(),
        close_date=_parse_date(_g(row, "accept_close")),
        post_date=_parse_date(_g(row, "accept_start")),
        url=(_g(row, "url") or "").strip(),
        supply_units=units,
    )


def fetch_notices(service_key: str, *, page_size: int = 100, timeout: int = 25,
                  exclude_suppliers: tuple[str, ...] = ("LH",)) -> list[Notice]:
    """마이홈 통합 공고를 가져와 Notice 목록으로. LH는 전용 어댑터가 처리하므로 기본 제외."""
    if not ENDPOINT:
        return []  # 아직 미설정 → 다른 소스에 영향 없이 조용히 건너뜀
    params = {
        "serviceKey": service_key,
        "numOfRows": str(page_size),
        "pageNo": "1",
        "type": "json",
    }
    url = ENDPOINT + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")

    # TODO(가이드): 실제 응답 구조에 맞춰 rows 추출 경로 확정
    data = json.loads(raw)
    rows = (data.get("response", {}).get("body", {}).get("items", {}) or {})
    if isinstance(rows, dict):
        rows = rows.get("item", [])
    if isinstance(rows, dict):
        rows = [rows]

    notices = [normalize(r) for r in rows]
    return [n for n in notices if n.source not in exclude_suppliers]
