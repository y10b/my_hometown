"""모든 공급기관(LH/SH/GH/민간)을 하나로 묶는 공통 공고 스키마.

각 소스 어댑터는 자기 응답을 Notice 로 normalize 해서 내보낸다.
필터/알림 로직은 이 공통 형식 위에서만 돈다 → 소스가 늘어도 어댑터만 추가.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from datetime import time as dtime


def _parse_date(s: str | None) -> date | None:
    """'2020.05.06' / '20200506' / '2020-05-06' 형태를 date 로."""
    if not s:
        return None
    s = s.strip()
    for fmt in ("%Y.%m.%d", "%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


@dataclass
class Notice:
    source: str            # 'LH' | 'SH' | 'GH' | 'PRIVATE'
    notice_id: str         # 소스 내 고유 공고 id (PAN_ID 등)
    title: str
    region: str
    house_type: str        # 세부유형명 (예: '행복주택', '행복주택(신혼희망)')
    status: str            # '접수중' / '공고중' / '접수마감' ...
    close_date: date | None
    post_date: date | None
    url: str
    supply_units: int | None = None   # 공급 호수 (없으면 None = 미확인)

    # 공급정보 조회 API 입력용 키 (LH 전용)
    extra: dict = field(default_factory=dict)

    @property
    def uid(self) -> str:
        """소스 전체에서 유일한 키 (중복 알림 방지용)."""
        return f"{self.source}:{self.notice_id}"

    @property
    def is_closed(self) -> bool:
        return "마감" in (self.status or "")

    def days_to_close(self, today: date | None = None) -> int | None:
        if self.close_date is None:
            return None
        today = today or date.today()
        return (self.close_date - today).days

    def close_datetime(self, assumed_time: str = "18:00") -> datetime | None:
        """마감일 + 가정 마감시각(API가 시각을 안 주므로) → datetime."""
        if self.close_date is None:
            return None
        try:
            h, m = (int(x) for x in assumed_time.split(":"))
        except ValueError:
            h, m = 18, 0
        return datetime.combine(self.close_date, dtime(h, m))

    def hours_to_close(self, now: datetime, assumed_time: str = "18:00") -> float | None:
        cd = self.close_datetime(assumed_time)
        if cd is None:
            return None
        return (cd - now).total_seconds() / 3600


def from_lh(row: dict) -> Notice:
    """LH lhLeaseNoticeInfo1 응답 row → Notice."""
    return Notice(
        source="LH",
        notice_id=str(row.get("PAN_ID", "")).strip(),
        title=(row.get("PAN_NM") or "").strip(),
        region=(row.get("CNP_CD_NM") or "").strip(),
        house_type=(row.get("AIS_TP_CD_NM") or "").strip(),
        status=(row.get("PAN_SS") or "").strip(),
        close_date=_parse_date(row.get("CLSG_DT")),
        post_date=_parse_date(row.get("PAN_NT_ST_DT")),
        url=(row.get("DTL_URL") or "").strip(),
        supply_units=None,  # 공급정보 API로 별도 enrich
        extra={
            "UPP_AIS_TP_CD": row.get("UPP_AIS_TP_CD"),
            "AIS_TP_CD": row.get("AIS_TP_CD"),
            "SPL_INF_TP_CD": row.get("SPL_INF_TP_CD"),
            "CCR_CNNT_SYS_DS_CD": row.get("CCR_CNNT_SYS_DS_CD"),
        },
    )
