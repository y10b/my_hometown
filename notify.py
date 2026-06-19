"""디스코드 알림 (Webhook + Embed 카드).

Webhook은 버튼은 못 달지만, embed url/필드로 '신청하러 가기' 링크를 클릭 가능하게 넣는다.
DRY_RUN(웹훅 미설정) 시에는 콘솔에 카드를 출력만 한다.
"""
from __future__ import annotations

import json
import urllib.request

from model import Notice

GREEN = 0x2ECC71
ORANGE = 0xE67E22
GREY = 0x95A5A6


def _man(won: int) -> str:
    """원 → 만원 단위 표기 (깔끔한 값은 정수, 아니면 소수 1자리)."""
    m = won / 10000
    if abs(m - round(m)) < 0.005:
        return f"{round(m):,}만원"
    return f"{m:,.1f}만원"


def build_embed(n: Notice, tags: dict, kind: str) -> dict:
    units = "미확인 (공고에서 확인)" if n.supply_units is None else f"{n.supply_units}호"
    dtc = n.days_to_close()
    when = "오늘 마감" if dtc == 0 else (f"D-{dtc}" if dtc and dtc > 0 else "-")

    flags = []
    # 신축 여부 힌트 (API로 자동판별 불가 → '예비'는 사진으로 직접 확인)
    if "최초" in n.title:
        flags.append("🆕 신축 첫입주(확정)")
    elif "예비" in n.title:
        flags.append("🔍 신축여부=공고 사진(박스옵션) 확인")
    if tags.get("big_supply"):
        flags.append("🟢 10호↑")
    if tags.get("closing_soon"):
        flags.append("⏰ 마감임박 - 지금 신청")
    if tags.get("supply_unknown"):
        flags.append("❓ 공급호수 미확인")

    title_prefix = "⏰ [마감임박] " if kind == "closing" else "🏠 [신규] "
    color = ORANGE if kind == "closing" else (GREEN if tags.get("big_supply") else GREY)

    fields = [
        {"name": "공급기관", "value": n.source, "inline": True},
        {"name": "유형", "value": n.house_type or "-", "inline": True},
        {"name": "지역", "value": n.region or "-", "inline": True},
        {"name": "공급 호수", "value": units, "inline": True},
        {"name": "마감", "value": f"{n.close_date or '-'} ({when})", "inline": True},
        {"name": "상태", "value": n.status or "-", "inline": True},
    ]
    # 공급/상세 정보에서 채워진 부가 항목 (있을 때만)
    if n.extra.get("area_text"):
        fields.append({"name": "면적", "value": n.extra["area_text"], "inline": True})
    if n.extra.get("deposit"):
        fields.append({"name": "보증금", "value": _man(n.extra["deposit"]), "inline": True})
    if n.extra.get("rent"):
        fields.append({"name": "월임대료", "value": _man(n.extra["rent"]), "inline": True})
    fields.append({"name": "신청", "value": f"[👉 바로 신청하러 가기]({n.url})", "inline": False})

    return {
        "title": (title_prefix + n.title)[:250],
        "url": n.url,
        "color": color,
        "fields": fields,
        "footer": {"text": " · ".join(flags) if flags else "-"},
    }


def send(webhook_url: str, embeds: list[dict]) -> None:
    """embed 최대 10개씩 묶어 전송. webhook 없으면 콘솔 출력(DRY RUN)."""
    if not embeds:
        return
    if not webhook_url:
        print("\n[DRY RUN] (webhook 미설정 - 콘솔 출력)")
        for e in embeds:
            print(f"  • {e['title']}")
            for fld in e["fields"]:
                print(f"      {fld['name']}: {fld['value']}")
            print(f"      tags: {e['footer']['text']}")
        return

    for i in range(0, len(embeds), 10):
        payload = {"embeds": embeds[i:i + 10]}
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            webhook_url, data=data,
            headers={"Content-Type": "application/json", "User-Agent": "happybot/1.0"},
        )
        urllib.request.urlopen(req, timeout=15).read()
