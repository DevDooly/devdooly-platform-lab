# 현재 상태에서 이어서 구축하기

최근 배포·보존 확인(2026-10-16 갱신): 소스 `74a8e988`의 [Actions](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38814779596)와 Jenkins 45에서 API 191개 + 독립 Java 예제 20개, 총 211개를 통과했습니다. 이어 PR #52의 API·웹과 PR #53의 worker를 실제 전환했습니다. 애플리케이션 소스는 `74a8e988`, 최종 GitOps revision은 `b63fedfa`입니다. 2026-10-15 23:12:57 UTC의 배포 후 검사에서 작업 8개·export 정보 16개, 기존 객체 24개 + native7 객체 12개의 전체 GET, PV·PVC 각 13개·Docker 60개와 Kafka offset/end 8·lag 0을 확인했습니다. [S3 전송 배포·보존 근거](evidence/s3-runtime-rollout/README.md)는 해당 시점의 기록이며 실시간 가용성을 뜻하지 않습니다.

후속 별도 JVM SDK 검증에서는 실제 배포 JAR의 factory와 Apache5로 알려진 객체 3개를 전체 GET했습니다. 3회 호출·3회 시도·추가 retry 0회, client 종료·정상 exit 0과 자기 Job·ConfigMap·Secret·읽기 전용 key의 정리·폐기를 확인했습니다. factory의 maxAttempts 3은 유지했습니다. 운영 API JVM 내부의 호출·장애 주입·PUT·SLA 검증과 구분합니다. 2026-10-16 00:02:58 UTC의 별도 읽기 검사에서 전체 객체 36개와 업무 SQL·기존 리소스 보존, 임시 SDK 자원·키 부재를 확인했습니다.

이전 readiness 운영 검증(2026-10-15 14:54 UTC)은 source `3e0d85be`의 readiness 배포·idle worker 교체·같은 ID 읽기 전용 재시도입니다. API 180개 + 독립 예제 20개, 8개 EXPORTED 작업·export 정보 16개·객체 24개와 Kafka lag 0을 확인했습니다. [전체 근거와 한계](evidence/worker-readiness/CORRECTED_IMAGE.md)를 먼저 읽습니다. [native7 데이터 흐름](evidence/iceberg-jdbc/README.md)과 별도 [Cloud Spark 시험 8](evidence/spark-silver/README.md)은 실제 검증한 정적 기록을 공개했습니다. native7의 빈 snapshot 포함 총 3개와 Cloud Bronze의 데이터 append snapshot 2개는 서로 다른 실험입니다. 공개 관측 카드의 숫자는 각 카드의 실제 수집 시각을 따릅니다.

2026-10-16 03:12:33 UTC의 [새 Cloud 전체 시험](evidence/cloud-lakehouse/FULL_SUCCESS.md)은 별도 fresh warehouse에서 Spark→Trino 10개 조회, 6→12→12행·현재 파일 2→1 compaction과 자기 컨테이너 종료를 확인했습니다. 기존 native7 자료는 유지하며, 새 a7의 [현재 DB 논리 백업·격리 복원](evidence/current-db-restore/README.md)은 8개 테이블 스키마·7개 비runtime 테이블 행·BLOB 대조와 원본 DB 보존을 확인했습니다. 원래 stop receipt는 실패로 유지하고 별도 DB 0·Pod 0·Bound/Retain 관측을 구분하며 정상 exit는 UNOBSERVED입니다. 전체 애플리케이션 복구·Phase6·운영 용량·현재 가용성의 완료 표시가 아닙니다.

이전 V4 배포 검증(2026-10-15): API·worker를 source `202ab6806130cfb37e8829ce7d52c89990d8a54a`·schema V4로 전환해 API·웹 32/32, worker 35/35를 확인했습니다. [V4 실제 전환](evidence/admission-v4-deployment/README.md)을 먼저 확인하세요. 해당 시점에는 신규 V4 stage 검증 전이었으며, 아래 V2 처리 결과는 이전 검증입니다. API·worker의 V2 지원 이미지 확인 후 고정 1,000건 작업을 처리했습니다. 총 7개 EXPORTED 작업·파일 정보 14개·Kafka lag 0과 기존 18개 객체 보존을 확인했고, 공개 JSON 전체가 실제 수집 원본과 일치했습니다. [이전 V2 배포·게시 근거](evidence/input-v2-deployment/README.md)에 당시 조건을 남겼습니다. 아래 단계별 기록은 각각 당시의 검증 조건을 보존합니다.

Java API·포트폴리오와 K3s·Jenkins·Argo CD를 Ubuntu 미니 PC에서 운영합니다. 2026-10-15 최초 Kafka·Garage·상시 worker 배포에서는 두 합성 작업의 자동 처리·파일 확인·슬롯 해제와 공개 Pages의 실제 job 관측을 확인했습니다. [최초 배포·게시 근거](evidence/runtime-deployment/README.md)를 보존합니다. 초기 설치는 [미니 PC 근거](evidence/mini-pc/README.md), CI/CD는 [Jenkins 근거](evidence/jenkins-ci/README.md), 이전 플랫폼 collector의 실패 보존·반복 게시 11회는 [플랫폼 수집 근거](evidence/platform-observation/README.md)에 구분해 기록했습니다. 전체 단계는 [진행 목록](ROADMAP.md)을 따릅니다.

실제 V2 배포 전 후보판의 최대 1,000개 입력·단일 슬롯 동시 2/8개 접수·초과 입력 거부는 격리 통합 검사 5개로 확인했습니다. 별도 Linux Docker worker에서도 1 CPU·768MiB 제한으로 1,000개 작업 3회와 원본·export 파일 9개의 전체 GET을 검증했습니다. [입력·동시 접수 검증](evidence/input-concurrency-load/README.md)은 현재 운영판과 구분합니다. 그 시험 당시 운영 source `ed5815e7`·기존 6개 작업과 서비스는 보존했으며, 운영 처리 용량이나 SLA를 검증한 결과는 아닙니다.

내부 승인 간격의 기본 API 157개·격리 backend 19개·복원본 호환 8개는 [기존 검증](evidence/admission-cooldown/README.md)에 보존합니다. 실제 운영 V4의 API·웹/worker 전환은 [별도 근거](evidence/admission-v4-deployment/README.md)로 확인했으며 기존 7개 작업·파일 정보 14개·Kafka lag 0을 유지했습니다. 첫 runtime 초기화 전 관측 실패와 이전 container exit UNOBSERVED를 함께 남깁니다. 기존 timer의 11:40:08.792Z V4 기록은 [Pages 실행](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/38728965840) 성공 후 12:01:58 UTC에 두 공개 JSON 전체가 서버 원본과 같음을 확인했습니다. [정기 게시 후속 근거](evidence/admission-v4-deployment/PUBLICATION.md)에 실제 hash를 보존합니다. 해당 문서의 신규 V4 fixture·charged cooldown 검증은 위 readiness 후속 근거에서 후속 확인했으며, 단일 슬롯·승인 간격·구형 stage 우회 위험을 구분합니다.

별도 [AI 개선 예제](../examples/java-window-analysis/README.md)는 시간대 오류 회귀와 같은 답을 내는 두 알고리즘의 비교입니다. Java 테스트 20개·runner 검사 3개, 실제 Windows Java 21 JMH 16조합·48 fork·240 interval을 [근거](evidence/ai-window-analysis/README.md)에 보존했고 [포트폴리오](https://devdooly.github.io/devdooly-platform-lab/#ai-window)에서 코드와 측정 기록을 선택해 볼 수 있습니다. 선택은 정적 기록 조회이며 Java를 실행하지 않습니다. 일부 큰 오차·미커밋 source manifest·사람 검토 대기 상태를 표시하고 운영 ETL 개선율로 일반화하지 않습니다. [CI 검증](evidence/ai-window-analysis/ci-validation.md)과 수동 JMH 측정도 구분합니다.

## 확인한 결과

- 서버 지문 대조와 전용 키 SSH 인증, Ubuntu·포트·기존 서비스 읽기 전용 점검
- 초기 설치 당시 Docker 컨테이너 23개와 방화벽 설정 보존, 새 Lab 전용 설치·저장 경로
- K3s Node Ready와 클러스터 API·DNS·외부 HTTPS 통신 확인
- 초기 API 테스트 15개·웹 테스트 13개; readiness 당시 Linux API 180개·독립 예제 20개와 이후 소스 `74a8e988`의 CI 211개(API 191 + 예제 20)를 각각 확인
- Linux runner의 이미지 빌드·MariaDB·API 교체·데이터 보존 검증
- GHCR 이미지 게시와 미니 PC에서 익명 다운로드
- Jenkins Kubernetes agent의 테스트·패키징·필수 산출물과 같은 SHA의 commit status 전달 확인
- 현재 main의 Jenkins·Actions 성공을 함께 요구하는 단일 이미지 게시 경로와 draft GitOps PR 자동 제안
- 정상 B 배포의 source·digest·GitOps·실행 이미지 추적과 실제 JUnit 실패의 게시·PR·배포 차단
- GitOps 값을 이전 정상 A로 되돌려 API/Web pin·source·전체 SQL·처리 시각·PVC와 기존 Docker 보존 검증
- 기존 저장소 `gitops/`의 digest 고정값으로 Argo CD 앱 배포
- API·웹·DB Ready, PVC Bound, 웹을 통한 12건 처리 결과 검증
- 공개 Pages용 실제 관측 기록 수집과 계약 검증
- 별도 플랫폼 collector의 허용 필드·출처 계약, 제한된 ServiceAccount 실제 수집과 읽기 권한 허용·거부 확인
- 인증 실패 때 마지막 성공 전체·수집 시각 유지와 정상 수집 회복, 실제 출력 0600 확인
- 새 관측 UI의 실패·오래된 기록 표시 로컬 검증: 신규 13개를 포함한 전체 웹 테스트 26개·타입 검사·Pages 경로 빌드
- 실제 HTTP 401 실패 envelope 수동 Pages 게시와 이전 성공 전체·시각 보존, 공개 1280px·390px 화면 확인
- Ubuntu 격리 collector 41개 통과, 최종 자동화 35개 root·일반 사용자 각각 통과, 초기 비활성 자동화 설치·systemd 정적 검증 완료
- 전용 Pages 자격증명 등록 후 수동 host cycle·실제 systemd service·timer 최초 자동 실행의 Pages 게시와 전체 공개 JSON 일치 확인
- 최초 자동 실행을 포함한 11회의 Pages build·deploy success와 실제 약 30~31분 간격 확인
- API·웹 replicas 0에서 공개 홈·마지막 기록과 DB·기존 서비스 보존, 같은 PR #5 정상 B 재가동·runtime 재검증 완료
- 외부 암호화 백업·격리 DB 복원·호스트 재부팅: [근거와 한계](evidence/recovery/README.md)
- 역사적 외부 백업의 파일 bytes·metadata, 빈 WAL SQLite 무결성과 별도256바이트 키 조립 후속 검증: [파일 전용 근거](evidence/historical-file-restore/README.md). 첫 restore 실패는 유지하며 K3s·Jenkins application 기동·전체 복원은 미검증
- Kafka·Garage·상시 worker의 실제 K3s 배포와 6개 workload Ready, 새 PVC 3개와 기존 PVC 보존
- 내부 고정 fixture 두 작업의 각 12/7/3/2/0 처리·파일 4개 전체 검증·빈 실행 슬롯·Kafka lag 0
- 실제 배포 job 관측과 플랫폼 관측의 Pages 게시·공개 JSON 전체 일치, Ubuntu 수집·게시 검사 135개 통과
- 새 job 관측의 실제 systemd service 성공·Pages 게시·공개 JSON 전체 일치, private 0600·임시 SA token 정리와 기존 timer 활성 설정 복구
- 원래 timer 자동 수집·Pages 게시 2회와 서비스 완료 간격 1개(1809.371239초), 변경 없는 unit/collector와 원본 전체 일치: [근거](evidence/runtime-recovery/README.md)
- 이번 배포 전후 Docker 전체 38개·실행 26개의 ID·시작 시각·mount와 기존 seed·V1 데이터/시각 보존
- 실제 idle worker Pod의 UID 조건 정상 교체·STOPPED→새 RUNNING·exit 143·restartCount 0과 기존 두 작업/파일/offset·다른 서비스 보존: [근거](evidence/runtime-recovery/README.md)
- 교체 worker의 새 fixture 12/7/3/2/0·EXPORTED·파일 2개 실제 Get 확인·슬롯 해제, 총 3작업/6파일·offset 3·lag 0
- Kafka/Garage 전용 PVC 3개 cold backup의 외부 암호화 사본 반환·인증·전체 해시 일치와 새 namespace/PVC 전체 manifest 복원: [근거](evidence/runtime-pvc-restore/README.md)
- 격리 정책의 원본 접근 차단·DNS 허용, Kafka 3개 record/offset과 Garage 9개 inline 객체의 전체 GET 일치
- clone에만 128KiB 물리 블록 canary를 만들어 추가 2PVC 복원·Pod 교체 전후 각 GET10, 복제 Kafka 정상 재시작 후 같은 PVC/record 보존
- 시험용 3개 workload 정상 종료·Pod 0·Retain PVC 5개 보관, 최종 28개 보존 검사에서 원본 SQL/PVC/6개 Ready Pod·기존 Docker 38개/실행 26개 유지
- 백업·trial 보호의 순수 dry-run 계획기 31개 테스트·실제 삭제 후보 0, 새 합성 PVC만의 실제 정리 검증과 기존 PVC/PV 11개·원본 Pod 6개·Docker 38개 보존
- 기존 cgroup limit 유지·고정 12개 입력 3회/약 63초 관측, 총 6개 EXPORTED 작업·파일 12개 전체 Get·Kafka offset 6/lag 0과 최종 보존 검사 25개 통과: [보존·자원 근거](evidence/retention-resource-budget/README.md)

Jenkins의 첫 빌드는 플러그인 충돌로 단계가 실행되지 않아 성공으로 인정하지 않았습니다. 교정 후 실제 단계·JUnit·산출물을 확인했고, 전용 status credential을 등록해 Actions 게시 gate에 연결했습니다. Actions가 유일한 이미지 게시자이며 사용자 승인으로 Actions의 PR 생성·승인 허용 설정과 draft GitOps PR 제안을 활성화했습니다. 워크플로는 PR을 자동 승인하거나 병합하지 않습니다. [정상 배포와 실패 차단](evidence/cicd-gate/README.md)을 확인합니다.

## 지금 접속하기

공개 결과는 [포트폴리오](https://devdooly.github.io/devdooly-platform-lab/)에서 볼 수 있습니다. 새 작업/export 카드는 실제 배포 환경 `MINI_PC / DEPLOYED_RUNTIME`의 마지막 HTTP 관측을 표시합니다. 앞선 재시작 검증의 두 번째 원래 주기 게시에서는 고정 fixture 3개 작업의 EXPORTED·새 worker 시작 시각·저장 확인 시각과 파일 정보 6개를 확인했습니다. 공개 JSON은 실제 수집 원본과 일치하며 미니 PC 실시간 API를 브라우저에 연결한 화면은 아닙니다. 수집은 약 30분 주기로 구성했고 heartbeat 경고 기준은 5분입니다. 새 job의 원래 timer 자동 수집·게시 2회와 완료 간격 1개(1809.371239초)를 확인했습니다. [후속 검증 근거](evidence/runtime-recovery/README.md)는 과거 플랫폼 collector 11회와 구분합니다.

기존 플랫폼 관측의 초기 공개·반복 실행 기록은 다음과 같습니다. 기존 **미니 PC에서 확인한 마지막 기록**은 정적 앱 관측본이며 실시간 상태는 아닙니다. 새 플랫폼 관측본은 공개 브라우저와 게시 순서 보존을 검증했습니다. 최초 timer 자동 수집 `2026-10-12T01:38:38.790231Z`의 전체 JSON과 브라우저 표시가 일치했습니다. 이후 서비스 실행 완료 시각 기준 01:38:40~06:45:29 UTC의 11회가 모두 Pages build·deploy success였고 약 30~31분 간격을 확인했습니다. 당시 추가 수집 `2026-10-12T07:16:23.800530Z`도 전체 공개 JSON·브라우저 재조회로 확인했습니다. timer는 enabled·active이며 장기간 운영과 자격증명 만료·회전은 후속입니다. API의 플랫폼 `NOT_CONFIGURED`는 조회 API 내부의 상태 수집이 연결되지 않았음을 뜻하며 별도 정적 collector의 결과로 이 값을 바꾸지 않습니다.

관리 화면은 [SSH 접속 도우미](runbooks/admin-access.md)를 사용합니다. 본인 PC에 준비한 `.local/open-admin.ps1`을 실행한 동안 Jenkins는 `http://127.0.0.1:18081`, Argo CD는 `https://127.0.0.1:18443`에서 접속합니다. 초기 로그인 정보는 미니 PC 프로젝트의 `.local/admin/`에 0600 파일로 보관합니다. 비밀번호를 채팅이나 Git으로 옮기지 않습니다.

Argo CD 자체 서명 인증서는 접속 안내에 따라 서버 인증서 지문을 대조합니다. 오래된 CA가 남아 있던 사용자 kubeconfig는 원본을 백업하고, 사용자 승인 후 현재 K3s 전용 0600 설정으로 교정했습니다. 현재 context는 `devdooly-platform-lab`이며 시스템 Helm·Docker·프록시는 유지합니다.

DB 작업/outbox·단일 슬롯 → Garage 원본 보관 → Kafka 전달·DB 처리·수동 offset → 결과/실패 두 파일 확인·슬롯 해제를 단계별 격리 검증한 뒤 실제 K3s에 배포했습니다. 이전 검증은 [DB](evidence/db-job-foundation/README.md), [원본 S3](evidence/s3-source-storage/README.md), [MariaDB/Garage 결합](evidence/mariadb-s3/README.md), [Kafka 중단·재전달](evidence/kafka-redelivery/README.md), [export](evidence/result-export/README.md), [상시 실행·영속 정지/재개](evidence/continuous-runtime/README.md)에 보존했습니다. 최초 배포 API와 worker의 source commit·image digest, 당시 두 작업·파일·offset과 기존 환경 보존은 [최초 배포 근거](evidence/runtime-deployment/README.md)에 남겼습니다. 공개 실행·POST는 없으며 fixture 접수는 내부 `--lab-runtime=stage` 명령으로 제한합니다.

실제 K3s worker의 작업 없는 정상 재시작도 검증했습니다. 기존 Pod를 UID 조건으로만 삭제해 STOPPED·정상 TERM 종료를 관측했고 같은 image/source의 새 Pod가 RUNNING·새 시작 시각·전진하는 heartbeat를 남겼습니다. 기존 두 작업의 전체 행·시각과 파일 4개·Kafka offset을 보존했습니다. [재시작 근거](evidence/runtime-recovery/README.md), [관측·실행 절차](runbooks/continuous-runtime.md)를 따릅니다. 진행 중 작업의 강제 종료나 전체 PVC 복원을 검증한 결과는 아닙니다.

교체된 worker에 별도 고정 fixture `lab-fixture-20261015-recovery`를 접수해 입력 12 = 성공 7 + 실패 3 + 업무상 중복 2 + 대기 0, EXPORTED와 슬롯 해제를 확인했습니다. 새 결과·실패 파일 2개도 실제 Get의 전체 내용·크기·SHA-256을 대조했습니다. 전체 작업은 3개·확인 파일 6개가 됐고 Kafka offset 3·log end 3·lag 0입니다. 원래 두 작업의 전체 SQL·시각·HTTP 요약과 파일 4개는 그대로 보존했습니다. [후속 처리 근거](evidence/runtime-recovery/README.md)를 따릅니다.

Kafka·Garage의 전용 PVC 3개는 외부 사본에서 새 볼륨으로 복원했습니다. 기존 9개 객체의 inline 복원과 별도 clone의 128KiB data 블록 복원을 구분하며 원본 객체를 재Put하지 않았습니다. [PVC 복원 결과와 한계](evidence/runtime-pvc-restore/README.md), [실행 절차](runbooks/runtime-pvc-recovery.md)를 따릅니다. 운영 PVC를 덮어쓰거나 K3s/Jenkins 전체를 복원한 결과는 아닙니다.

별도 Linux worker의 부분 export 중단·복구도 검증했습니다. 결과 파일 확인 후 실패 파일 PUT을 Garage에 전달하기 직전에 SIGKILL 1회로 중단했고 동일 JAR로 pending export만 완료했습니다. 격리 검사 12/12와 운영 보존 18/18을 통과했으며 [중단 경계와 한계](evidence/maximum-export-crash/README.md)를 따릅니다. 진행 중 호스트 재부팅과 구분합니다.

## 다음 작업

**다음 작업 지점(2026-10-18):** 소스 `e89a858d`의 [여덟 번째 capture](evidence/iceberg-capture/ATTEMPT_8.md)은 기본 CI·Linux86·UID0·skip0·source 전후 동일과 prep·원래 main 한 번/반환0·새 decoder 정지/CLI 회수를 확인했습니다. 전체 capture는 SUMMARY_NOT_VERIFIED/NORMALIZE_DECODER_REPLY_JSON_UNVERIFIED 실패입니다. 코드는 strict JSON 검증 구간이며 원인·decoder exit·graph·통합 actors/clock·inventory·전체 KEEP은 미확인, 관측 count·정규화 hash는 null입니다. 다음은 공개 source의 응답 protocol 검토이며 수정 범위는 아직 미정입니다. [절차](runbooks/iceberg-closed-copy-capture.md)에 따라 이전1–7 기록을 보존하며 계정 잔여60%에서 안전하게 중단합니다.

[다음 개발 계획](NEXT_STEPS.md)에 우선순위와 단계별 결과물·완료 조건을 정리했습니다.

1. 초기 관리자 비밀번호 변경과 본인 관리 화면 로그인 확인
2. 확보한 외부 백업의 추가 물리 장치 사본과 K3s·Jenkins archive 전체 복원 검토
3. 전용 status credential의 만료·회전과 게시 산출물 보존 운영 정리
4. Pages 자격증명의 실제 만료·회전과 장기간 반복 운영 검증
5. 필요한 경우 기존 프록시·DDNS·TLS 조건을 확인한 뒤 공개 읽기 API와 외부망 검증
6. [보존·자원 기준](runbooks/retention-resource-budget.md)을 유지하며 객체 GC·요청 빈도 제한·과부하 용량·진행 중 장애와 AI 합성 예제의 사람 검토를 이어가기. [새 Cloud 연결·작은 compaction](evidence/cloud-lakehouse/FULL_SUCCESS.md)과 [현재 DB 백업·격리 복원 공개 기록](evidence/current-db-restore/README.md)은 완료했으며 다음은 [실제 closed-copy capture와 순수 보존 계획 연결](runbooks/iceberg-closed-copy-capture.md). snapshot 만료·객체 GC는 미실행이며 미니 PC native7의 중지된 시험 환경과 보관 자료는 유지하기

CI/CD의 정상 배포·실패 차단·이전 digest 복구를 확인했으며, 3단계는 제한된 실제 수집·인증 실패·회복과 수동 공개 게시·브라우저를 확인했습니다. 게시 순서 회귀 교정 후 실제 재검증도 완료했고 API·웹 중단·같은 정상 B 복원도 확인했고 정기 운영 검증을 이어가며 새로운 inbound 경로는 열지 않았습니다. 기존 서비스가 있으므로 재부팅·방화벽 변경·프록시 교체를 일괄 실행하지 않습니다. Windows 외부 사본의 무결성, 격리 DB 복원과 호스트 재부팅을 검증했습니다. K3s·Jenkins archive 전체 복원은 아직 별도 작업입니다. PV의 Delete 정책 때문에 PVC·namespace를 수동 삭제하면 데이터가 지워질 수 있습니다.

## 관련 자료

- [전체 계획](PROJECT_PLAN.md), [배포 결정](adr/0003-gitops-in-existing-repository.md)
- [API 계약](contracts/demo-api.md), [API 검증](evidence/api-mvp/README.md)
- [화면 검증](../apps/lab-web/VALIDATION.md), [관측 기록 계약](../apps/lab-web/OBSERVATION.md)
- [플랫폼 관측 계약](../apps/lab-web/PLATFORM_OBSERVATION.md), [실제 수집 검증](evidence/platform-observation/README.md)
- [플랫폼 관측 수집·게시 운영](runbooks/platform-observation.md)
- [상시 worker 실행](runbooks/continuous-runtime.md), [이전 V2 배포·job 공개 관측](evidence/input-v2-deployment/README.md)
- [보존 정책과 자원 예산](runbooks/retention-resource-budget.md), [실제 정리·측정 근거](evidence/retention-resource-budget/README.md)
- [최대 입력·동시 접수와 별도 Linux 자원/지연 검증](evidence/input-concurrency-load/README.md)
- [Kafka/Garage PVC 격리 복원](runbooks/runtime-pvc-recovery.md), [외부 사본·블록 복원 근거](evidence/runtime-pvc-restore/README.md)
- [K3s bootstrap](runbooks/k3s-bootstrap.md), [플랫폼 설치](runbooks/platform-install.md)
- [이미지 게시](runbooks/image-publication.md), [앱 Helm](runbooks/app-helm.md)

## 객체 보호의 현재 범위

[객체 참조 보호·격리 GC](evidence/object-reference-gc/README.md)는 전체 운영 DB·S3 LIST 21객체의 KEEP/후보0 검증과 새 disposable Garage의 자연 블록 회수 검증을 구분합니다. 공개 계획기는 network·삭제 기능 없는 dry-run이며 기존 보존 검사 31개와 신규 20개가 함께 통과했습니다. 운영 객체 삭제 프로토콜은 별도 후속입니다.
