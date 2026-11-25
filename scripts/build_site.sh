#!/usr/bin/env bash
# 한 브랜치의 체크아웃(src)에서 배포용 사이트 폴더(out)를 만든다.
# 사용: bash scripts/build_site.sh <src> <out>
# 배포 주소 구조: /  /desk/  /curve/  /macro/  /study/
set -euo pipefail
src="$1"; out="$2"
mkdir -p "$out"
if [ -d "$src/desk" ]; then            # 새 구조
  cp "$src/site/index.html" "$out/"
  cp -r "$src/desk" "$out/desk"
  cp -r "$src/pipeline/inputs/curve" "$out/curve"
  cp -r "$src/pipeline/inputs/macro" "$out/macro"
else                                   # 옛 구조 (static/) — 구조 변경 전의 브랜치용
  cp -r "$src/static/." "$out/"
fi
if [ -d "$src/docs/study" ]; then
  mkdir -p "$out/study"
  cp "$src"/docs/study/*.html "$out/study/"
fi
find "$out" \( -name '*.py' -o -name '.env' \) -delete
