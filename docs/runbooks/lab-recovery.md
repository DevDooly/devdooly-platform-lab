# Lab 백업과 격리 DB 복원 CLI

두 스크립트는 Ubuntu Lab 호스트에서 root 권한으로 실행하며 Python 3.10 이상의 표준 라이브러리를 사용합니다. 설치된 `k3s`, `tar`와 실제 DB Pod의 `mariadb`·`mariadb-dump`를 사용합니다. 비밀번호를 인자로 전달하거나 원문 Secret을 출력하지 않습니다.

이 CLI는 현재의 개인 합성 샘플 **run 1건·outcome 12건**을 대상으로 합니다. 다른 데이터나 storage backend에 자동 확장하지 않습니다. 운영 앱·Jenkins·K3s를 중지하거나 재부팅하지 않으며 운영 PVC·namespace를 삭제하지 않습니다.

## 새 백업 만들기

```sh
sudo python3 infra/scripts/backup-lab.py \
  --data-root /var/lib/devdooly-platform-lab \
  --backup-root /var/backups/devdooly-platform-lab
```

기본 경로는 저장소 bootstrap의 Lab 전용 경로입니다. 별도 설치라면 실제 설치·데이터 경로를 확인한 뒤 두 옵션을 바꿉니다. 백업 루트는 root 전용 0700이어야 하고 데이터 루트와 겹치지 않아야 합니다. 새 `operations-<UTC>-<임의 ID>` 디렉터리를 만들므로 기존 백업을 덮어쓰지 않습니다.

백업은 다음을 포함합니다.

- InnoDB-only·single transaction MariaDB 논리 dump와 전체 SQL 비교용 baseline
- SQLite online backup과 `PRAGMA quick_check`
- K3s server token, credential·TLS 디렉터리, 설치 config·systemd unit
- 이미지 digest·SHA-256·대상·시각·완료 범위를 적은 private manifest

성공 시 stdout에는 비밀값과 경로를 제외한 요약만 출력합니다. 완성된 백업 디렉터리와 manifest는 백업 루트에서 비공개로 확인합니다. 도중 실패하면 성공 manifest를 만들지 않고 부분 파일을 비공개 디렉터리에 남깁니다. 부분 백업을 복원 대상으로 선택하지 않습니다.

이 작업은 **로컬 백업 생성**입니다. 서버 외부 전송·암호화, Jenkins Home 백업·복원, K3s 전체 복원, 호스트 재부팅을 실행하지 않습니다. K3s SQLite와 token·credential 자료의 복구 검증도 DB 격리 복원과 별도입니다.

## 선택한 백업을 새 시험 환경에 복원

아래 `SELECTED_BACKUP`과 `/path/to/repository`는 예시 입력입니다. 실제 manifest가 있는 백업 디렉터리와 독립 기대 결과 파일이 있는 저장소의 절대 경로로 바꿉니다.

```sh
sudo python3 infra/scripts/restore-lab-drill.py \
  --backup-directory /var/backups/devdooly-platform-lab/SELECTED_BACKUP \
  --repository /path/to/repository
```

`--backup-directory`와 `--repository`는 필수이며 최신 백업을 자동 선택하지 않습니다. 기본값 외의 경로에서는 `--backup-root`와 `--data-root`도 명시합니다. manifest·dump·baseline의 root 소유권, 비공개 권한, 해시를 확인한 뒤 시작합니다.

매 실행은 새 restore namespace·Secret·PVC를 만듭니다. 별도 NetworkPolicy와 자원 quota를 적용하고 NodePort·Ingress를 추가하지 않습니다. DB 및 API의 이미지 digest는 백업과 현재 운영 선언이 같아야 합니다.

검증 순서는 다음과 같습니다.

1. 운영 PVC UID와 PV mount 경로를 기록합니다.
2. 시험 API를 0으로 유지하고 시험 DB만 실행합니다.
3. 시험 PVC UID·PV claimRef UID·실제 mount 경로가 운영과 다르고, 경로가 서로 포함되지 않는지 확인합니다.
4. SQL을 import하고 API 실행 전에 전체 run·outcome·Flyway history·저장 시각을 baseline과 비교합니다.
5. 중복 INSERT의 제약 오류와 원본 데이터 불변을 확인합니다.
6. 시험 API에서 독립 시나리오의 12건과 모든 분류·사유를 비교하고, API 재시작 후 다시 확인합니다. 재수집 시각인 `observedAt`만 제외하며 `startedAt`·`completedAt`은 유지되어야 합니다.
7. 운영 PVC·mount·데이터가 그대로인지 재확인합니다.
8. 시험 workload를 0으로 내려 Pod를 모두 중지하고 시험 PV의 reclaimPolicy를 `Retain`으로 유지합니다.

시험 PVC와 Secret을 자동 삭제하지 않습니다. 결과는 선택한 비공개 백업 디렉터리의 새로운 `restore-drill-*.json`에 기록합니다. 완료 요약만 stdout에 출력합니다. 실패 시에도 소유권을 확인한 시험 workload만 중지하도록 시도합니다. 강제 종료·통신 단절 시에는 private namespace의 실제 상태를 직접 확인합니다.

## 기존 시험 환경을 명시적으로 재사용

```sh
sudo python3 infra/scripts/restore-lab-drill.py \
  --backup-directory /var/backups/devdooly-platform-lab/SELECTED_BACKUP \
  --repository /path/to/repository \
  --reuse-trial OWNED_TRIAL_NAMESPACE
```

자동 탐색·자동 재사용은 하지 않습니다. namespace·workload·Secret·PVC의 `devdooly.io/purpose=restore-drill`, 일치하는 `devdooly.io/backup-id`를 확인해야 합니다. 기존 PV에 label이 없다면 명시적으로 선택한 소유 PVC의 정확한 claimRef UID와 운영과 분리된 mount 경로를 확인한 뒤에만 PV를 표시합니다. 충돌하는 owner label, 예상하지 못한 리소스, 운영과 공유한 저장소가 있으면 중단합니다. 재사용은 시험 DB 내용을 선택한 dump로 덮어쓰는 작업입니다.

## 검증 범위

원본 운영 스크립트로 논리 dump·SQLite online snapshot과 실제 격리 DB 복원, SQL 선검증·HTTP·중복 제약·재시작 후 데이터 유지가 확인됐습니다. 호스트 재부팅은 사용자 허용 후 별도 작업으로 확인했으며 이 CLI에 재부팅 자동화를 넣지 않았습니다.

공개 CLI는 위 동작을 옵션·소유권·경로 검증으로 재구성한 버전입니다. Windows의 offline 검사 31개에서 명시 입력·owner label·PVC UID·claimRef UID·공유/중첩 mount 거부와 저장 시각 변화 탐지를 확인했습니다. 이 검사는 클러스터 명령을 실행하지 않습니다.

이후 Ubuntu에서 **공개 CLI 두 파일을 실제로 실행**했습니다. 새 논리 dump는 6,825바이트이며 백업에 0.529초가 걸렸고 SQLite online snapshot의 quick_check가 통과했습니다. 기존 소유 시험 namespace를 `--reuse-trial`로 명시해 복원했으며, import 0.268초·전체 61.046초가 걸렸습니다. SQL 전체·저장 시각·독립 기대 결과·중복 제약 오류 1062·API 재시작 후 데이터·운영 PVC/mount/data 유지·시험 Pod 0과 PV Retain을 모두 확인했습니다. 이는 작은 합성 샘플 한 번의 관측값이며 다른 크기의 복구 시간 보장이 아닙니다.

공개 CLI의 **새 시험 namespace 생성 경로는 이 추가 회귀에서 실행하지 않았습니다.** 기존 원본 스크립트에서의 격리 환경 생성 결과와 공개 CLI의 명시 재사용 회귀를 구분합니다. K3s 전체 복원·Jenkins 복원·반복 예약 백업도 이 CLI 검증에 포함하지 않습니다. 실제 주소·trial 이름·백업 경로가 포함된 원본 보고서는 Git에서 제외한 비공개 경로에 보관합니다.

공식 근거: [K3s datastore와 token 백업](https://docs.k3s.io/datastore/backup-restore), [MariaDB single-transaction dump](https://mariadb.com/docs/server/clients-and-utilities/backup-restore-and-import-clients/mariadb-dump).

[공개 CLI 실제 실행 요약](../evidence/recovery/portable-cli.json)에서 관측 필드를 확인합니다.

Offline 보호 조건 검사는 저장소 루트에서 `python tests/operations/check_recovery_guards.py`로 다시 실행합니다. Kubernetes 명령이나 서버 연결을 하지 않습니다.
