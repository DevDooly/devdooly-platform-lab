# 호스트 구성 자동화

환경 점검 결과를 바탕으로 Ubuntu와 K3s 구성을 반복 가능하게 만들 위치입니다. 현재 inventory, playbook과 role은 없습니다.

실제 호스트 주소와 SSH 설정은 Git에서 제외되는 로컬 inventory로 관리합니다. 실행 전 기존 서비스·데이터 경로와 백업을 확인하고, 반복 실행 결과 및 원상 복구 범위를 기록합니다.

배포용 애플리케이션 Helm chart와 Argo CD 선언은 2단계에서 별도 `devdooly-platform-gitops` 저장소에 작성합니다. 제품 설치 명령이나 chart 버전은 확인된 OS와 공식 지원 범위를 기준으로 정합니다.
