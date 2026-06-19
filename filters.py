"""당첨 전략 필터.

사용자 전략:
  1) 행복주택만 본다.
  2) 공급 5호 이하는 제외(당첨 확률 급락).
  3) 10호 이상은 '첫 입주 신축' 신호 → 우선 태그.
  4) 실시간 경쟁률은 공개 안 되므로, 공급 호수가 많을수록 유리 → 호수 내림차순 랭킹.
  5) 막판 접수 전략 → 마감 임박(D-day~D-n) 공고를 따로 알림.

주의: 공급 호수(supply_units)는 LH 공고 리스트엔 없고 공급정보 API로 채워야 한다.
값이 None(미확인)이면 '제외'하지 않고 '미확인'으로 두되 랭킹은 뒤로 보낸다.
('박스에 쌓인 옵션 사진' 첫입주 판별은 자동화 비현실적 → 사람이 링크 보고 최종 확인)
"""
from __future__ import annotations

from datetime import date, datetime

from model import Notice


def is_happy_house(n: Notice, keyword: str = "행복주택") -> bool:
    return keyword in (n.house_type or "")


def passes_supply_floor(n: Notice, min_units: int) -> bool:
    """공급 호수가 알려져 있고 하한 미만이면 제외. 미확인(None)은 통과시킨다."""
    if n.supply_units is None:
        return True
    return n.supply_units >= min_units


def is_big_supply(n: Notice, big_units: int) -> bool:
    return n.supply_units is not None and n.supply_units >= big_units


def is_closing_soon(n: Notice, within_days: int, today: date | None = None) -> bool:
    d = n.days_to_close(today)
    return d is not None and 0 <= d <= within_days


def is_closing_within_hours(n: Notice, hours: float, assumed_time: str,
                            now: datetime) -> bool:
    """마감(접수종료일+가정시각)까지 남은 시간이 hours 이내(아직 안 지남)이면 True.
    → '마감 3시간 전' 막판 알림 트리거."""
    h = n.hours_to_close(now, assumed_time)
    return h is not None and 0 < h <= hours


def prefilter(notices: list[Notice], cfg: dict,
              today: date | None = None) -> list[Notice]:
    """공급호수 조회 전에 값싼 조건(행복주택/미마감/지역)으로 먼저 좁힌다.
    → 공급정보 API를 행복주택 후보에만 호출해서 횟수를 아낀다."""
    f = cfg["filters"]
    kw = f.get("house_type_keyword", "행복주택")
    regions = f.get("regions") or []
    status_in = f.get("status_in") or []
    near_only = f.get("near_seoul_only")
    near_cities = f.get("near_seoul_cities") or []
    exclude_kw = f.get("exclude_title_keywords") or []
    exclude_ht = f.get("exclude_house_type_keywords") or []
    out = []
    for n in notices:
        if not is_happy_house(n, kw) or n.is_closed:
            continue
        if status_in and n.status not in status_in:                   # 접수중만 등
            continue
        if regions and not any(r in n.region for r in regions):
            continue
        # 서울 근교만: 서울은 전부 통과, 그 외(경기 등)는 제목에 근교 도시명 있어야 통과
        # (LH API 지역은 '경기도'까지만 줘서 시 단위는 제목으로 판별)
        if near_only and "서울" not in n.region:
            if not any(c in n.title for c in near_cities):
                continue
        if exclude_kw and any(k in n.title for k in exclude_kw):       # 예비 등 제외(신축만)
            continue
        if exclude_ht and any(k in n.house_type for k in exclude_ht):  # 신혼희망 등 유형 제외
            continue
        out.append(n)
    return out


def select_candidates(notices: list[Notice], cfg: dict,
                      today: date | None = None) -> list[Notice]:
    """전략 필터를 적용하고 '당첨 확률 높은 순'으로 정렬해 반환."""
    f = cfg["filters"]
    today = today or date.today()
    kw = f.get("house_type_keyword", "행복주택")
    min_units = f.get("min_supply_units", 6)
    regions = f.get("regions") or []

    out = []
    for n in notices:
        if not is_happy_house(n, kw):
            continue
        if n.is_closed:
            continue
        if not passes_supply_floor(n, min_units):
            continue
        if regions and not any(r in n.region for r in regions):
            continue
        out.append(n)

    # 랭킹: 공급 호수 많은 순(미확인은 -1로 뒤) → 마감 임박 순
    def sort_key(n: Notice):
        units = n.supply_units if n.supply_units is not None else -1
        dtc = n.days_to_close(today)
        dtc = dtc if dtc is not None else 9999
        return (-units, dtc)

    out.sort(key=sort_key)
    return out


def annotate(n: Notice, cfg: dict, now: datetime | None = None) -> dict:
    """알림 카드에 쓸 부가 태그. (마감임박은 '마감 N시간 전' 기준)"""
    f = cfg["filters"]
    now = now or datetime.now()
    hours = f.get("closing_alert_hours", 3)
    assumed = f.get("assumed_close_time", "18:00")
    return {
        "big_supply": is_big_supply(n, f.get("big_supply_units", 10)),
        "closing_soon": is_closing_within_hours(n, hours, assumed, now),
        "supply_unknown": n.supply_units is None,
    }
