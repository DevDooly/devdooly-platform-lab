# 합성 Iceberg 보존 조건 선택 예제

공개 합성 입력3개를 기존 Python planner로 offline 계산하고 화면에서는 저장된 결과만 선택한다. 실제 metadata·Cloud capture·미니 PC·회사 자료를 사용하지 않는다. 브라우저에 planner를 다시 구현하지 않고 expiry·DELETE·GC·서비스 명령도 제공하지 않는다.

| 조건 | 고정 입력 변화 | 실제 계산 결과 |
| --- | --- | --- |
| 현재 이력 보호 | current300→200→100→900 연결 | DETERMINED, snapshot9개 KEEP·후보0 |
| old detached 이력 | current/ref/pin 밖의 오래된900 | DETERMINED, snapshot8개 KEEP·900 후보1 |
| 오래된 inventory | 수집 뒤300초+1ns라는 가정 시각 | UNDETERMINED, 후보0·모두 KEEP으로 보호 |

각 조건의 파일9개는 전부 KEEP이고 객체 후보는0이다. snapshot 후보가 아직 만료되지 않았으며 공유 파일·참조 없는 파일도 삭제를 허가하지 않는다. 판정 보류의0은 검증 성공을 뜻하지 않는다.

정책은 최소 경과7일·최소 보관1개·inventory 유효300초다. 입력 시각과 평가 시각은 고정된 합성 가정이며 방문자의 현재 시각을 평가하지 않는다. 다른 Cloud 검증의 정책·개수·graph와 연결하거나 합산하지 않는다.

## 생성과 출처

`generate_scenarios.py`는 같은 폴더의 공개 fixture3개와 `infra/maintenance/iceberg_retention_plan.py`만 읽는다. planner의 공개 source commit은 `245d61a5749760a20918ab091d9410ce6735b1c0`이며 같은 Git tree의 로컬 소스로 파일 hash를 확인했다. 입력은 기존 `tests/maintenance/test_iceberg_retention_plan.py`의 공개 fixture에서 파생했다.

새 생성기 자체의 commit은 생성 당시 미확정이라 null로 남기고 실제 source SHA-256을 기록한다. 공개 JSON bytes hash와 planner의 canonical input hash도 구분한다. `offlineComputation`, `onlyPublicFixtures`만 true이고 실제 metadata 수집·서비스 명령·실제 시계 평가는 false다. planner의 `applyEnabled`, `deletionExecutorImplemented`, `inventoryClaimsIndependentlyVerified`도 false를 유지한다.

```sh
python3 -B examples/iceberg-retention-scenarios/generate_scenarios.py --check
python3 -B -m unittest discover -s tests/maintenance -p 'test_iceberg_policy_scenarios.py' -v
```

생성은 새 출력만 허용하며 기존 파일을 자동으로 덮어쓰지 않는다. `--check`는 현재 공개 입력·소스로 다시 계산한 bytes와 정적 bundle을 비교한다. 임의 inventory 경로를 받지 않는다. fixture·planner가 변경되면 새 source pin과 결과를 별도로 검토해야 한다.

## 검증 범위

C 후보에서 실제 offline 생성, 기존 planner8개·생성 계약5개·새 UI SSR6개와 새 component의 TypeScript strict 검사를 수행한다. 결과와 source 전후 hash는 별도 제출 manifest/receipt에 기록한다. UI 테스트는 기본 조건·detached·stale 표시, 잘못된 데이터의 fail-closed, 합성 label·native select·닫힌 details를 확인한다.

전체 Astro 통합·기존 전체 웹 회귀·브라우저의 실제 select 조작·1280/375px·공개 게시·운영 서비스 검증은 별도다. 이 합성 UI의 결과로 기존 실제 capture 기록이나 백업·배포 상태를 갱신하지 않는다.
