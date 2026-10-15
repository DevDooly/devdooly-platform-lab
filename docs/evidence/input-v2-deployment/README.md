# 1,000건 시나리오 실제 배포와 공개 관측

2026-10-15 UTC에 미니 PC의 API·웹·worker를 같은 검증 소스 `6c5aff948770982dd44c8d44547131b3ccf6ddd9`로 배포했습니다. 실제 worker가 고정 합성 입력 1,000건을 처리하고 원본·결과·실패 파일 3개를 저장했으며, 공개 Pages에도 전체 7개 작업·export 파일 정보 14개를 게시했습니다. [기계 판독 요약](summary.json), [공개 작업 화면](https://devdooly.github.io/devdooly-platform-lab/#job-observation)을 연결합니다.

이 기록은 [앞선 격리 입력·동시성·자원 시험](../input-concurrency-load/README.md) 이후의 실제 배포 검증입니다. 앞선 보고서의 당시 운영 소스·수치·판정은 그대로 보존했습니다.

## 소스에서 실행 이미지까지

같은 소스의 Jenkins build 26과 [Actions 검증](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38707565738)이 성공한 뒤 [이미지 게시 실행](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38708118514)이 gate·publish·propose 단계를 모두 수행했습니다. gate만 성공하고 게시 단계가 제외된 별도 실행은 이미지 게시 성공으로 세지 않았습니다.

API와 worker의 고정 index digest는 `sha256:b669d7e03712f436e20baedb2ed50cb8c41136164e6b2cc6bd4b4c5b7e7d43e6`입니다. 익명 GHCR 조회·K3s 이미지 캐시의 OCI index → amd64 manifest → config와 Pod의 실제 imageID·CRI config를 대조했습니다. 웹도 별도 고정 digest와 실제 실행 config를 확인했습니다. 선언된 태그나 환경 변수만으로 실행 버전을 판정하지 않았습니다.

| 단계 | Git 변경과 검증 |
| --- | --- |
| API·웹 | [PR 28](https://github.com/DevDooly/devdooly-platform-lab/pull/28), GitOps `1ea896c09f3c650f1d3f93c5d391e7e65d1a482f`, 읽기 검사 30/30 |
| worker | [PR 29](https://github.com/DevDooly/devdooly-platform-lab/pull/29), GitOps `ea261f038725d1a2f49d77e885ea730fd98564a6`, 읽기 검사 33/33 |
| 실제 V2 접수 | 한 번의 내부 stage Job, 처리·파일·원본 보존·정리 검사 5/5 |

Helm의 세 단계 render를 비교해 첫 배포는 API·웹 두 Deployment, 다음 배포는 worker 한 Deployment만 변경함을 확인했습니다. Argo CD가 main을 오래된 캐시로 보던 시점에는 캐시 새로고침을 요청했으며 workload에 직접 image 변경이나 `helm upgrade`를 수행하지 않았습니다. 최종 상태는 지정 GitOps revision의 Synced·Healthy입니다.

## 기존 자료의 보존과 실제 결과

배포 전에 기존 6개 작업의 원본 6개·export 12개를 전체 GET으로 확보하고, 업무 자료와 runtime journal의 InnoDB 7개 테이블을 transaction snapshot으로 보관했습니다. 외부 AES-256-GCM 사본의 인증·전체 bytes 일치도 확인했습니다. 이 배포 중 백업을 실제 복원했다는 뜻은 아닙니다.

API와 worker 양쪽의 실제 새 버전을 확인한 뒤 `sensor-validation-v2` 고정 fixture를 한 번 접수했습니다. 접수 실패에 대한 자동 재시도는 없었습니다.

| 결과 | 실제 확인 값 |
| --- | --- |
| 입력 | 1,000건·자연 생성 원본 99,600 bytes |
| 성공 / 실패 / 업무상 중복 / 대기 | 500 / 300 / 200 / 0 |
| 작업 / export 상태 | COMPLETED / EXPORTED |
| Kafka | partition 0, committed offset 7, log end 7, lag 0 |
| 실행 슬롯 | 두 export의 저장 확인 후 비어 있음 |
| 전체 파일 GET | 기존 18개 bytes 그대로 + 신규 3개 독립 검증 = 21개 |

새 원본·결과·실패 파일을 실제 전체 GET해 내용·크기·SHA-256과 DB/API metadata를 대조했습니다. 기존 6개 작업의 전체 업무 SQL·시각·HTTP 작업 정보는 그대로였고, 전체 DB 작업은 7개·export 정보는 14개가 됐습니다. 기존 PVC/PV 11개, 원래 Docker 38개(실행 26개), DB·Kafka·Garage Pod, 방화벽·호스트 부팅·관측 unit·timer 주기도 보존했습니다.

stage Job은 실패·미확정 상태의 증거가 자동 삭제되지 않도록 initial TTL을 넣지 않았습니다. 검증을 마친 성공 Job만 정확한 UID의 DeleteOptions로 정리했으며 DB 작업·S3 객체·PVC는 삭제하지 않았습니다.

## 공개 화면의 확인

기존 systemd 관측 서비스를 한 번 실행해 실제 7개 작업·파일 정보 14개를 수집했습니다. root 0600 상태 파일, 임시 SA token 정리, 기존 timer enabled·active 상태를 확인했습니다. [Pages 실행](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38714361174)의 build·deploy 성공 후 공개 작업 JSON과 플랫폼 envelope 전체를 실제 수집 원본과 비교했습니다. 확인 시각·소스는 summary.json에 남겼습니다.

공개 화면은 마지막 실제 수집 기록을 읽습니다. 브라우저가 미니 PC의 실시간 API에 연결하거나 작업을 접수하는 기능은 제공하지 않습니다. 관측 시각을 게시 시각으로 바꾸지 않았고 원래 약 30분 수집 주기를 유지했습니다.

## 검사에서 발견한 문제와 한계

첫 API·웹 읽기 검사는 29/30이었습니다. 기존 DB Pod의 과거 restartCount 1을 새 Pod처럼 0회로 요구한 검사 오류였고 DB가 새로 재시작한 것은 아니었습니다. 수정 후 새 Pod는 0회, 바뀌지 않은 Pod는 배포 전 횟수·container 상태가 정확히 같은지 검사해 30/30을 확인했습니다. 첫 실패 보고서는 보존했습니다.

이 배포의 실제 1,000건 작업은 한 번이며 원본 크기는 99,600 bytes입니다. 정확한 1MiB 경계와 동시 2·8개 접수 시험은 앞선 별도 격리 통합 검사입니다. 운영 처리량·p95·SLA·진행 중 crash·전체 호스트 복구·고가용성 검증으로 확장해 해석하지 않습니다.

이전 `ed5815e7` worker는 V2 dispatch를 거부하고, 이전 작업 관측 API는 V2 export 문서를 재생성할 수 없어 새 작업의 관측에 실패합니다. 기존 demo GET 모델이 1,000행 조회 자체를 지원하지 않는다는 뜻은 아닙니다. V2 접수 이후에는 API와 worker 모두 V2 지원 소스를 유지해야 하며, 옛 digest만 단순 복구하는 절차를 사용하지 않습니다. 배포 전 checkpoint는 별도 복원 계획의 입력이며 현재 운영 자료 위에 자동으로 덮어쓰지 않습니다. 요청 빈도 제한과 공개 실행은 이 소스의 구현 범위에 없습니다.
