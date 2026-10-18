# 첫 closed-copy capture 실행

**Linux 검사 통과 / 실제 capture 미완료.** [첫 실행](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38876152951)은 source `48a7fee222c8a25a70c446ac55b9b458be2ccab2`, run attempt 1입니다. 기존 [Cloud Spark→Trino 성공](../cloud-lakehouse/FULL_SUCCESS.md)과 다른 실행이며 이전 성공을 이번 capture의 성공으로 사용하지 않습니다.

| 경계 | 실제 확인 결과 |
| --- | --- |
| 기본 CI | `verify` 성공 |
| Linux 계약 검사 | Python 3.12.3·effective UID 0에서 56개 통과, 실패·오류·skip 각각 0개 |
| 소스 대조 | runtime 11개·기존 producer 7개와 base 8개·immutable input 5개·테스트 7개의 고정 SHA를 검사 전후 대조 |
| 실제 준비·수집 단계 | 실패. 공개 요약은 `FAILED / PREP_NOT_VERIFIED` |
| 원인·원본 작업·decoder | 구체적인 준비 실패 원인과 원래 main·metadata 수집·decoder 성공은 미확인 |
| 관측 개수 | captured object·snapshot·ref·validation pin·snapshot candidate는 모두 null. 0개로 바꾸지 않음 |
| 보존 정책 | object candidate 0은 KEEP-only 정책값. 완전 inventory나 삭제 가능성의 관측 결과가 아님 |

Linux 56개는 named observer·loader·composite 27개, prep helper 21개, CLI 8개입니다. 실제 Linux 파일 소유권·mode·nofollow·합성 child 제어를 검사했지만 실제 Spark classpath 준비·warehouse graph 수집의 성공을 대신하지 않습니다. 준비·수집 단계의 내부 provider 출력과 private 증거는 게시하지 않았습니다.

공개 [요약 원문](attempt-1.summary.json)의 whole SHA-256은 `2c6b7c0220da6feee86739740cbda70f8fb255e900e30c039fd941dbfb43df3e`, 크기는 1,317 bytes입니다. Runtime manifest는 `c8cecad8fc09ab20a78382c4a96daf5c9e761065cb774abd6cd9b65d0ee8be28`입니다. [실제 실행·Linux 검사 기록](attempt-1.validation.json)은 공개 workflow 메타데이터와 허용된 검사 출력만 묶습니다. 그 안의 `actualRuntimeCalled: false`는 Linux 오프라인 검사 단계의 범위이며 뒤에 시작한 준비 단계 전체를 설명하는 값이 아닙니다.

현재 schema 1 요약의 기본 false·null은 미확인을 뜻합니다. `compilerPrepVerified: false`로 구체적인 명령 실패나 컨테이너 부재를 추론하지 않습니다. `PREP_NOT_VERIFIED`만으로 실패 원인·자기 cold container의 종료·제거를 확인할 수도 없습니다. 새 public summary에는 UTC가 없으므로 실행 시각은 GitHub workflow 메타데이터와 구분합니다.

같은 workflow attempt를 재실행하지 않았습니다. 다음은 검토된 고정 단계·명령 결과·정리 관측만 추가해 원인을 구분하는 새 소스의 독립 실행입니다. source guard를 완화하거나 provider 예외문·argv·환경·stderr·내부 경로·CID를 공개하지 않습니다. 첫 실패 기록은 유지하며 snapshot 만료·객체 삭제·미니 PC 변경·전체 데이터 플랫폼 완료를 표시하지 않습니다.

검사 기록 JSON은 저장소의 `eol=lf` 규칙에 따라 줄바꿈만 LF로 게시합니다. 원래 수집 파일의 SHA-256은 `7d81de0fff48952f7b638074495412d4ab17dd55aa0bbe7121220cb462923827`, 게시 파일은 `19b3653222c7a28cac997b33480b743077b3bea28865681c28299ced8833ff84`이며 JSON 값은 같습니다. 공개 summary 원문 bytes는 변경하지 않았습니다.
