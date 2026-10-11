# 0003 기존 저장소에서 초기 GitOps 상태 관리

상태: 채택 · 2026-10-11

개인 단일 노드 Lab의 초기 구축에서는 기존 devdooly-platform-lab 저장소에 gitops 디렉터리를 둡니다. 추가 저장소·접근 권한 없이 소스와 배포 변경을 확인할 수 있습니다.

Argo CD는 단일 source로 main의 Helm chart와 상대 경로의 환경 values를 읽습니다. 같은 저장소의 서로 다른 revision을 조합하는 초기 설정은 실제 manifest 생성에서 거절되어 단일 source로 교정했습니다. 앱 source commit과 이미지 digest는 values에 고정하고, chart 변경은 Git diff로 검토합니다. Argo가 적용한 Git revision을 배포 근거에 기록합니다. 이미지 게시가 곧 배포 성공을 의미하지는 않습니다.

AppProject는 이 저장소와 platform-lab namespace 및 chart에 필요한 종류만 허용합니다. 비밀번호와 초기 관리 인증정보는 서버의 Secret·비공개 파일로 관리합니다. Kubernetes API·Jenkins·Argo CD는 공개 프록시에 연결하지 않습니다.

소스와 환경 설정의 쓰기 권한은 현재 분리되지 않습니다. 팀 운영이나 환경별 승인·권한 분리가 필요해지면 별도 GitOps 저장소로 이동합니다. 그때도 배포 상태와 앱 이미지의 실제 digest 연결을 유지합니다.
