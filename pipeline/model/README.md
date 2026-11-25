# pipeline/model/ — 모형 포트폴리오 (아직 비어 있음)

`pipeline/desk/build_data.py`는 이 폴더의 `portfolio.js`를 읽는다. 지금은 파일이 없어서
`build_data.py`를 다시 돌릴 수 없고, 화면은 올려 둔 `desk/data/desk_data.js`로만 보인다.

넣어야 할 파일 (팀원 로컬의 `3. dashboard/`에 있음):

| 파일 | 내용 |
|---|---|
| `portfolio.js` | 2015년부터 규칙대로 운용한 모형 포트폴리오 (`backtest.py`의 출력) |
| `backtest.py` | 위 파일을 만드는 스크립트 |

함께 필요한 것: 매 영업일 자동 갱신 워크플로 `.github/workflows/daily.yml`.
넣은 뒤에는 그 안의 경로를 이 저장소 구조(`pipeline/inputs/...`, `pipeline/model/...`)에 맞게 고친다.
