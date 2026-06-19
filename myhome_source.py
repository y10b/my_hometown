"""마이홈포털 공공주택 모집공고 통합 어댑터 (SH/GH/민간 + 지자체 도시공사).

국토교통부_마이홈포털 공공주택 모집공고 조회 서비스 (data.go.kr/15108420, org 1613000)
  GET https://apis.data.go.kr/1613000/HWSPR02/rsdtRcritNtcList
  → 공공임대 + 공공지원 민간임대를 '통합' 제공. 한 번의 호출로 LH/SH/GH/지자체/민간을 모두 준다.

LH는 전용 API(lh_source+supply+detail)가 전용면적(평수)까지 줘서 더 풍부하므로,
이 어댑터는 기본적으로 LH를 제외하고 그 외 공급기관(SH/GH/민간/지자체)만 보강한다.

응답 1행 = 한 공고의 한 주택형(houseSn). 같은 공고(pblancId)+공급유형(suplyTyNm)을 묶어
공급호수(sumSuplyCo)를 합산한다.

이 API는 접수 '상태' 필드가 공급구분(일반/우선공급)이라, 접수중 여부는 접수기간(beginDe~endDe)으로 직접 판정한다.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import date

from model import Notice, _parse_date

ENDPOINT = "https://apis.data.go.kr/1613000/HWSPR02/rsdtRcritNtcList"


def _to_int(v) -> int | None:
    try:
        return int(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _derive_status(begin: date | None, close: date | None, today: date) -> str:
    """접수기간으로 상태를 판정 (API가 접수상태를 안 줌)."""
    if close and today > close:
        return "접수마감"
    if begin and close and begin <= today <= close:
        return "접수중"
    if begin and today < begin:
        return "공고중"
    return "접수중" if close and today <= close else "접수마감"


def _fetch_raw(service_key: str, page_size: int, timeout: int) -> list[dict]:
    params = {"serviceKey": service_key, "numOfRows": str(page_size),
              "pageNo": "1", "type": "json"}
    url = ENDPOINT + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    body = data.get("response", {}).get("body", {})
    items = body.get("item", []) or []
    return [items] if isinstance(items, dict) else items


def fetch_notices(service_key: str, *, page_size: int = 500, timeout: int = 30,
                  exclude_suppliers: tuple[str, ...] = ("LH",),
                  today: date | None = None) -> list[Notice]:
    """마이홈 통합 공고 → Notice 목록. LH는 기본 제외(전용 어댑터가 처리)."""
    today = today or date.today()
    rows = _fetch_raw(service_key, page_size, timeout)

    # (공고, 공급유형) 단위로 묶어 공급호수 합산
    groups: dict[tuple, dict] = {}
    for r in rows:
        inst = (r.get("suplyInsttNm") or "").strip()
        if inst in exclude_suppliers:
            continue
        key = (r.get("pblancId"), r.get("suplyTyNm"))
        g = groups.get(key)
        units = _to_int(r.get("sumSuplyCo")) or 0
        if g is None:
            groups[key] = {"row": r, "inst": inst, "units": units}
        else:
            g["units"] += units

    out = []
    for (pblanc_id, suply_ty), g in groups.items():
        r = g["row"]
        begin = _parse_date(r.get("beginDe"))
        close = _parse_date(r.get("endDe"))
        region = " ".join(x for x in [(r.get("brtcNm") or "").strip(),
                                      (r.get("signguNm") or "").strip()] if x)
        n = Notice(
            source=g["inst"] or "MYHOME",
            notice_id=f"{pblanc_id}-{suply_ty}",
            title=(r.get("pblancNm") or "").strip(),
            region=region,
            house_type=(suply_ty or "").strip(),
            status=_derive_status(begin, close, today),
            close_date=close,
            post_date=begin,
            url=(r.get("url") or r.get("pcUrl") or "").strip(),
            supply_units=g["units"] or None,
        )
        dep = _to_int(r.get("rentGtn"))
        rent = _to_int(r.get("mtRntchrg"))
        if dep:
            n.extra["deposit"] = dep
        if rent:
            n.extra["rent"] = rent
        out.append(n)
    return out
