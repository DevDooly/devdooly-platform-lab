# 공개 PR 입력 수집기 후보

누적 자동 배포 초안의 상태를 공개 metadata로 확인하는 별도 읽기 단계입니다. 역사적 번호 16개(74·72·69·65·62·60·58·55·51·49·42·39·36·26·24·22)만 대상으로 합니다. PR 목록 검색이나 임의 번호·URL 입력은 받지 않습니다. 2026-10-18 09:24:09–09:24:20 UTC에 공개 GET 52회를 한 번 실행했으며, 선택 metadata가 완전한 16개 모두 KEEP·후보 0으로 남았습니다. 이는 해당 시점의 기록입니다.

[실제 관측 요약](../../../docs/evidence/image-proposal-retention/public-capture-20261018-summary.json)과 [선택 metadata 원본 JSON](../../../docs/evidence/image-proposal-retention/public-capture-20261018.json)을 함께 제공합니다. 원본은 17,554바이트이며 SHA-256 `cd0a5481c4513fc29598d34dbcce01429e29f71a966b7676995974398d335084`로 독자가 대조할 수 있습니다. main `02d79aca` 양끝과 공개 values/runtime 전체 bytes가 같았고, 응답 570,017바이트·open draft 16개·review 0개·선택한 사람 활동 지표 0개였음을 보존합니다. 전체 사람 활동 이력이나 provenance·rollback 보호를 확인했다는 뜻은 아닙니다.

이 HTTP 기록은 미커밋 검토 소스 SHA-256 `0ba6a6f1fb3e0f342c0dc901bbce4785043c703ea7d02b1db5041953278474f2`에서 얻었습니다. 이후 버전은 부모 process 시작의 OSError도 유한 UNKNOWN/KEEP 결과로 저장하도록 보완했습니다. 이 새 오류 경로는 합성 검사 1개로 확인했으며, 과거 HTTP 결과를 새 소스에서 재실행한 것으로 표시하지 않습니다.

## 요청과 자원 한도

- GitHub의 고정 공개 저장소 API로 GET만 수행합니다. Authorization·cookie·token 파일·Git credential·SSH를 사용하지 않고 환경 프록시와 redirect를 비활성화합니다.
- PR 시작·끝 snapshot 32회, reviews 첫 페이지 16회, main 시작·끝 2회, 같은 main의 고정 values/runtime 파일 2회로 최대 52회입니다. retry·다음 페이지·files/commit/publication/ancestry 조회는 없습니다.
- 요청 timeout 4초, 응답 각각 128KiB·총 최대 6.5MiB, review 첫 페이지 최대 100개입니다. `Link`의 다음 페이지가 있거나 페이지가 100개로 가득 차면 부분 관측으로 남깁니다. 403/429 또는 잔여 한도 0 뒤에는 추가 네트워크 요청을 하지 않습니다.
- worker의 논리 시간은 120초이며 CLI 부모는 전용 child를 150초에 종료합니다. DNS·네트워크 지연이 논리 시계 밖에서 길어져도 부모의 상한을 적용합니다. 결과는 최대 128KiB인 새 로컬 파일 한 개에만 씁니다. 실패나 timeout에 자동 재실행하지 않습니다.

## 현재 상태와 KEEP 판단

PR의 head·base·created/updated·draft/open/merged·review/댓글 수·label·assignee·요청 reviewer·bot creator·본문 hash를 시작과 끝에서 대조합니다. 원문 body와 사용자 이름을 결과에 복사하지 않습니다. review가 있거나 댓글·label·사람/미확인 creator·설명되지 않은 update가 있으면 보존 근거로 표시합니다. 리뷰 목록의 완전한 역사나 변경 주체를 입증하지는 않습니다.

head나 선택 metadata가 변하면 한쪽을 현재 사실로 채택하지 않습니다. 부분 페이지·실패·필드 누락은 unknown으로 남기며, 과거 `draft=true`를 현재 값으로 대신하지 않습니다. 일부 관측이 불완전하면 planner 입력은 null입니다. 전체가 읽혀도 files·commit author·publication·ancestry 증거는 없으므로 모든 `proof`는 null이고 **KEEP 16 / 후보 0**입니다. 읽기 성공은 정리 후보의 출처 검증 성공을 뜻하지 않습니다.

현재 source는 같은 main에서 읽은 공개 values/runtime 파일이 [검토한 선언 핀](public-capture-pins.json)과 전체 bytes·Git blob SHA·SHA-256으로 같을 때만 API/worker source로 기록합니다. main이 바뀌면 이 확인은 무효입니다. 이는 GitOps 선언의 source이며 실제 Pod·실행 이미지 확인은 아닙니다. rollback source는 조회하거나 추정하지 않아 `complete=false`, `rollback=[]`를 유지합니다.

수집은 순차 관측입니다. head 양끝이 같다는 사실을 원자적 snapshot이나 GitHub 전체 역사 검증으로 확대하지 않습니다. 실제 PR 닫기·label·branch/image 삭제·병합·배포·운영 정책 변경은 구현하지 않습니다.

## 수동 실행과 검증 범위

원 소스의 합성 경계 검사 8개는 Windows Python 3.12.14에서 skip 0으로 통과했습니다. head drift·부분 review·사람 활동·공개 선언 변경·unknown·main drift·고정 URL/호출 예산을 다룹니다. 이후 부모 process 시작 실패 검사 1개도 별도로 통과했고 이전 8개를 수동 반복하지 않았습니다. 소스 `1ceb6855`의 [Linux CI 39115988241](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39115988241)에서 최종 합성 9개가 skip 0으로 통과했습니다. 같은 실행의 기존 planner 14개와 역사적 예제 KEEP 16 / 후보 0도 확인했습니다. CI의 public GET은 0회이며 검사한 source bytes는 전후 동일했습니다.

기존 retention workflow의 별도 `offline-capture` job은 고정 합성 9개만 자동 검증합니다. 합성 검사는 [검토한 공개 선언 fixture](examples/captured-declarations/) 두 개만 사용하므로 향후 정상 배포에서 GitOps 값이 바뀌어도 영향을 받지 않습니다. 실제 collector가 현재 공개 선언의 고정 핀을 확인하는 정책은 유지합니다. public GET·클러스터·SSH·자격증명·실제 정리는 호출하지 않습니다. 기존 planner 14개 job은 그대로 유지하며, collector 수정 때문에 그 14개를 수동 반복하지 않습니다. 실제 네트워크 요청 전에는 고정 대상·자원 한도·출력 위치를 검토합니다.

```sh
python3 -I -B infra/maintenance/image-proposals/test_collect_public_inputs.py
python3 -I -B infra/maintenance/image-proposals/collect_public_inputs.py \
  --output /tmp/public-image-proposals-capture-once1.json
```

실제 GET은 별도 검토 후 새 출력 경로에서 한 번만 실행합니다. `--public-read-worker`는 부모가 시간 제한을 적용하기 위한 내부 인수이며 직접 실행하지 않습니다. 수집 완료 후에도 rollback/출처 누락을 보호 상태로 유지하고, 실제 정리는 별도 범위에서 검토합니다.
