# pipeline/model/ — 모형 포트폴리오와 2페이지 대시보드

팀 로컬 폴더의 `3. dashboard/`를 옮겨 온 것이다. `pipeline/desk/build_data.py`는 이 폴더의 `portfolio.js`를 읽는다.

- 경로는 이 저장소 구조에 맞게 고쳤다 (`pipeline/inputs/curve`, `pipeline/inputs/macro`).
- `backtest.py`는 벤치마크 비중을 `pipeline/inputs/curve/initial_portfolio_wip/benchmark_proxy.json`에서 읽는데,
  이 파일은 저장소에 없다. 없으면 스크립트 안의 기본 비중(`BM_W_FALLBACK`)을 쓴다.
- `build_mock_data.py`는 같은 폴더의 `benchmark_proxy.json`, `universe.csv`가 있어야 돈다 (저장소에 없음).
- 이 폴더는 배포 사이트에 올라가지 않는다. 화면은 저장소를 받아 `combined.html`을 직접 연다.
- 매 영업일 자동 갱신 워크플로(`.github/workflows/daily.yml`)는 아직 없다.

아래는 원래 `3. dashboard/README.md`의 내용이다.

---

# 대시보드

- `combined.html` — 매크로와 운용을 합친 화면. 다른 파일 없이 열린다. 이것부터 열면 된다.
- `macro_slim.html`, `index_slim.html` — 매크로, 운용 화면 각각 (자료 파일을 옆에서 읽음)
- `backtest.py` → `portfolio.js` — 2015년부터 규칙대로 운용했다고 보고 다시 계산한 성과·위험·리밸런싱 기록.
  만기 구간마다 모형 국채 한 종목을 재무부 CMT 금리로 매일 평가한 것이고 실제 종목이 아니다.
- `build.py` → `macro_indicators.js`, `combined.html` — 지표 표를 뽑고 합친 화면을 만든다.
- `anim.js` — 애니메이션

다시 만들기: `python3 backtest.py && python3 build.py` (먼저 각 섹션 `fetch_data.py`와 `pipeline/inputs/macro/scoreboard.py`)

아래는 처음 만든 자세한 운용 시안(`portfolio_full.html`, `build_mock_data.py`, `mock_portfolio.js`)에 대한 설명이다.

---

# 운용 페이지 화면 시안

실제 페이지가 아니라 **구상을 보여 주는 견본**입니다. 기준 문서는 `../design_spec.md`입니다.

## 여는 법

- `portfolio_full.html`을 더블클릭합니다. 같은 폴더의 `mock_portfolio.js` 하나만 읽고, 인터넷 연결은 필요 없습니다.
- 어두운 화면은 주소 끝에 `?theme=dark`, 밝은 화면은 `?theme=light`를 붙입니다. 붙이지 않으면 기기 설정을 따릅니다.
- 맨 아래 "자료와 계산 규칙"을 펼친 채로 열려면 주소 끝에 `#rules`를 붙입니다.

## 다시 만드는 법

```
python3 build_mock_data.py
```

표준 라이브러리만 씁니다. 아래 원자료를 읽어 검산 33개를 찍고, **모두 맞을 때만** `mock_portfolio.js`를 새로 씁니다. 하나라도 어긋나면 파일을 쓰지 않고 오류로 끝납니다.

| 읽는 파일 | 쓰임 |
|---|---|
| `pipeline/inputs/curve/data.js` | 수익률곡선, 스프레드, Fly z-score, 금리 공분산, 월별 금리 변화 |
| `pipeline/inputs/macro/scoreboard.csv` | 점수, 뷰, 포지션, 판단 기록 (깨져 있으면 `page_build_wip/backup_before_build/`의 백업본) |
| `pipeline/inputs/macro/scoreboard.js` | 다음 달 잠정 판정 (`live`) |
| `pipeline/inputs/curve/initial_portfolio_wip/benchmark_proxy.json` | 벤치마크(대용 지수). `validation` 항목은 읽자마자 버립니다 |
| `pipeline/inputs/curve/initial_portfolio_wip/universe.csv` | 예시 포트폴리오에 담은 종목의 가격과 듀레이션, 대용 지수의 가격 출처 |

Bloomberg 자료와 공식 지수 값은 읽지도 싣지도 않습니다.

## 어느 숫자가 실제·추정·예시인가

화면에서는 예시를 **주황 점선 칸**으로, 추정을 **"추정"이라는 말**로 표시합니다. 아직 없는 값은 지어내지 않고 **"–"와 점선 빈 칸**으로 둡니다. 자료 파일에서는 `kind`(또는 `kinds`) 값이 `real` / `estimate` / `example` / `pending`입니다.

| 부분 | 성격 | 만든 방법 |
|---|---|---|
| 점수 5개, 뷰 3개, 포지션, 다음 달 잠정, 판단 기록 | 실제 | `scoreboard.csv`, `scoreboard.js` |
| 수익률곡선, 2s10s, 5s30s, Fly, z-score | 실제 | `data.js`. z-score는 그날까지 직전 3년(1년) 일별 값의 평균과 표본 표준편차 |
| 벤치마크(대용 지수) 버킷 비중·듀레이션·수익률·carry·roll | 실제 (확정 전, 12월 구성) | `benchmark_proxy.json`, `universe.csv`. 300종목 중 296개는 FedInvest 종가, 4개는 CMT 금리로 값을 매김 |
| 금리 공분산, Duration 포지션만 있을 때의 추적오차 (±0.25년 19.9bp, ±0.5년 39.8bp) | 실제 | 버킷 대표 금리의 최근 3년 일별 변화 748개 (2023-11-21 ~ 2026-11-20) |
| 월별 금리 변화 (10년, 2s10s, Fly) | 실제 | `data.js` 월말 값. scoreboard의 `next_*`와 같음을 확인 |
| Duration·Slope·Curvature 월별 기여와 누적, 맨 위 "초과수익 추정" 타일, 누적 선, 워터폴, 적중 횟수 | 추정 | 포지션 × 버킷 대표 금리 변화. Slope는 다리당 0.10년(2년·30년 쪽), 불릿은 5–7 +0.10년에 1–3·10–20 −0.05년씩으로 가정 |
| 오늘(11-20) 치 NAV | 추정 | 버킷별 듀레이션 기여 × 가격일 뒤 금리 변화 |
| 보유 18종목, 도넛, NAV, 현금, 한도 점검 | 예시 | 버킷당 3종목(만기 순서의 1/6·3/6·5/6 지점). 종목과 가격은 실제, 고른 종목과 비중이 예시. carry 기준으로 고르지 않음 |
| 액티브 듀레이션, 추적오차 20.2bp, 시나리오 손익, 월 carry+roll 42.4bp | 예시 | 예시 포트폴리오에 실제 공분산·금리 충격·종목 값을 곱해 계산. 현금 이자는 0 |
| Carry & Rolldown 기여, 기타, 초과수익 합계, Carry 적중 횟수 | 아직 없음 | 종목 가격으로 과거를 다시 만든 뒤에 채움. 화면에는 "–"와 빈 칸. 지어낸 숫자를 넣지 않음 |

## 파일

| 파일 | 내용 |
|---|---|
| `portfolio_full.html` | 시안 화면. 계산하지 않고 읽어서 그리기만 합니다 |
| `mock_portfolio.js` | `window.PORTFOLIO_MOCK`. 실제 페이지의 `portfolio.js`가 가질 형태의 초안. 화면에 소수 한 자리로 찍는 값은 넷째 자리까지 담아 화면에서 한 번만 반올림합니다 |
| `build_mock_data.py` | 위 자료 파일을 만드는 스크립트. 기본값(버킷 한도 ±5%p, 현금 이자 0 등)은 파일 맨 위에 있습니다 |

## 알아 둘 점

- 세 전략 기여의 합은 2015년 이후 +13.4bp입니다. 1년에 1bp쯤이라 우연히 나온 값과 구분되지 않고(t 0.15), 거래비용은 빼지 않았습니다. 가장 크게 밀린 폭은 −55bp입니다.
- 대용 지수는 12월 구성(11-30 기준 예정)입니다. 공식 지수보다 듀레이션이 짧게 나오는 것으로 알려져 있어, 액티브 듀레이션은 대용 지수 대비로만 읽어야 합니다. 차이의 크기는 화면과 자료 파일에 싣지 않았습니다.
- Slope 기여는 2년과 30년 금리의 차이로 계산합니다. 그래서 월간 분해표의 2s10s 변화와 방향이 다른 달이 있습니다 (25개월 중 4개월).
- 가정한 Slope 다리 0.10년은 1–3 버킷 비중으로 약 5.4%p라 버킷 한도 ±5%p를 넘습니다. 한도 안에서 담을 수 있는 크기는 초기 포트폴리오 쪽에서 받아야 합니다.
- 적중 횟수는 기여를 0.01bp 단위로 반올림해 0보다 큰 달만 셉니다. 금리가 움직이지 않은 달(0bp)은 판단 기록에 ○/✕를 표시하지 않습니다.
- 과거 월 고르기는 모양만 있고 동작하지 않습니다. 판단 기록은 최근 12개월까지만 담았습니다. 매크로 링크는 `pipeline/inputs/macro/portfolio_full.html` 첫 화면으로만 갑니다.
- 종목 종가는 하루 늦게 나와서 평가 기준일(11-19)이 금리 기준일(11-20)보다 하루 이릅니다.
- `portfolio_full.html` 끝의 `selfCheck`와 `flag`는 시안 점검용입니다 (오류 수와 화면 폭을 `<html>`에 적고, 다른 페이지 안에 넣었을 때 부모 창에 알림). 실제 페이지로 옮길 때 지웁니다.
- 원자료는 만든 시각의 값으로 고정됩니다 (`data.js` 14:09, `scoreboard.csv`·`scoreboard.js` 18:05, `benchmark_proxy.json`·`universe.csv` 18:06). 원자료가 바뀌면 스크립트를 다시 돌립니다.
