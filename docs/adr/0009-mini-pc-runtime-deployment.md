# 0009 미니 PC 상시 실행기와 내부 데이터 서비스 배포

날짜: 2026-10-15

## 결정

기존 K3s의 `platform-lab` namespace에 Kafka·Garage StatefulSet과 worker Deployment를 추가한다. Kafka 1개 partition·복제 1개와 Garage 복제 1개를 사용하는 개인 합성 데이터 Lab이다. 분산 고가용성을 주장하지 않는다.

Kafka·Garage는 ClusterIP로만 연결하고 외부 포트는 만들지 않는다. 고정 image digest, 전용 영속 PVC와 서버에서 만든 Secret을 사용한다. 기존 Docker·DB·PVC·프록시·방화벽을 보존한다.

Jenkins와 Actions에서 같은 현재 main SHA 검증이 모두 성공한 API image를 worker에도 고정한다. Argo CD가 Helm 선언을 적용하며 Jenkins는 배포하지 않는다. worker는 1개 replica·Recreate·300초 종료 유예로 명시적 CLI를 실행하고, MariaDB named lock을 추가 소유권 검사로 사용한다.

이미지 자동 제안의 기존 엄격한 파일 형식을 유지하기 위해 `home-lab/values.yaml`은 API/web image 입력만 가진다. runtime 설정·실행기 image/source SHA는 별도 `runtime.yaml`에 둔다. 이미지 제안이 worker pin을 암묵적으로 바꾸지 않는다.

## 순서와 공개 범위

1. 기존 DB·K3s의 새 백업과 외부 암호화 사본을 검증한다.
2. Kafka·Garage를 먼저 준비하고 전용 topic·bucket·자격증명을 만든다.
3. 검증된 API image로 V2·V3 migration을 적용한다. worker CLI는 migration을 수행하지 않는다.
4. 같은 검증 image의 worker를 시작하고 내부 `--lab-runtime=stage`로 고정 합성 입력 12건을 등록한다.
5. Kafka 수신·DB 처리·결과/실패 파일 GET 검증·슬롯 해제와 기존 서비스 보존을 확인한다.
6. 최소 읽기 수집기로 실제 `/api/jobs/observation`을 수집하여 Pages에 게시한다. 공개 POST·작업 실행·관리자 자격증명을 제공하지 않는다.

공개 페이지는 30분 주기의 마지막 DB 관측 기록이다. 현재 프로세스 생존이나 저장소 가용성을 실시간 증명하지 않는다. 파일 SHA/크기는 DB 결과에서 재계산하고 저장 확인 commit 시각을 구분한다. 수집·게시 실패나 오래된 입력에서는 마지막 유효 기록과 원래 시각을 보존한다.

## 복구 한계

PVC retention은 StatefulSet 삭제·scale-down에 대한 보호이다. local-path PV의 Delete reclaim policy, 디스크 고장·호스트 유실에 대한 백업을 대신하지 않는다. Kafka/Garage PVC의 완전 복원과 여러 노드 장애 복구는 후속 검증이다. PAUSED_OPERATOR는 원인과 데이터 상태를 확인한 뒤 명시적으로 resume한다.

실제 배포 결과는 별도 [검증 근거](../evidence/runtime-deployment/README.md)에 기록한다.
