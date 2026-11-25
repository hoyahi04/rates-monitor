# 협업 규칙 (5인 팀)

## 브랜치 구조
```
production  ← 실제 배포되는 최종본. main에서 PR로만 갱신
main        ← 리뷰가 끝난 통합본. 작업 브랜치에서 PR로만 갱신
feature/*   ← 개인 작업 브랜치 (fix/*, docs/* 도 동일)
```
- `main`, `production`에는 **직접 push하지 않습니다.**
- 작업 브랜치 이름: `feature/기능명`, `fix/버그명`, `docs/문서명`

## 하루 작업 흐름
```bash
git switch main && git pull
git switch -c feature/기능명
# 작업 후
git add . && git commit -m "무엇을 왜 바꿨는지"
git push -u origin feature/기능명
# GitHub에서 main 대상으로 PR 생성
```
작업 중 main이 바뀌었으면 `git pull origin main`으로 가져와 충돌을 먼저 해결합니다.

## PR 규칙
1. PR 하나에 목적 하나. 변경은 대략 400줄 이내.
2. 리뷰어 1명 이상 승인 후 병합 (본인 PR은 본인이 승인하지 않음).
3. 병합은 **Squash and merge** 로 통일.
4. 병합된 브랜치는 삭제.
5. PR 템플릿(무엇/왜/확인 방법)을 채운다.

## 배포 (production 갱신)
1. `main`이 안정적인 상태인지 확인한다.
2. GitHub에서 `main` → `production` PR을 만든다 (제목: `release: YYYY-MM-DD`).
3. 승인 후 **Create a merge commit** 으로 병합한다. (squash 사용 안 함)
4. 확정된 버전에 태그/릴리스를 만든다 (`v1.0.0` 형식).

## GitHub 설정 (저장소 관리자가 1회)
Settings → Rules → Rulesets 에서 `main`, `production` 에 각각:
- Require a pull request before merging
- Require approvals: 1
- Block force pushes
- (CI가 생기면) Require status checks to pass

Settings → General → "Automatically delete head branches" 켜기.
