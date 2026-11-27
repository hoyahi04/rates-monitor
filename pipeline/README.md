# pipeline/ — 자료 수집과 가공

| 경로 | 내용 |
|---|---|
| `inputs/curve/` | 재무부 CMT 일별 금리(1990년~). `fetch_data.py` → `data.js`. 다른 모든 단계의 공통 입력 |
| `inputs/macro/0X_*/` | 매크로 신호 5개 섹션. `fetch_data.py` → `analyze.py` → `data.js`, `signals.js` |
| `inputs/macro/scoreboard.py` | 5개 섹션 점수 → `scoreboard.csv`/`.js` (커브 뷰·포지션). 규칙은 `inputs/macro/README.md` |
| `desk/` | desk 화면용 자료. `fetch_extra.py`, `fetch_korea.py` → `build_data.py` → `../desk/data/desk_data.js` |
| `model/` | 모형 포트폴리오와 백테스트(`backtest.py` → `portfolio.js`), 2페이지 대시보드(`build.py` → `combined.html`) |

`inputs/` 아래 폴더에는 각자의 화면(`index.html`)도 있어 `/curve/`, `/macro/` 주소로 함께 배포된다.

## 실행 순서

```bash
python3 pipeline/inputs/curve/fetch_data.py
(cd pipeline/inputs/macro/03_inflation && python3 fetch_data.py && python3 analyze.py)   # 섹션별로
python3 pipeline/inputs/macro/scoreboard.py
python3 pipeline/desk/fetch_extra.py
python3 pipeline/desk/fetch_korea.py     # ECOS 인증키가 있을 때만
python3 pipeline/desk/build_data.py
```

## 저장소에 넣지 않는 것

- Bloomberg 지수 엑셀, 논문·교재 PDF: 재배포 제한·저작권. 각자 받는다.
- `inputs/macro/05_liquidity_vol/MOVE_index_daily_weekly.xlsx`: ICE 지수 원자료. 없으면 `fetch_data.py`가 Yahoo `^MOVE`로 대신 받는다.
- `desk/.env` (ECOS 인증키).
