# 사용자 접속 설정과 서비스 재기동 검증

2026년 10월 11일, Ubuntu 사용자 kubectl의 오래된 연결 설정을 교정하고 K3s 서비스 재기동 후의 동작을 확인했습니다. [공개 허용 필드로 정리한 결과](summary.json)에 실제 관측 범위를 기록했습니다.

## 연결 설정 교정

기존 사용자 kubeconfig에는 2025년에 생성된 이전 클러스터 CA가 남아 있었고 current-context가 비어 있었습니다. 이전 context를 지정한 조회에서는 인증서 검증 오류가 발생했습니다. 확인 범위에서 실행 중인 별도 이전 클러스터와 kind 컨테이너는 찾지 못했습니다.

원본 설정을 백업하고 사용자 승인 후 현재 K3s 설정으로 교체했습니다. 파일은 사용자 전용 0600 권한이며 current-context는 `devdooly-platform-lab`입니다. 일반 사용자 계정의 kubectl에서 Node Ready와 전체 Pod Ready를 확인했습니다. K3s와 기존 kubectl 실행 파일은 보존했습니다.

## 재기동과 데이터 확인

- K3s Node 1개와 Pod 11개 Ready
- Jenkins·Argo CD·Lab 앱의 준비 상태와 Argo CD Synced·Healthy
- 웹 경로를 통한 API·MariaDB 조회와 기존 합성 결과 12건 유지
- 기존 Docker 실행 컨테이너 23개의 ID·시작 시각 유지
- 기존 UFW 상태와 설정 파일의 동일성

K3s 전용 데이터와 Jenkins·MariaDB 볼륨, 설정을 쓰기 중지 후 같은 서버의 root 전용 백업으로 보관했습니다. archive 목록 검증과 SHA256 기록을 확인했습니다. 비밀값과 내부 접속 정보가 포함된 백업 원본은 공개하지 않습니다.

이번 서비스 재기동은 **기존 디스크 데이터를 그대로 사용한 재기동**입니다. 백업 archive에서의 복원, 외부 백업 복사, 호스트 재부팅 복구는 별도 검증이 필요합니다. [다음 개발 계획](../../NEXT_STEPS.md)의 첫 작업으로 연결합니다.
