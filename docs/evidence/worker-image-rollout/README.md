# worker 이미지 전환 — 2026-10-21 UTC

[PR177](https://github.com/DevDooly/devdooly-platform-lab/pull/177)에서 worker의 image digest와 source 두 값만 바꾸고, Argo CD의 자동 동기화 뒤 새 worker가 Ready인 것을 확인했습니다. API·웹의 pin은 유지했습니다. 이전의 [읽기 전용 클러스터 점검](../cluster-readonly/README.md)은 worker74를 확인한 당시 기록이며, 이번 전환 이후 상태와 구분합니다.

| 항목 | 확인한 값 |
| --- | --- |
| PR head | `70264c390385bcff96ae5bb528a1ce45416421eb` |
| main 병합 | `33c5e8c0cf211dc3f4c622b98b40be0b48a3890b`, `2026-10-21T00:19:02Z` |
| 이전 worker source | `74a8e98844a8fea0653951136ede0e7de0d7ac08` |
| 새 worker source | `6f551a16a8ed536bb126403234c41b9e9b266d43` |
| 새 worker image digest | `sha256:ee71389be27fa484284a517a324c52a9c827cd20db21f0b306c4dcfd52147aad` |
| 관측 API source | `245d61a5749760a20918ab091d9410ce6735b1c0` — worker와 별도 pin |
| 공개 메타데이터 요약 | [summary.json](summary.json) |

## 소스·이미지와 적용 범위

선정한 source의 [Actions 검증39476929942](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39476929942), Jenkins build133의 성공 status와 [실제 이미지 게시39477559607](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39477559607)을 대조했습니다. 공개 OCI index의 전체 bytes와 digest 일치는 [게시 준비 근거](../runtime-release-readiness/oci-read-summary.json)에 보존되어 있습니다. 이번에는 이 고정 이미지를 worker에만 적용했으며 [PR169](https://github.com/DevDooly/devdooly-platform-lab/pull/169)의 API·웹 전환을 함께 병합하지 않았습니다.

PR177의 [렌더 검사39516401223](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39516401223)은 성공했습니다. 별도 로컬 Helm 비교에서는 worker의 image·source annotation·`SOURCE_COMMIT`·`IMAGE_DIGEST` 네 렌더 값만 바뀌고 나머지 리소스가 같음을 확인한 뒤 적용했습니다. 렌더 비교는 적용 전 선언 검사이며 실제 Ready의 근거는 아래 클러스터 관측입니다.

## 적용 중과 적용 후 관측

| 관측 시각(UTC) | 확인한 상태 |
| --- | --- |
| `00:19:59.882406` | 새 worker는 Running이지만 Ready가 아니었고 Argo health는 Progressing이었습니다. |
| `00:20:56.548017` | 새 worker Ready, Argo Synced·Healthy와 main revision `33c5e8c0…`를 확인했습니다. |
| `00:23:59.660316` | 같은 새 worker의 Ready·재시작0과 Argo Synced·Healthy를 다시 확인했습니다. |

최종 관측에서 Deployment4개는 observed generation이 일치하며 각각1개 Ready, Pod7개는 Running·Ready, PVC4개는 Bound였습니다. 기존 DB의 restartCount1과 다른 container의0을 구분해 유지합니다. worker의 Deployment·Pod image와 CRI imageID가 선정한 digest에 일치했습니다. 선택한 다른 workload·PVC 메타데이터도 전후 같았습니다. 이 대조는 선택한 리소스와 관측 창의 범위이며 호스트 전체의 무변경 증명은 아닙니다.

worker의 Recreate, 종료 유예300초, exec readiness의 주기10초·timeout5초·실패 threshold3, 메모리 request256Mi/limit768Mi는 바꾸지 않았습니다. Kubernetes `preStop`은 없으며 JVM 내부 종료 hook의 대기와 구분합니다. Argo operation의 성공 시각을 worker Ready 시각으로 대신 사용하지 않았습니다.

## 보존 점검과 공개 요약의 범위

별도로 허용받은 기존 DB·객체·Kafka의 선택 항목을 교체 전후 읽어 대조하고, 새 실행의 시작·heartbeat 전진과 현재 잠금 소유를 확인했습니다. 자료 불일치 없이 전환을 마쳤고 원복은 사용하지 않았습니다. 새 업무 작업을 넣거나 기존 자료·슬롯을 수정하지 않았습니다. 그 과정의 행 지문·객체 키/본문 지문·소유 세션 값과 원문은 공개 요약에 포함하지 않습니다. `summary.json`은 클러스터 메타데이터와 이미 공개된 GitOps 변경을 요약하며, 비공개 보존 점검을 독립적으로 재검증할 수 있는 자료는 아닙니다.

이전 프로세스의 종료 코드와 잠금 해제 순간은 직접 포착하지 못했습니다. 이전 Pod의 부재와 새 Pod의 Ready를 그 이벤트의 관측으로 바꾸어 적지 않습니다. [Error 처리](../runtime-error-cleanup/README.md)와 [일부 client 구성 실패 정리](../client-construction-error/README.md)가 포함된 소스의 배포를 확인한 것이며, 실제 OOM·Error 주입 후 운영 복구·HA·전체 백업 복원·SLA를 검증한 결과는 아닙니다.

## 공개 연결과 다음 확인

교체 후 [수동 GET39521322979](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39521322979)의 고정6개 조회가 HTTP200·공개 DTO 검증을 통과했습니다. 응답 source는 관측 API245이며 worker6f55와 구분합니다. [원문과 별도 공개 화면 관측](../public-get/README.md#후속-실제-관측--2026-10-21-utc)에서 GET 결과와 브라우저의 새 실행 표시를 각각 설명합니다. GET artifact 자체는 worker의 source·시작 시각·heartbeat를 담지 않습니다.

다음은 기존30분 주기의 관측 수집·게시가 새 worker를 저장된 Pages 관측에도 반영하는지 확인하는 것입니다. 실시간 조회 화면의 갱신과 저장된 관측의 자동 게시를 구분하며, timer를 강제 실행하거나 주기를 줄인 결과를 자연 갱신으로 기록하지 않습니다.

기동 복원·토큰 교체·자원 예산 정책·[PR102](https://github.com/DevDooly/devdooly-platform-lab/pull/102)는 계속 보류합니다.
