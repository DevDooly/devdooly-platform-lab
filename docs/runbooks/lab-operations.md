# 운영 대상 확인과 복구 경계

현재 개인 Lab은 Ubuntu의 단일 K3s 노드이며 기존 Docker 서비스와 같은 장비를 사용합니다. Lab 전용 데이터 루트는 bootstrap 기본값인 `/var/lib/devdooly-platform-lab`, 백업 루트는 `/var/backups/devdooly-platform-lab`입니다. 실제 SSH 주소·계정·호스트 지문·CA 지문·원문 진단·복구 키는 Git에서 제외한 개인 운영 기록에 보관합니다.

## 작업 전 확인

사용자 kubectl의 현재 context는 `devdooly-platform-lab`입니다. 사용자 kubeconfig는 본인만 읽는 0600으로 유지합니다. context 이름만으로 실제 대상을 확정하지 않고 node·namespace와 CA도 함께 확인합니다.

```sh
kubectl config current-context
kubectl get nodes
kubectl get namespaces
kubectl config view --minify --raw -o jsonpath='{.clusters[0].cluster.certificate-authority-data}' | base64 -d | openssl x509 -noout -fingerprint -sha256
```

마지막 명령은 CA 인증서 지문만 출력합니다. `kubectl config view --raw` 전체 결과에는 관리자 인증 자료가 포함되므로 공개 로그에 남기지 않습니다. 기록한 CA와 다르거나 인증 오류가 나면 서버의 현재 K3s 설정과 사용자 설정을 비교한 뒤 접속 설정부터 교정합니다. 클러스터나 kubectl을 지우는 방법으로 대응하지 않습니다.

설치 설정·systemd unit·실제 데이터 루트도 비공개로 대조합니다. 실행 중인 Docker 서비스와 마운트, K3s PVC UID와 PV의 실제 경로를 함께 기록합니다. [관리 화면 접속](admin-access.md)은 SSH 터널을 사용합니다.

## 백업과 검증

[백업·격리 복원 CLI](lab-recovery.md)는 운영 DB와 K3s SQLite 자료의 새 로컬 백업을 만들고 선택한 SQL을 분리된 시험 공간에 복원합니다. 비밀번호나 원문 Secret을 출력하지 않습니다. [암호문 검증 도구](encrypted-backup.md)는 외부 파일의 인증·해시 확인과 복호화만 담당합니다.

현재 Windows의 외부 사본과 복구 키는 OneDrive 밖의 서로 다른 비공개 위치에 있습니다. Jenkins Home 백업은 controller만 중지한 상태에서 만들었고 master.key는 일반 archive에서 제외해 별도로 암호화했습니다. K3s는 SQLite 자료와 server token을 같은 복구 단위로 보관합니다.

[실제 검증 기록](../evidence/recovery/README.md)은 외부 파일의 인증·해시, 서버의 새 dump로 수행한 격리 DB 복원, 호스트 재부팅을 구분합니다. K3s·Jenkins archive 전체 복원과 외부 암호문→K3s 통합 복구, 다른 물리 장치의 추가 사본은 아직 검증하지 않았습니다.

## 호스트 재부팅

재부팅은 기존 Docker 서비스도 일시 중단하므로 실행 시점을 사용자와 확인합니다. 이번 검증에서는 Docker 23개 중 자동 재시작 설정이 없는 1개를 사전에 확인하고, 재부팅 후 같은 컨테이너를 다시 시작했습니다.

재부팅 전 boot ID·컨테이너 ID·restart policy·마운트·PVC UID·SQL baseline·방화벽 상태를 비공개로 기록합니다. 재부팅 후 node와 Pod Ready, Argo CD Synced·Healthy, 기존 Docker 실행·마운트, PVC UID와 SQL·HTTP 결과, 사용자 kubectl과 방화벽을 다시 비교합니다. 기존 서비스별 전체 업무 기능 검증과는 구분합니다.

초기 Jenkins·Argo CD 관리자 비밀번호는 아직 유효합니다. 교체와 복구 기록 갱신을 별도 작업으로 남깁니다. 백업·재부팅 성공을 비밀번호 교체 완료로 표시하지 않습니다.
