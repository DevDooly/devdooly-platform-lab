# 현재 클러스터 metadata의 읽기 전용 확인

2026-10-20 **22:25:12.733684–22:25:12.898406 UTC**에 기존 연결로 Lab의 Kubernetes metadata와 Argo Application 설정·상태를 읽었다. [공개 파생 요약](summary.json)은 허용한 집계와 선언 pin만 새로 작성한 자료다. 접속 주소·Pod 이름·UID·context·volume 식별자·비밀 값과 비공개 점검 원문은 포함하지 않는다.

## 이 시점에 확인한 것

| 대상 | 관측 |
| --- | --- |
| Deployment | 4개 모두 observed generation이 현재 generation과 같고 각각 desired 1 / Ready 1 |
| Pod | 7개 모두 Running이며 Ready 조건이 True |
| 재시작 횟수 | DB 컨테이너 1, 나머지 각 컨테이너 0. 원인은 조회하지 않음 |
| PVC | 4개 모두 Bound, `local-path` / `ReadWriteOnce` |
| Argo | 현재 sync revision `e0f14d3d0203b5dfe897895c78e68a24200d186e`, `Synced` / `Healthy` |

Argo의 repository·`main`·chart 경로·release가 저장소 선언과 일치했다. 별도 후속 조회에서 두 valueFiles의 정확한 순서와 Helm override 1개의 이름을 확인했다. 이 override는 프록시 CIDR 설정이며 값은 공개하지 않는다. image·source override는 없었다. 이 후속 수집기에도 관측 시각이 없으므로 최초 수집 구간에 합치지 않는다. 현재 sync revision과 과거 마지막 operation revision은 서로 다른 필드이므로 같은 적용 시점으로 합치지 않았다. [Application 선언](https://github.com/DevDooly/devdooly-platform-lab/blob/e0f14d3d0203b5dfe897895c78e68a24200d186e/gitops/bootstrap/application.yaml)

## API와 worker의 pin은 별도다

API의 `SOURCE_COMMIT`은 `245d61a5749760a20918ab091d9410ce6735b1c0`, worker는 `74a8e98844a8fea0653951136ede0e7de0d7ac08`이었다. Deployment·Pod에 선언된 API·web·worker image digest는 요약에 구분했다. Argo가 최신 main과 동기화됐다는 사실만으로 모든 애플리케이션 image가 최신 소스로 바뀌었다고 판정하지 않는다.

별도의 후속 읽기에서 worker의 Pod→ReplicaSet→Deployment controller UID 연결과 selector 일치를 확인했다. Deployment·Pod·컨테이너 runtime의 image도 모두 위 worker digest와 일치했다. 실제 UID와 이름은 공개하지 않는다. 후속 수집기에는 관측 시각이 없으므로 위 22:25:12 UTC 구간에 수행한 것으로 합치지 않는다.

worker의 현재 선언은 `Recreate`, 종료 유예 300초, runtime run 인자, exec readiness의 주기 10초·timeout 5초·실패 기준 3회이며 `preStop`은 없었다. 메모리 request 256Mi / limit 768Mi는 조회한 현재 설정이고, 새 자원 예산 정책이나 여유 용량의 보장이 아니다. [선언된 worker 설정](https://github.com/DevDooly/devdooly-platform-lab/blob/e0f14d3d0203b5dfe897895c78e68a24200d186e/gitops/environments/home-lab/runtime.yaml)

[Error 정리](../runtime-error-cleanup/README.md)와 [부분 client 구성 실패](../client-construction-error/README.md)의 최근 수정은 위 worker pin에 반영된 것으로 확인하지 않았다. 이번 읽기에서 image를 바꾸거나 새 worker를 배포하지 않았다. 소스·이미지 후보와 실제 실행 상태의 구분은 [배포 준비 계획](../../plans/runtime-rollout-readiness.md)을 따른다.

## 관측 과정과 남은 경계

첫 SSH 시도는 host key 확인에서 차단되어 조회하지 않았다. 기존 신뢰 지문으로 엄격히 대조한 후속 연결만 성공했으며, 첫 실패 기록과 실제 지문 값은 비공개로 보존했다. 첫 투영에서 상위 경로로 시작하는 valueFiles가 필터링되어 `null`로 보였지만 설정 부재로 판정하지 않았다. 지정 Application만 다시 읽은 후속 조회로 두 파일의 정확한 순서 일치를 확인했고 override 값은 출력하지 않았다.

이번 범위는 metadata 조회이며 service exec·DB 질의·재시작·설정 변경·배포를 수행하지 않았다. DB의 새 V3/V4·업무 자료 baseline, 유휴 상태·lease 소유, S3·Kafka 자료 상태는 확인하지 않았다. Pod Ready와 Argo Healthy도 작업 완료·자료 보존·장기 가용성의 증거로 확대하지 않는다. 기동 복원·토큰 교체·자원 예산 정책·PR102 접수 gate의 보류는 유지한다.
