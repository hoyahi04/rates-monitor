# Y-FoRM Rates Monitor

미국 국채 모니터링, 상대가치 전략, 포트폴리오 위험 분석을 한 앱에 모으는 조별 프로젝트다. 첫 화면은 2024년 11월 미국 재무부의 과거 수익률 표본으로 동작한다. 나머지 6개 화면과 공통 이벤트 캘린더는 담당자가 구현할 시작점이다.

## 실행

Python 3.11 이상에서 저장소 루트의 터미널을 연다. 다른 프로젝트와 설치 환경을 분리하려면 먼저 `python -m venv .venv`를 실행하고 만든 가상환경을 활성화한다.

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## 4인 작업 분담 예시

| 역할 | 작업 파일 | 첫 PR |
| --- | --- | --- |
| A | `pages/yield_curve.py`, `pages/yield_decomposition.py` | 곡선 비교 예제 검산 및 금리 분해 차트 |
| B | `pages/auction.py`, `pages/supply.py`, `pages/monetary_policy.py` | 응찰률, SOMA 잔액, SOFR−IORB 차트 |
| C | `pages/strategy.py` | 2s10s 신호와 포지션 출력 |
| D | `pages/risk.py` | 포지션 입력, 누적 손익과 DV01 |
| 공동 | `app.py`, `docs/positions.md` | 탭 연결과 전략·리스크 입력 형식 합의 |

공통 앱 설정은 `app.py`에 두고 각 화면은 담당 페이지 파일에서 수정한다. 원본 데이터 출처, 기준일, 단위는 화면에 표시한다. 각 탭은 본인 브랜치에서 실행한 뒤, 차트 하나 또는 계산 하나씩 PR을 연다. 리뷰어는 자기 환경에서 실행해 숫자와 단위를 확인한다.

## 조원 작업 시작

팀 저장소를 각자 복제하고 프로젝트 폴더를 연다.

```bash
git clone https://github.com/hoyahi04/rates-monitor.git
cd rates-monitor
```

수정 작업은 담당 탭 이름의 브랜치에서 시작한다. 예를 들어 `git switch -c feat/auction`으로 경매 작업 브랜치를 만들 수 있다. 변경을 커밋한 뒤 브랜치를 GitHub에 올리고 `main`을 대상으로 PR을 연다. 브랜치를 올리려면 저장소 쓰기 권한이 필요하다.
