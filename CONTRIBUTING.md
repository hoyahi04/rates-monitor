# 협업 규칙 (5인 팀)

## 브랜치의 역할
```
production  ← 확정본. 발표·투자의사결정·운용에 쓰는 화면 (배포 주소 /)
main        ← 팀 내부 베타. 리뷰를 통과한 1차 완성본 (배포 주소 /beta/)
feature/*   ← 개인 작업 브랜치 (fix/*, docs/* 도 동일)
```
- `main`, `production`에는 **직접 push하지 않는다.** PR로만 바꾼다.
- 이 저장소는 **공개**다. 실제 포지션, 금액, 계좌, API 키는 올리지 않는다.

## 하루 작업 흐름
```bash
git switch main && git pull
git switch -c feature/기능명
# 작업 후
git add . && git commit -m "무엇을 왜 바꿨는지"
git push -u origin feature/기능명
# GitHub에서 main 대상으로 PR 생성
```
작업 중 main이 바뀌었으면 `git pull origin main`으로 가져와 충돌을 먼저 해결한다.

## PR 규칙 (→ main)
1. PR 하나에 목적 하나. 변경은 대략 400줄 이내.
2. 리뷰어 1명 이상 승인 후 병합. CI(계산 점검)가 통과해야 한다.
3. 병합은 **Squash and merge**.
4. 병합된 브랜치는 삭제.
5. 병합되면 `/beta/`에 자동 배포된다. 팀이 여기서 화면을 확인한다.

## 확정 (main → production)
1. `/beta/`에서 숫자와 화면을 팀이 확인한다.
2. `main` → `production` PR을 만든다 (제목: `release: YYYY-MM-DD`).
3. **2명 이상** 승인 후 **Create a merge commit** 으로 병합한다 (squash 사용 안 함).
4. 발표나 투자판단에 쓰는 시점에는 태그를 붙인다: `vYYYY.MM.N` (예: `v2026.11.1`).
5. 판단을 내렸으면 `decisions/`에 기록한다 (`decisions/README.md`).

## GitHub 설정 (저장소 관리자가 1회)
Settings → Rules → Rulesets:

| 대상 | 설정 |
|---|---|
| `main` | PR 필수, 승인 1명, 상태 검사 `check` 필수, force push 차단 |
| `production` | PR 필수, 승인 2명, 상태 검사 `check` 필수, force push 차단 |

- Settings → General → "Automatically delete head branches" 켜기.
- Settings → Environments → `github-pages` → Deployment branches 에 `main`과 `production` 둘 다 허용.
