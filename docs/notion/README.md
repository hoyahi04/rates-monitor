# Rates Monitor · Notion 확인 및 보관

확인일: 2026-11-18 (Asia/Seoul)
워크스페이스: Rates Monitor
루트: [Rates Monitor](https://app.notion.com/p/40dd4ed089878085a6d0d895d3c34ff8)

## 확인 결과

[탭 구성 아이디어](pages/410d4ed0-8987-8064-aa5a-d6c963e2d305.md)는 실제 미국 국채 종목을 가상 매매하고 자체 벤치마크 대비 위험과 초과성과를 분석하는 대시보드를 제안한다. 제목과 문맥상 기획안이며, 팀의 최종 승인이나 구현 완료를 의미하지 않는다.

- 화면 구상: Macro Views, Treasury Market, Relative Value, Portfolio Positioning, Attribution, Risk.
- 평가: GSW 제로 커브로 현금흐름을 할인하고 모델 평가가격으로 표시한다. 포트폴리오와 벤치마크에 동일한 평가 방식을 적용한다.
- 운용 가정: 가상 1,000만 달러, 잔존만기 1년 이상 고정금리 Notes·Bonds, 대표 종목 12~20개, 공매도·레버리지 없이 월별 리밸런싱.
- 비교: MSPD 발행잔액과 Dirty Price로 가중한 자체 벤치마크, 중립 복제 포트폴리오, 듀레이션을 맞춘 벨리 확대 포트폴리오.
- 공통 기반: 종목 정보, 거래·현금 장부, 일별 평가, 벤치마크 이력. 위험은 DV01·KRD·tracking error·시나리오로 측정한다.
- 성과분해: 캐리·롤다운, 평행 이동, 커브 변화, 거래비용, 잔차를 총손익과 대사한다.
- 데이터 제약: 개별 CUSIP rich/cheap에는 실제 시장가격, 입찰 tail에는 입찰 직전 when-issued 수익률이 필요하다.
- [호연](pages/41cd4ed0-8987-808e-a156-d281839d7ffc.md)에는 ACM과 연준 이사회의 금리 분해 자료, CSV, 참고 논문 파일이 연결되어 있다.

## 현재 코드와 기획의 차이

확인한 코드 기준 커밋: `7e030e3`.

| 항목 | 저장소 현재 상태 | Notion 기획 |
| --- | --- | --- |
| 화면 | 시장 5개 + 전략·리스크 2개 | 시장 3개 + 포트폴리오 3개 구상 |
| 수익률곡선 | 2024년 11월 표본, 날짜 비교와 2s10s | 시장 데이터 수집 및 기준 시점 정렬 |
| 나머지 화면 | 작업 예정 안내 | 평가·포지셔닝·성과·위험 기능 상세화 |
| 포지션 | 만기별 목표 DV01 전달 초안 | CUSIP별 거래·현금흐름 기반 보유내역 |
| 평가·성과 | 공통 평가 엔진과 NAV 미구현 | GSW 평가, 벤치마크, KRD, 성과분해 |

이번 저장은 문서 보관이다. 화면 재구성이나 계산 기능 구현은 포함하지 않는다. 기존 README의 4인 작업 분담은 예시이며, Notion에서 담당자 배정으로 확인된 것은 아니다. 구현을 진행할 때는 기획의 순서인 데이터 → 평가 엔진 → 중립 포트폴리오 → 위험 → 성과 → 액티브 전략 → 시장 화면 확장을 참고할 수 있다.

## Project 일정

원본 데이터: [project-rows.json](project-rows.json). Timeline 뷰의 활성 행 11개를 조회했고 `has_more=false`를 확인했다. 조회된 행에는 Status 값이 없으므로 일정 이름만으로 완료 여부를 추정하지 않는다.

| 날짜 | Milestone | Status |
| --- | --- | --- |
| 2026-11-04 | [상대가치 전략](https://app.notion.com/p/40ed4ed0898780f48021d67da68ce1f4) | 미지정 |
| 2026-11-07 | [공부해올것](https://app.notion.com/p/410d4ed0898780f5a8a5f094253cf761) | 미지정 |
| 2026-11-10 | [탭 별 개념들 + 뭐 들어갈지 아이디어](https://app.notion.com/p/410d4ed08987803c8841e6577718ae9a) | 미지정 |
| 2026-11-17 | [데스크 유형](https://app.notion.com/p/41bd4ed089878015a4fde0af373275fa) | 미지정 |
| 2026-11-17 | [탭 구성 아이디어](https://app.notion.com/p/410d4ed089878064aa5ad6c963e2d305) | 미지정 |
| 2026-11-18 | [탭 완성](https://app.notion.com/p/410d4ed0898780438460effe5d0e0f0b) | 미지정 |
| 2026-11-20 | [step6,7](https://app.notion.com/p/410d4ed089878060a24ec4aeeec5f4ff) | 미지정 |
| 2026-11-24 | [step6,7](https://app.notion.com/p/410d4ed08987806e9822f564e1395615) | 미지정 |
| 2026-11-30 | [대시보드 완성](https://app.notion.com/p/410d4ed0898780499749d55bb0a4b8cd) | 미지정 |
| 2026-12-01 | [장표 등 완성!!](https://app.notion.com/p/410d4ed0898780948c86e1104f33cc95) | 미지정 |
| 2026-12-04 | [발표](https://app.notion.com/p/410d4ed08987804caab1e33508f897de) | 미지정 |

## 원문 색인

| 저장 파일 | 출처 |
| --- | --- |
| [Rates Monitor](pages/40dd4ed0-8987-8085-a6d0-d895d3c34ff8.md) | [Notion](https://app.notion.com/p/40dd4ed089878085a6d0d895d3c34ff8?pvs=204) |
| [Project](pages/40ed4ed0-8987-8001-b62b-e9081526bee2.md) | [Notion](https://app.notion.com/p/40ed4ed089878001b62be9081526bee2?pvs=204) |
| [상대가치 전략](pages/40ed4ed0-8987-80f4-8021-d67da68ce1f4.md) | [Notion](https://app.notion.com/p/40ed4ed0898780f48021d67da68ce1f4?pvs=204) |
| [탭 별 개념들 + 뭐 들어갈지 아이디어](pages/410d4ed0-8987-803c-8841-e6577718ae9a.md) | [Notion](https://app.notion.com/p/410d4ed08987803c8841e6577718ae9a?pvs=204) |
| [탭 완성](pages/410d4ed0-8987-8043-8460-effe5d0e0f0b.md) | [Notion](https://app.notion.com/p/410d4ed0898780438460effe5d0e0f0b?pvs=204) |
| [공부해올것](pages/410d4ed0-8987-80f5-a8a5-f094253cf761.md) | [Notion](https://app.notion.com/p/410d4ed0898780f5a8a5f094253cf761?pvs=204) |
| [탭 구성 아이디어](pages/410d4ed0-8987-8064-aa5a-d6c963e2d305.md) | [Notion](https://app.notion.com/p/410d4ed089878064aa5ad6c963e2d305?pvs=204) |
| [호연](pages/41cd4ed0-8987-808e-a156-d281839d7ffc.md) | [Notion](https://app.notion.com/p/41cd4ed08987808ea156d281839d7ffc?pvs=204) |
| [데스크 유형](pages/41bd4ed0-8987-8015-a4fd-e0af373275fa.md) | [Notion](https://app.notion.com/p/41bd4ed089878015a4fde0af373275fa?pvs=204) |
| [대시보드 완성](pages/410d4ed0-8987-8049-9749-d55bb0a4b8cd.md) | [Notion](https://app.notion.com/p/410d4ed0898780499749d55bb0a4b8cd?pvs=204) |
| [step6,7](pages/410d4ed0-8987-8060-a24e-c4aeeec5f4ff.md) | [Notion](https://app.notion.com/p/410d4ed089878060a24ec4aeeec5f4ff?pvs=204) |
| [step6,7](pages/410d4ed0-8987-806e-9822-f564e1395615.md) | [Notion](https://app.notion.com/p/410d4ed08987806e9822f564e1395615?pvs=204) |
| [장표 등 완성!!](pages/410d4ed0-8987-8094-8c86-e1104f33cc95.md) | [Notion](https://app.notion.com/p/410d4ed0898780948c86e1104f33cc95?pvs=204) |
| [발표](pages/410d4ed0-8987-804c-aab1-e33508f897de.md) | [Notion](https://app.notion.com/p/410d4ed08987804caab1e33508f897de?pvs=204) |

페이지는 Notion fetch가 반환한 본문과 속성·상위 경로·스키마를 보존한 Markdown이다. 일반 Markdown에 없는 Notion 태그와 안정적인 파일 참조가 포함되어 있다. 구조화된 응답은 [snapshot.json](snapshot.json)에 함께 저장했다. 중복 제목 `step6,7`은 서로 다른 페이지 ID로 구분한다.

## 보관 범위와 제한

- Rates Monitor 루트, Project 데이터베이스, 활성 행 11개, 연결된 하위 페이지 호연으로 총 14개 엔터티를 보관했다.
- Rates Monitor를 대상으로 한 검색과 루트·데이터베이스 탐색에 기반한다. 접근 권한 밖의 페이지, 휴지통·보관된 행, 다른 최상위 페이지까지 포함하는 워크스페이스 전체 내보내기는 아니다.
- 조회 응답에 본문 잘림이나 알 수 없는 블록 관련 메타데이터는 제공되지 않았다. `<embed />`처럼 URL·내용이 반환되지 않은 블록은 그대로 보존했다.
- 첨부파일 10개는 안정적인 원본 참조와 파일명을 [attachments.json](attachments.json)에 기록했다. **파일 본체는 저장되지 않았다.** 다운로드 호스트 `prod-files-secure.s3.us-west-2.amazonaws.com`가 현재 환경 허용 목록에 없고, 다운로드 시 프록시 CONNECT 403이 반환되었다.
- 만료되는 서명 URL은 저장소에 기록하지 않았다. 첨부파일을 추후 보관하려면 Notion에서 새 다운로드 URL을 발급받고 해당 호스트에 접근 가능한 환경에서 다운로드해야 한다.
- 외부 Google Drive·블로그 링크, 댓글·변경 이력, 첨부문서의 내용은 수집·검증하지 않았다.
