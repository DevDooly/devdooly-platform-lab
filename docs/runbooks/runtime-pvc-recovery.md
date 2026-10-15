# Kafka·Garage PVC 격리 복원

이 절차는 원본 저장소를 덮어쓰지 않고 cold checkpoint를 새 namespace·새 PVC에서 검증하기 위한 것입니다. [2026-10-15 실제 결과](../evidence/runtime-pvc-restore/README.md), [기존 암호화 백업](encrypted-backup.md), [DB 복구 절차](lab-recovery.md)를 함께 봅니다. 고정된 private helper와 원문 결과는 Git 제외 경로에 보관하며, 이 문서는 비밀 없는 재현 순서입니다.

## 준비

1. 현재 context·namespace·소유 workload·원본 PVC/PV UID와 실제 provisioner 경로를 읽습니다. 기본 K3s 경로라고 추정하지 않습니다. Docker·다른 서비스·boot·방화벽·Argo 정책·관측 timer의 기준을 보관합니다.
2. 슬롯이 비고 처리·export 대기가 없으며 outbox가 ACK인지 확인합니다. DB business 행 전체와 시각, 작업 DTO, Kafka offset·메시지 전체 bytes, Garage 객체 GET을 보관합니다. 객체 크기를 확인해 inline 검증과 실제 data block 검증을 구분합니다.
3. 추가 PVC의 요청량과 실제 점유량, 디스크·inode 여유를 점검합니다. 입력·출력 파일은 root 0700 디렉터리와 0600 파일에 생성하고 기존 결과가 있으면 덮어쓰지 않습니다.

## Cold checkpoint와 원본 재개

1. 변경 전 Argo Application UID·spec·현재 operation을 확인합니다. 자동 sync를 잠시 멈출 경우 기존 정책 원문을 보관하고 finally에서 되돌립니다. 다른 GitOps controller가 이를 즉시 덮어쓰는 구조면 먼저 해결합니다.
2. 새 작업 추가를 멈춘 유지보수 상태에서 소유한 worker·Kafka·Garage를 정상 종료합니다. 종료 marker/exit와 Pod 부재를 확인하기 전에는 복사를 시작하지 않습니다. 강제 종료를 정상 checkpoint로 기록하지 않습니다.
3. Kafka PVC에는 KRaft metadata·로그·consumer offsets를 포함합니다. Garage는 node identity·metadata DB와 WAL·layout·data 디렉터리를 함께 보관합니다. 실행 프로세스가 없는 동안 regular file·디렉터리 전체 manifest를 생성하고 POSIX sparse archive로 소유자·권한·고해상도 시각을 유지합니다. 링크·특수 파일·예상 외 경로는 거부합니다.
4. tar 전후 manifest가 같은지 비교하고 관련 Secret·실제 설정·DB checkpoint와 묶어 전체 SHA-256을 기록합니다. Kafka·Garage·worker 순서로 재개하고 기존 자동 정책·업무 SQL·runtime 신호를 확인합니다. 원본 재개 실패를 남겨 둔 채 시험 복원을 계속하지 않습니다.
5. archive를 외부 PC로 가져와 AES-256-GCM으로 암호화합니다. 키는 백업과 별도로 보관합니다. 저장한 암호화 파일을 다시 읽어 인증·복호화하고 원본 SHA를 대조합니다. 그 복호화 bytes 자체를 서버의 새 복원 입력으로 돌려보냅니다.

## 새 환경의 격리와 복원

1. 새 namespace·ownership label·ResourceQuota를 생성합니다. Secret 없는 probe의 원본 broker/controller·S3·DB Pod IP/Service IP 접속을 먼저 확인합니다.
2. default deny ingress/egress, 같은 namespace와 DNS만 허용하는 정책을 적용합니다. 같은 probe의 원본 접속이 실제 차단되는지 반복 확인하고 원본이 살아 있는 양성 대조를 동시에 수행합니다. probe를 UID 조건으로 종료한 뒤 Secret을 넣습니다. hostNetwork·privileged·SA token mount를 사용하지 않습니다.
3. 새 PVC를 bind하고 PVC/PV UID·claimRef·실제 경로가 원본 및 다른 복원본과 완전히 다른지 확인합니다. 시험 PV를 Retain으로 지정하고 populator 종료·Pod 부재를 확인합니다.
4. archive의 항목 allowlist·크기·regular type·상대 경로를 검증합니다. 절대 경로·상위 경로 이동·symlink·hardlink·특수 파일을 거부합니다. 빈 새 저장소에 복원하고 시작 전 전체 파일 manifest를 비교합니다.
5. Kafka는 같은 cluster/node/directory ID의 복구 저장소를 재포맷하지 않고 직접 실행합니다. advertised listener·controller voter 주소는 격리 환경을 가리켜야 합니다. Garage RPC는 loopback으로 고정하고 peer discovery가 없음을 확인합니다. 원본 cluster join 가능성이 남으면 실행하지 않습니다.
6. 원본과 Kafka 메시지 전체 bytes·timestamp·partition·offset, consumer group/committed offset·log end·lag를 대조합니다. 수동 partition 읽기·auto commit 비활성으로 검증하고 produce·offset reset·새 group 생성은 피합니다. Pod를 정상 교체한 뒤 동일 PVC와 데이터를 다시 확인합니다.
7. Garage의 원본 객체를 새 GET으로 읽어 전체 bytes·크기·SHA·identity를 대조합니다. 모두 inline이면 이 결과만으로 data block 복원을 입증하지 않습니다. 격리 복원본에만 큰 canary를 한 번 쓰고 정상 종료→metadata/data cold copy→또 다른 새 PVC 두 개 복원→GET→Pod 교체 후 GET을 추가합니다.

## 종료와 보존

1. 원본 객체를 마지막으로 새 GET하고 전체 business SQL·작업·offset·원본 PVC/PV·workload·다른 Pod·Docker·host·Argo·timer 기준을 대조합니다. 의도한 cold maintenance Pod 교체와 무관한 재시작을 구분합니다.
2. 소유한 시험 StatefulSet만 UID·spec 조건으로 replica 0으로 만들고 시험 Pod 0개를 확인합니다. 원본 PVC와 namespace는 삭제하지 않습니다. 시험 PVC·PV Retain 여부와 실제 디스크 점유량을 기록합니다.
3. 암호화 백업 보존 기한·키 회전·시험 PVC 삭제 시점을 별도 정합니다. 만료 시 시험 namespace UID·PV claimRef·경로 소유를 다시 검증하고 승인된 시험 자료만 정리합니다.
4. 공개 근거는 허용한 수량·시각·SHA·통과 여부만 남깁니다. Secret, kubeconfig, 내부 주소, 저장 경로, 전체 SQL·payload·로그는 게시하지 않습니다.

실패나 타임아웃이 발생하면 단계별 private marker와 실제 리소스를 확인합니다. 상태를 모르는 PUT·archive·namespace 생성·삭제를 통째로 재실행하지 않습니다. 원본 복귀를 최우선으로 하고 실패 결과는 그대로 보존합니다.
