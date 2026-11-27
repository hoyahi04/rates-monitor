# Y-FoRM Rates Monitor


> **팀 내부 베타: [https://hoyahi04.github.io/rates-monitor/beta/](https://hoyahi04.github.io/rates-monitor/beta/)** -> 요거 보기



> 📊 대시보드 바로가기: [https://hoyahi04.github.io/rates-monitor/](https://hoyahi04.github.io/rates-monitor/)
미국 국채 중심의 채권 데스크 대시보드다. 공개 자료만으로 만들며, 팀 발표와 투자의사결정, 예비 펀드운용에 쓴다.

| 주소 | 브랜치 | 용도 |
|---|---|---|
| `/` | `production` | 확정본. 발표와 투자판단에는 이 화면만 쓴다 |
| `/beta/` | `main` | 팀 내부 베타. 1차 완성본을 같이 본다 |

## 폴더

```
desk/                제품. 화면(index.html, v2.html), assets/, 화면용 자료 data/
pipeline/
  desk/              desk 자료 수집·가공 (fetch_extra, fetch_korea, build_data, bondmath)
  inputs/curve/      재무부 CMT 금리 (공통 입력) + 수익률 곡선 화면
  inputs/macro/      매크로 신호 5개 섹션과 점수표 + 각 화면
  model/             모형 포트폴리오·백테스트, 2페이지 대시보드 (model/README.md 참고)
site/                배포 첫 화면
decisions/           투자의사결정 기록 (날짜별 1파일)
docs/                스터디 자료
scripts/             배포용 사이트 빌드
archive/streamlit/   예전 Streamlit 앱 (더 쓰지 않음, 보관)
```

## 보기

`desk/index.html`을 브라우저로 연다. 서버가 필요 없다. 화면 설명과 숫자 읽는 법은 `desk/README.md`.

## 자료 다시 만들기

```bash
python3 pipeline/inputs/curve/fetch_data.py
python3 pipeline/desk/fetch_extra.py
python3 pipeline/model/backtest.py       # → pipeline/model/portfolio.js
python3 pipeline/desk/build_data.py
```

## 점검

```bash
python3 pipeline/desk/bondmath.py
node desk/assets/bondmath.js check
```

작업 방식은 `CONTRIBUTING.md`를 본다.
