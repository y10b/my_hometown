"""접수 일정 enrich — '분양임대공고별 상세정보 조회' API.

엔드포인트: https://apis.data.go.kr/B552555/lhLeaseNoticeDtlInfo1/getLeaseNoticeDtlInfo1
요청 파라미터는 공급정보 API와 동일(SPL_INF_TP_CD, CCR_CNNT_SYS_DS_CD, PAN_ID, UPP_AIS_TP_CD, AIS_TP_CD).

행복주택(063)의 공급일정 블록 dsSplScdl 에서:
  SBSC_ACP_ST_DT   접수기간시작일
  SBSC_ACP_CLSG_DT 접수기간종료일  ← '마감일'의 권위있는 값 (단, 날짜만 / 시각 없음)
  PZWR_ANC_DT      당첨자발표일

※ API가 마감 '시각'은 주지 않으므로, '마감 N시간 전' 알림은
  접수기간종료일 + config.assumed_close_time(기본 18:00)로 계산한다.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

from model import Notice, _parse_date

ENDPOINT = "https://apis.data.go.kr/B552555/lhLeaseNoticeDtlInfo1/getLeaseNoticeDtlInfo1"


def _first(data, key) -> dict | None:
    for block in data:
        if isinstance(block, dict) and key in block and block[key]:
            return block[key][0]
    return None


def parse_schedule(raw: str) -> dict:
    data = json.loads(raw)
    row = _first(data, "dsSplScdl")
    if not row:
        return {}
    return {
        "accept_start": row.get("SBSC_ACP_ST_DT"),
        "accept_close": row.get("SBSC_ACP_CLSG_DT"),
        "winner_announce": row.get("PZWR_ANC_DT"),
    }


def fetch_schedule(n: Notice, service_key: str, timeout: int = 20) -> dict:
    e = n.extra
    params = {
        "serviceKey": service_key,
        "SPL_INF_TP_CD": e.get("SPL_INF_TP_CD") or "",
        "CCR_CNNT_SYS_DS_CD": e.get("CCR_CNNT_SYS_DS_CD") or "",
        "PAN_ID": n.notice_id,
        "UPP_AIS_TP_CD": e.get("UPP_AIS_TP_CD") or "",
    }
    if e.get("AIS_TP_CD"):
        params["AIS_TP_CD"] = e["AIS_TP_CD"]
    url = ENDPOINT + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return parse_schedule(resp.read().decode("utf-8"))


def enrich(notices: list[Notice], service_key: str) -> None:
    """접수 마감일(권위값)으로 close_date 를 보정하고, 일정 정보를 extra 에 채운다."""
    for n in notices:
        if n.source != "LH":
            continue
        try:
            sch = fetch_schedule(n, service_key)
        except Exception as ex:
            n.extra["detail_error"] = repr(ex)[:120]
            continue
        close = _parse_date(sch.get("accept_close"))
        if close:                       # 접수기간종료일이 공고마감일보다 정확
            n.close_date = close
        for k in ("accept_start", "winner_announce"):
            if sch.get(k):
                n.extra[k] = sch[k]
