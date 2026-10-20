# 역사적 백업의 runtime 복원 사전준비

상태: **보류 · 별도 격리 환경 없음 · runtime 미실행**. 사용자 결정에 따라 실제 K3s·Jenkins 기동 복원은 보류한다. 실행 환경이 준비되면 대상·버전·자료와 정확한 시험 범위를 확인해 재개한다. 대상 자료는 2026-10-11 외부에 보관한 네 구성요소이며, 이후의 업무 데이터·PVC 사본·Jenkins 설정을 같은 checkpoint로 합치지 않는다.

## 실제 입력과 현재 증거

| 역사적 입력 | 인증 후 bytes | 확인한 범위 / 남은 경계 |
| --- | ---: | --- |
| MariaDB 논리 dump | 6,825 | 인증·파일 bytes 확인. 이 외부 사본의 SQL import는 미실행 |
| K3s datastore archive | 2,581,509 | SQLite snapshot·server token·credential/TLS·설치 설정. K3s binary와 모든 PV의 업무 데이터가 포함된 전체 장비 사본은 아님 |
| Jenkins Home archive | 309,657,060 | 일반 Home과 분리한 master key를 구분. controller 기동·credential 사용은 미검증 |
| 별도 Jenkins master key | 256 | 인증과 새 별도 비공개 파일의 전체 bytes 일치. 기존 Home에 넣거나 credential을 복호화하지 않음 |

[실제 파일 검증](../evidence/historical-file-restore/README.md)에서 archive member 2,688개와 regular/hardlink 1,907개의 전체 bytes·numeric owner/mode/mtime을 비교했다. 첫 실행은 SQLite 연결 전에 sidecar 부재 가정으로 실패했다. **원래 restore receipt의 `passed=false`와 exit1은 그대로 보존한다.**

후속 결과는 별도 범위다. 빈 WAL·metadata 확인 뒤 읽기 전용 SQLite integrity 검사와 명시 close를 통과했고, DB/WAL/SHM을 바꾸지 않았다. 분리 키도 새 파일 한 개로만 조립했다. 이 결과를 원래 실패의 성공이나 서비스 복구로 합치지 않는다. [허용 필드 원문](../evidence/historical-file-restore/summary.json)

## 서로 다른 네 복원 범위

| 범위 | 현재 상태 | 실제 기동 뒤 별도로 확인할 결과 |
| --- | --- | --- |
| K3s API·datastore | 파일·빈 WAL SQLite 검증 완료 / API 미검증 | 선택한 버전의 새 격리 API에서 역사적 metadata를 읽고 원본 사본을 보존했는지 |
| Jenkins controller | Home 파일 검증 완료 / controller 미검증 | 선택한 core·Java·plugin 조합으로 시작해 설정·job·빌드 기록을 읽는지. 실제 빌드·배포 성공과 구분 |
| Jenkins credential | 별도 키 파일 검증 완료 / 복호화 미검증 | 명시적으로 선택한 사본·키의 복호화 가능성. 비밀 출력이나 외부 서비스 로그인과 구분 |
| 전체 애플리케이션 | 미검증 | 같은 복구 시점의 DB·객체·각 PV·설정을 갖추고 업무 결과까지 대조하는지. API/controller 기동만으로 완료하지 않음 |

서버에서 만든 새 dump의 [격리 DB 복원](../evidence/recovery/README.md)과 이후 [Kafka·Garage PVC 복원](../evidence/runtime-pvc-restore/README.md)은 각각 별도 입력·시점의 증거다. 이들을 10월11일 백업의 전체 애플리케이션 복구 증거로 대신하지 않는다.

## 실제 기동 전 필요한 정보

- 네 범위 중 시험할 대상을 먼저 고르고, 실제 archive·분리 키를 사용할 범위와 보관 방식을 확인한다. 기존 파일 전송·파일 복원 허용을 runtime 기동·credential 사용 승인으로 확대하지 않는다.
- 재개 시 기존 서비스·저장소와 분리된 실행 대상을 정한다. 복원한 controller·설정이 기존 node·agent·job·외부 서비스에 작동하지 않는 방식, 종료와 실패 사본 보존 범위를 함께 검토한다. 현재 별도 실행 환경이 없어 기동 복원을 보류한다.
- archive와 결합할 K3s binary·Jenkins core·Java·plugin의 출처와 버전을 확인한다. [초기 K3s 관측](../evidence/mini-pc/README.md)과 [저장소 Jenkins 선언](../../infra/platform/jenkins-values.yaml)은 비교 자료이며, archive 자체에 묶인 실행 버전의 확정 증거로 취급하지 않는다.
- 전체 애플리케이션 범위라면 같은 시점의 PV·DB·객체 자료와 독립 기대 결과가 필요하다. 자료가 없으면 해당 범위는 미검증으로 남긴다.

기존 파일 전용 실행기는 제한된 새 scratch에만 쓰며 업무 서비스 시작·SQL import·네트워크를 허용하지 않는다. 고정된 첫 실행의 실패 자료도 남아 있으므로 runtime 시험용으로 재호출하거나 변경해 재사용하지 않는다. 실제 기동은 위 자료와 정확한 범위를 검토한 후 별도 계획으로 결정한다.

[백업 생성 범위와 producer](../runbooks/lab-recovery.md) · [snapshot·token·설정 수집 소스](../../infra/scripts/backup-lab.py) · [운영 복구 경계](../runbooks/lab-operations.md)
