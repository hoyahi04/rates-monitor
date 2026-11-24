# static/ — 정적 HTML 모니터 (매크로 신호 5개 + 수익률 곡선)

Streamlit 앱(`app.py`, `pages/`)과 별개로, Python 스크립트가 데이터를 받아 `data.js`/`signals.js`를 만들고
`index.html`을 브라우저로 바로 여는 구조다. 원본은 팀원 로컬 폴더(thebomchoi/rates-monitor 클론)에서 옮겨 왔다.

| 경로 | 내용 |
|---|---|
| `macro/README.md` | 5개 섹션 공통 틀, 신호 정의·백테스트 규칙 |
| `macro/0X_*/` | 섹션별 `fetch_data.py` → `analyze.py` → `index.html`, `notes.md` |
| `macro/scoreboard.py` | 5개 섹션 점수 → `scoreboard.csv`/`.js` (커브 뷰·포지션) |
| `macro/scoreboard_rules.html` | 점수 규칙표 페이지 |
| `desk/` | 채권 데스크 대시보드 (홈 + 메뉴 6개). `index.html` 버전 1, `v2.html` 버전 2. 자세한 건 `desk/README.md` |
| `curve/` | Tab 1 수익률 곡선 모니터 (원래 폴더명 `2. portfolio`). 1990년~ CMT 일별 금리 |

## 실행

```bash
cd static/curve && python3 fetch_data.py          # 공통 금리 데이터
cd ../macro/03_inflation && python3 fetch_data.py && python3 analyze.py   # 섹션별
cd .. && python3 scoreboard.py                     # 통합 점수표
```

## 레포에 넣지 않은 것

- Bloomberg 지수 엑셀(`data/benchmark/`), 논문·교재 PDF: 재배포 제한·저작권. 각자 받는다.
- `macro/05_liquidity_vol/MOVE_index_daily_weekly.xlsx`: ICE 지수 원자료. 파일이 없으면 `fetch_data.py`가 Yahoo `^MOVE`로 대신 받는다.
