# 자동 배포 초안 보존 계획기

공개 PR metadata를 입력받아 `KEEP` 또는 `SUPERSEDED_CANDIDATE`를 계산합니다. 적용기는 없으며 GitHub 호출·PR 닫기·label 변경·branch/image 삭제·병합·배포를 수행하지 않습니다.

## 실행

저장소 루트에서 Python 3으로 실행합니다. 외부 패키지는 필요하지 않습니다. 출력은 아직 없는 새 파일 경로여야 합니다.

```sh
python3 -I -B infra/maintenance/image-proposals/test_planner.py
python3 -I -B infra/maintenance/image-proposals/planner.py \
  --input infra/maintenance/image-proposals/examples/incomplete-historical-16.json \
  --output /tmp/image-proposal-retention-plan-once1.json
```

Windows에서는 `python3` 대신 설치된 `python`을 쓰고 새 출력 경로를 지정합니다. `plan_retention(document, rules)`는 입력이나 외부 상태를 바꾸지 않는 순수 함수이며 CLI만 로컬 입력·새 결과 파일을 읽고 씁니다.

## 보호 규칙

- 현재·rollback 보호 source가 불완전하거나 비어 있으면 전부 KEEP입니다. 현재·rollback source는 항상 KEEP입니다.
- 사람 commit·review·review request·human comment·assignee·label·본문 변경·설명되지 않은 updated 시각, 불완전한 snapshot·fork·Ready/auto-merge PR는 KEEP입니다.
- 엄격히 확인한 자동 draft 중 최신 source는 KEEP입니다. 최신 시각에 서로 다른 source가 동률이면 전부 KEEP입니다.
- 위 조건을 모두 통과하고 최신 source의 조상임이 compare metadata로 확인된 더 오래된 draft만 후보입니다. 날짜만으로 정리 대상으로 판단하지 않습니다.

`capturedAt`과 PR의 `created_at`·`updated_at`을 비교합니다. PR 시각이 제공된 캡처 시각보다 뒤라면 후보로 승격하지 않습니다. 현재 wall clock와의 비교나 실제 수집 시각의 독립 검증은 수행하지 않습니다.

## 기존 검증 코드 재사용

[public-rules-pins.json](public-rules-pins.json)은 main O(`1a9365fb`)의 기존 공개 [gitops_values.py](../../scripts/gitops_values.py), [ci_publication_gate.py](../../scripts/ci_publication_gate.py), [validate_gitops_pr.py](../../scripts/validate_gitops_pr.py), [propose_gitops_pr.py](../../scripts/propose_gitops_pr.py) 네 파일을 바이트 길이와 SHA-256으로 고정합니다. 코드를 복사하지 않고 현재 checkout의 기존 위치에서 핀을 확인한 뒤 별도 module로 로드합니다. 원본 파일은 변경하지 않습니다.

기존 `require_draft_pr`, 오프라인 get-map을 연결한 `evaluate_pr`, 제공된 과거 source 문맥의 `prepare`를 재사용합니다. Writer·실시간 metadata client는 만들지 않습니다. JSON 입력의 PR body·Git blob·publication·bot commit/review·ancestry를 검사하지만, bot actor metadata는 독립적인 암호학적 provenance 증명이 아닙니다. 현재 CI·registry 내용·배포를 재검증하거나 정리 권한을 주지 않습니다.

## 역사적 불완전 예제와 검증 상태

[16개 공개 요약 예제](examples/incomplete-historical-16.json)는 main N 시점에 이미 읽었던 draft 번호와 label 유무만 보존합니다. 정확한 수집 시각·author·파일·review·commit proof가 없고 rollback 보호 목록도 미완성이므로 **KEEP 16 / 후보 0**입니다. 현재 열린 PR 목록이나 현재 보호 source로 사용하지 않습니다. 누락된 provenance를 추정해 채우지 않습니다.

저장소 밖 원 후보의 Windows 검증에서는 합성 테스트 14개와 이 16개 요약 CLI를 각각 한 번 실행해 14 PASS·skip 0 및 KEEP 16 / 후보 0을 확인했습니다. 저장소 구조에 맞춘 후보도 Windows Python 3.12.14에서 합성 테스트 14개·skip 0, 역사적 요약 KEEP 16 / 후보 0을 각각 한 번 확인했습니다. Linux CI는 아직 실행하지 않았습니다. 테스트는 사람 수정·검토·image-only 위반·불완전 보호·ancestry·동률과 Writer/client 미호출을 확인합니다.

독립 workflow는 기존 ubuntu-24.04의 `python3`와 고정된 checkout/upload action을 재사용합니다. `contents: read`·checkout credential 비보존으로 합성 14개와 예제 CLI 한 번만 실행하고 제한된 결과 JSON을 게시하도록 준비했습니다. Docker·클러스터·배포를 호출하지 않습니다. 저장소의 기존 main Lab CI가 `infra/maintenance/**` 변경으로 별도 실행되는 규칙은 그대로입니다.
