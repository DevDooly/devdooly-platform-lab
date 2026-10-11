# 외부 백업·격리 DB 복원·호스트 재부팅 검증

2026년 10월 11일, 미니 PC의 백업을 Windows PC에 암호화해 보관하고 별도 DB로 복원했습니다. 이후 사용자에게 기존 서비스의 일시 중단 범위를 설명하고 재부팅 허용을 받아 복구를 확인했습니다. [허용 필드 요약](summary.json)에 관측 범위를 남깁니다.

## 백업

- 기존 cold archive 3,420,565,222바이트의 외부 사본: AES-256-GCM으로 전송 중 암호화, 암호문을 다시 읽어 GCM 인증과 평문 SHA-256 일치 확인
- 새로운 MariaDB 논리 dump 6,825바이트: InnoDB 테이블, single transaction, 전체 행과 저장 시각 기준값 보관
- 현재 K3s SQLite online backup: quick_check 통과, server token·cred·TLS·설치 설정과 함께 보관
- Jenkins Home 309,657,060바이트: 실행·대기 빌드가 없는 상태에서 controller만 중지해 생성, master.key는 일반 archive에서 제외
- DB·K3s·Jenkins·Jenkins master.key의 새 외부 암호화 사본 각각 read-back 인증과 해시 확인

외부 사본은 같은 사용자의 Windows PC이며 OneDrive 밖에 있습니다. 파일 접근은 본인·SYSTEM으로 제한하고, 암호화 복구 키와 Jenkins master.key는 일반 archive와 별도 위치에 보관합니다. 실제 주소·키·원문 로그·보관 경로는 Git에서 제외합니다. 다른 물리 장치의 추가 사본은 아직 검증하지 않았습니다.

## 격리 복원

운영과 다른 namespace·Secret·PVC에 동일 MariaDB digest를 실행했습니다. 시험 공간에는 CPU·메모리·저장공간 상한과 namespace 간 통신 제한을 적용했고 외부 포트나 Ingress는 만들지 않았습니다. 초기 메모리 quota 2Gi가 DB·API limit의 합보다 작아 API 생성이 차단됐으며, 실제 한도를 확인해 시험 공간만 3Gi로 교정했습니다.

API를 먼저 실행하면 없는 샘플을 자동 생성할 수 있으므로 **API replica=0 상태에서 dump를 복원하고 SQL을 먼저 비교**했습니다. 전체 demo_run·demo_outcome·Flyway history와 저장된 처리 시각의 일치를 확인한 뒤 API를 시작했습니다.

- run 1건, outcome 12건: 성공 7·실패 3·중복 2·대기 0
- 독립 시나리오의 모든 sequence·status·reason과 시계열 7건 일치
- 중복 INSERT가 outcome_sequence 제약 오류로 거부되고 기존 행 유지
- API 재시작 후 전체 SQL과 시작·완료 시각 유지
- 운영 PVC UID와 데이터 유지

HTTP의 observedAt은 조회 시각이므로 재시작 전후 동일성 비교에서 제외했습니다. 저장된 startedAt·completedAt과 결과는 비교에 포함했습니다. 시험 workload는 0으로 종료했으며 시험 PVC는 후속 확인을 위해 Retain 상태로 남겼습니다.

이번 DB 복원은 **서버의 새 논리 dump**를 사용했습니다. Windows의 암호문을 K3s에 되돌려 주입하는 통합 복구 시험, K3s 전체 archive 복원과 Jenkins archive 복원은 수행하지 않았습니다.

## 재부팅

기존 Docker 서비스 23개가 함께 중단된다는 점과 자동 재시작 설정이 없는 1개의 수동 복구 계획을 설명한 뒤 사용자 허용을 받았습니다. 재부팅 전 boot ID·컨테이너·마운트·PVC·DB·방화벽을 기록했습니다.

재부팅 후 boot ID 변경, Node 1·Pod 11 Ready, Argo CD Synced·Healthy를 확인했습니다. 기존 Docker 23개는 같은 ID와 마운트를 유지했고, 자동 재시작이 설정되지 않은 1개를 다시 시작했습니다. 기존 PVC UID, 전체 DB 행·처리 시각·Flyway history와 API 결과가 동일했습니다. 사용자 kubectl과 0600 설정, UFW 상태·설정도 유지했습니다.

Docker는 실행 상태와 마운트를 확인했습니다. 기존 각 서비스의 전체 업무 기능을 개별 검증했다는 뜻은 아닙니다. Jenkins·Argo CD 초기 관리자 비밀번호가 아직 유효함도 확인했으며, 이 기록은 비밀번호 교체 완료를 뜻하지 않습니다.

## 복호화 도구 검증

[복호화 안내](../../runbooks/encrypted-backup.md)와 [재사용 도구](../../../infra/scripts/encrypted-backup.py)를 제공합니다. Windows의 [20개 검사](encrypted-backup-windows.json), Ubuntu의 [합성 파일 검사](encrypted-backup-linux.json)를 구분했습니다. 인증 실패 때 평문 결과를 게시하지 않고, 기존 출력 파일을 덮어쓰지 않는지 확인했습니다.

[다음 작업](../../NEXT_STEPS.md)은 동일 SHA의 Jenkins·Actions 검증을 연결하고 GitOps 변경·실패 차단·이전 digest 복구로 이어집니다.

## 재실행 가능한 백업·복원

[백업과 복원 CLI 안내](../../runbooks/lab-recovery.md)에 실제 명령과 경로 선택·소유권 확인·종료 절차를 정리했습니다. 공개 CLI로 Ubuntu에서 새 백업을 만들고, 앞서 생성한 소유 시험 공간을 명시적으로 재사용해 회귀 검증했습니다. [실행 요약](portable-cli.json)의 백업 0.529초, SQL import 0.268초, 복원·API 재시작·시험 종료 전체 61.046초는 이 작은 샘플의 관측값입니다. 새로운 namespace를 만드는 기본 경로는 이번 CLI 회귀에서 다시 실행하지 않았습니다. 운영 데이터는 그대로 유지했습니다.

공개 복호화 도구의 `--verify-only`로 실제 3,420,565,222바이트 cold archive의 GCM 인증과 기대 SHA-256도 다시 확인했습니다. 이 검사는 평문 파일을 만들거나 archive를 복원하지 않았습니다.
