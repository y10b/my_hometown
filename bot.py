"""행복주택 당첨 알림 봇 — 메인 오케스트레이터.

흐름:  소스 수집 → 공통형식 normalize → 공급호수 enrich → 전략 필터/랭킹
       → (신규 / 마감임박) 중복 제거 → 디스코드 알림 → 상태 저장

사용법:
    python bot.py --sample      # 오프라인 샘플로 동작 확인 (네트워크/키 불필요)
    python bot.py --once        # 실데이터 1회 실행 (스케줄러/작업스케줄러가 주기 호출)
    python bot.py --once --dry   # 실데이터로 가져오되 디스코드 전송은 콘솔 출력
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime

# Windows 콘솔(cp949)에서도 한글/기호가 깨지지 않게 UTF-8로 출력
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import detail
import filters
import lh_source
import myhome_source
import notify
import store
import supply
from model import Notice, from_lh


def load_config(path: str = "config.json") -> dict:
    """config.json(필터/주기) + config.local.json(비밀, gitignore) + 환경변수 병합.
    비밀값 우선순위: 환경변수 > config.local.json > config.json
    → GitHub Actions에서는 LH_SERVICE_KEY / DISCORD_WEBHOOK_URL 시크릿으로 주입."""
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    if os.path.exists("config.local.json"):
        with open("config.local.json", encoding="utf-8") as f:
            cfg.update(json.load(f))
    cfg["lh_service_key"] = os.environ.get("LH_SERVICE_KEY") or cfg.get("lh_service_key", "")
    cfg["discord_webhook_url"] = (os.environ.get("DISCORD_WEBHOOK_URL")
                                  or cfg.get("discord_webhook_url", ""))
    return cfg


def collect(cfg: dict, use_sample: bool) -> list[Notice]:
    """모든 소스에서 공고를 모아 공통형식으로 반환. (현재 LH만, 나머지 어댑터는 추후)"""
    rows: list[dict] = []
    if use_sample:
        rows = lh_source.load_sample()
    else:
        rows = lh_source.fetch_notices(
            cfg["lh_service_key"],
            page_size=cfg["poll"]["list_page_size"],
            lookback_days=cfg["poll"]["lookback_days"],
        )
    notices = [from_lh(r) for r in rows]

    # 마이홈포털 통합 공고 (SH/GH/민간) — 활용신청+ENDPOINT 설정 시에만 동작, LH는 제외
    if not use_sample and cfg.get("myhome", {}).get("enabled"):
        try:
            # 마이홈은 LH 공고가 앞쪽을 채워서, 비-LH(SH/GH/민간)까지 잡으려면 전량 수신
            notices += myhome_source.fetch_notices(
                cfg.get("myhome", {}).get("service_key") or cfg["lh_service_key"],
                page_size=cfg.get("myhome", {}).get("page_size", 1000),
            )
        except Exception as ex:
            print(f"[myhome] 수집 실패(건너뜀): {repr(ex)[:120]}")
    return notices


def run(cfg: dict, *, use_sample: bool, dry: bool) -> None:
    now = datetime.now()
    today = now.date()

    notices = collect(cfg, use_sample)
    prelim = filters.prefilter(notices, cfg, today)     # 행복주택/미마감/지역/유형 먼저
    if use_sample:
        print("[샘플] 네트워크 미사용 → 공급/일정 조회 생략 (실행 시 자동 채워짐)")
    else:
        key = cfg["lh_service_key"]
        supply.enrich(prelim, key)      # 후보에만 공급호수+면적+보증금+월세
        detail.enrich(prelim, key)      # 정확한 접수마감일(시각은 가정값) + 당첨발표일
    candidates = filters.select_candidates(prelim, cfg, today)

    print(f"[수집] 전체 {len(notices)}건 → 대상유형 {len(prelim)}건 → 최종 후보 {len(candidates)}건")

    state = store.load()
    seen_new = set(state["seen_new"])
    seen_closing = set(state["seen_closing"])

    new_embeds, closing_embeds = [], []
    for n in candidates:
        tags = filters.annotate(n, cfg, now)

        if n.uid not in seen_new:                       # 신규 공고 알림
            new_embeds.append(notify.build_embed(n, tags, "new"))
            seen_new.add(n.uid)

        if tags["closing_soon"] and n.uid not in seen_closing:  # 마감 N시간 전 알림
            closing_embeds.append(notify.build_embed(n, tags, "closing"))
            seen_closing.add(n.uid)

    webhook = "" if dry else cfg.get("discord_webhook_url", "")
    notify.send(webhook, new_embeds)
    notify.send(webhook, closing_embeds)
    print(f"[알림] 신규 {len(new_embeds)}건 / 마감임박 {len(closing_embeds)}건 전송")

    state["seen_new"] = sorted(seen_new)
    state["seen_closing"] = sorted(seen_closing)
    store.save(state)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true", help="샘플 응답으로 오프라인 동작 확인")
    ap.add_argument("--once", action="store_true", help="실데이터 1회 실행")
    ap.add_argument("--dry", action="store_true", help="디스코드 전송 대신 콘솔 출력")
    args = ap.parse_args()

    cfg = load_config()
    if args.sample:
        run(cfg, use_sample=True, dry=True)
    elif args.once:
        run(cfg, use_sample=False, dry=args.dry)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
