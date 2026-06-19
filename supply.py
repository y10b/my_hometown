"""공급 호수 enrich — '분양임대공고별 공급정보 조회' API.

엔드포인트: https://apis.data.go.kr/B552555/lhLeaseNoticeSplInfo1/getLeaseNoticeSplInfo1
요청: serviceKey, SPL_INF_TP_CD, CCR_CNNT_SYS_DS_CD, PAN_ID, UPP_AIS_TP_CD, (AIS_TP_CD)
      → 이 값들은 공고 리스트(lhLeaseNoticeInfo1) 응답이 그대로 줌 (model.from_lh가 extra에 저장).

행복주택(SPL_INF_TP_CD=063) 등 임대주택 응답은 dsList01 에 주택형별로 한 줄씩:
  HTY_NNA(주택형) · DDO_AR(전용면적㎡) · HSH_CNT(세대수) · NOW_HSH_CNT(금회공급세대수)
  · LS_GMY(임대보증금) · RFE(월임대료) · SPL_AR(공급면적)

총 공급 호수 = Σ NOW_HSH_CNT (이번 회차 공급분).
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

from model import Notice

ENDPOINT = "https://apis.data.go.kr/B552555/lhLeaseNoticeSplInfo1/getLeaseNoticeSplInfo1"
SQM_PER_PYEONG = 3.305785


def _to_int(v) -> int | None:
    try:
        return int(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _to_float(v) -> float | None:
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def parse_supply(raw: str) -> dict:
    """공급정보 응답에서 총 공급호수 + 면적/임대조건 요약을 뽑는다."""
    data = json.loads(raw)
    rows: list[dict] = []
    for block in data:
        # 임대주택은 dsList01, 일부 유형은 dsList02/03 → 01~03 모두 훑는다
        for key in ("dsList01", "dsList02", "dsList03"):
            if isinstance(block, dict) and key in block:
                rows.extend(block[key] or [])

    total = 0
    areas: list[float] = []
    deposits: list[int] = []
    rents: list[int] = []
    for r in rows:
        now = _to_int(r.get("NOW_HSH_CNT")) or _to_int(r.get("QUP_CNT")) \
            or _to_int(r.get("HSH_CNT"))
        if now:
            total += now
        a = _to_float(r.get("DDO_AR"))
        if a:
            areas.append(a)
        d = _to_int(r.get("LS_GMY"))
        if d:
            deposits.append(d)
        rt = _to_int(r.get("RFE"))
        if rt:
            rents.append(rt)

    out: dict = {"supply_units": total if rows else None, "n_types": len(rows)}
    if areas:
        lo, hi = min(areas), max(areas)
        py_lo, py_hi = lo / SQM_PER_PYEONG, hi / SQM_PER_PYEONG
        if abs(lo - hi) < 0.5:
            out["area_text"] = f"전용 {lo:.0f}㎡ (약 {py_lo:.0f}평)"
        else:
            out["area_text"] = f"전용 {lo:.0f}~{hi:.0f}㎡ (약 {py_lo:.0f}~{py_hi:.0f}평)"
    if deposits:
        out["deposit"] = min(deposits)
    if rents:
        out["rent"] = min(rents)
    return out


def fetch_supply(n: Notice, service_key: str, timeout: int = 20) -> dict:
    """공고 1건의 공급정보 요약을 반환."""
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
        raw = resp.read().decode("utf-8")
    return parse_supply(raw)


def enrich(notices: list[Notice], service_key: str) -> None:
    """각 공고의 supply_units + 면적/임대조건(extra)을 채운다(in-place)."""
    for n in notices:
        if n.source != "LH" or n.supply_units is not None:
            continue
        try:
            info = fetch_supply(n, service_key)
        except Exception as ex:
            n.extra["supply_error"] = repr(ex)[:120]
            continue
        n.supply_units = info.get("supply_units")
        for k in ("area_text", "deposit", "rent", "n_types"):
            if info.get(k) is not None:
                n.extra[k] = info[k]
