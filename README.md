# 🏠 my_hometown — 행복주택 당첨 알림 봇

서울 근교 **행복주택** 공고를 자동으로 모아, 전략에 맞는 것만 골라 **디스코드로 알림**을 보낸다.
신청은 알림 속 링크로 **LH 사이트에서 직접** 한다. (대리 신청 ❌ → 개인정보·책임 리스크 없음)

> 기존 청약 앱은 UX가 무거워 손이 안 간다. 이 봇은 **"알림만 켜두면, 조건 맞는 게 뜰 때 링크로 쏴주는"** 가벼운 개인용 도구다.

## 무엇을 하나

- LH 공공데이터 오픈 API로 **분양임대 공고 → 공급정보 → 접수일정**을 가져온다
- 전략 필터를 통과한 공고만 **디스코드 Embed 카드**로 알림 (공급호수·면적·보증금·월세·마감일·신청 링크 포함)
- **신규 공고 알림** + **마감 N시간 전 알림**(막판 접수용) 두 가지
- 30분마다 자동 실행 (GitHub Actions 또는 윈도우 작업 스케줄러)

## 당첨 전략 (필터)

| 필터 | 의도 |
|---|---|
| 행복주택만 | 대상 주택 한정 (`AIS_TP_CD_NM`에 "행복주택") |
| 신혼희망 제외 | 신혼희망타운은 신혼부부 전용 → 미혼 청년은 일반 행복주택만 |
| 서울 근교만 | `near_seoul_cities` 도시명이 공고 제목에 있는 것만 (LH API는 시·군 구분을 안 줘서 제목으로 판별) |
| 접수중만 | 지금 바로 신청 가능한 것만 (`status_in`) |
| 5호 이하 제외 | 공급 적으면 당첨 확률 급락 (`min_supply_units`) |
| 공급호수 내림차순 랭킹 | **실시간 경쟁률은 LH가 비공개** → 공급 많을수록 저경쟁으로 추정 |
| 마감 N시간 전 알림 | 막판 접수 전략 (`closing_alert_hours`, 기본 3시간) |

### ⚠️ 설계상 한계 (솔직하게)

- **실시간 경쟁률(신청자 수)은 LH가 접수 마감 후에만 공개**한다. 그래서 "그날 가장 저경쟁"을 실시간 숫자로 못 고른다 → **공급호수 기반 추정**이 최선.
- **마감 "시각"은 API에 없다**(접수마감 *날짜*만 제공). → 마감일 + `assumed_close_time`(기본 18:00)로 계산한 근사값.
- **신축(첫입주) 여부는 API로 판별 불가**(준공일·입주시기 미제공). → 카드에 "공고 사진(박스 옵션)으로 확인" 안내. 최종 판단은 사람이 링크 열어 사진 확인.

## 사용하는 LH 오픈 API (공공데이터포털, 키 1개 공용)

| API | 용도 | 모듈 |
|---|---|---|
| `lhLeaseNoticeInfo1` | 분양임대 공고 목록 | `lh_source.py` |
| `lhLeaseNoticeSplInfo1` | 공급호수·면적·보증금·월세 | `supply.py` |
| `lhLeaseNoticeDtlInfo1` | 접수 일정(마감일)·당첨발표일 | `detail.py` |

## 구조 (어댑터 패턴 — 소스 추가가 쉬움)

```
lh_source.py   LH 공고목록 어댑터  ─┐
(추후 SH/GH/민간 어댑터 추가)        ├→ model.Notice (공통 형식)
model.py       공통 스키마           ─┘
supply.py      공급호수/면적/임대조건 enrich
detail.py      접수일정/마감일 enrich
filters.py     전략 필터 + 랭킹 + 마감 N시간 전 판정
store.py       중복 알림 방지 (state.json)
notify.py      디스코드 Webhook 카드
bot.py         오케스트레이터 (엔트리)
```

## 로컬 실행

```bash
python bot.py --sample     # 네트워크/키 없이 샘플로 동작 확인
python bot.py --once       # 실데이터 1회 (디스코드 전송)
python bot.py --once --dry # 실데이터 가져오되 전송은 콘솔 출력만
```

의존성 없음 (Python 3.11+ 표준 라이브러리만 사용).

## 설정

### 비밀값 (키/웹훅)
우선순위: **환경변수 > `config.local.json` > `config.json`**

- `config.json` — 필터·주기만. 깃에 올려도 안전 (비밀값 비어 있음).
- `config.local.json` — 로컬 실행용 키·웹훅. **`.gitignore`로 커밋 제외.**
  ```json
  {
    "lh_service_key": "공공데이터포털 인증키",
    "discord_webhook_url": "디스코드 웹훅 URL"
  }
  ```
- 환경변수 `LH_SERVICE_KEY`, `DISCORD_WEBHOOK_URL` — GitHub Actions 시크릿용.

### 필터 (`config.json`)
```json
{
  "filters": {
    "house_type_keyword": "행복주택",
    "min_supply_units": 6,
    "big_supply_units": 10,
    "closing_alert_hours": 3,
    "assumed_close_time": "18:00",
    "status_in": ["접수중"],
    "regions": ["서울", "경기"],
    "near_seoul_only": true,
    "near_seoul_cities": ["고양", "성남", "부천", "광명", "과천", "안양", "의왕", "군포", "하남", "구리", "남양주", "의정부", "김포", "수원", "용인", "안산", "시흥", "양주"],
    "exclude_house_type_keywords": ["신혼희망"]
  },
  "poll": { "list_page_size": 100, "lookback_days": 60 }
}
```
- 예고 알림도 받고 싶으면 `status_in`에 `"공고중"` 추가.
- 근교 도시는 `near_seoul_cities`에서 가감.

## GitHub Actions 자동 운영

`.github/workflows/happybot.yml` — 30분마다 실행, 상태는 Actions 캐시로 유지.

1. 저장소 **Settings → Secrets and variables → Actions** 에 시크릿 추가:
   - `LH_SERVICE_KEY`
   - `DISCORD_WEBHOOK_URL`
2. **Actions 탭 → happybot → Run workflow** 로 1회 수동 테스트.

> ⚠️ GitHub Actions 러너는 **해외(미국) IP**라 `data.go.kr`이 차단(403)할 수 있다.
> 그럴 땐 **윈도우 작업 스케줄러**(`run.bat`을 30분 주기, 국내 IP)로 운영한다.
> 또한 무료 플랜 스케줄은 수~수십 분 지연/누락될 수 있어 "마감 N시간 전"은 정확히 N이 아니라 근사값이다.

## 로드맵

- [ ] SH(서울주택도시공사) 어댑터
- [ ] GH(경기주택도시공사) 어댑터 — 공급세대수도 API로 제공
- [ ] 민간(공공지원 민간임대) — 통합 API 없음, 스크래핑 검토

---
개인용 프로젝트. LH 공고 데이터는 공공데이터포털 오픈 API를 사용한다.
