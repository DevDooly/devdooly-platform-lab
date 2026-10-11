# 개인 Lab 배포 상태

기존 저장소에서 앱 소스와 배포 설정을 함께 관리합니다. Argo CD는 main의 Helm chart와 환경 values를 읽습니다. 이미지에는 실제 게시 digest를 사용하고 비밀번호·인증 토큰·서버 주소를 Git에 넣지 않습니다.

- [프로젝트 범위](bootstrap/project.yaml): 새 platform-lab namespace와 필요한 리소스 종류만 허용
- [Application](bootstrap/application.yaml): chart·values의 Git 변경 자동 동기화, 자동 삭제 안 함
- [실제 이미지 값](environments/home-lab/values.yaml): 게시한 API·웹 digest와 source commit
- [이미지 게시](../docs/runbooks/image-publication.md)
- [배포 결정](../docs/adr/0003-gitops-in-existing-repository.md)

namespace와 platform-lab-db Secret은 최초 배포 전에 서버에서 준비합니다. Secret의 app-password·root-password 값은 Git과 Helm values에 넣지 않습니다. bootstrap에는 Application finalizer를 넣지 않았고 자동 prune도 꺼두었습니다. 이 설정이 namespace/PVC의 수동 삭제를 막아주지는 않습니다.

이미지 게시, Argo 동기화, Pod readiness와 실제 API 결과는 각각 확인해야 합니다. 현재 진행과 검증 결과는 저장소의 진행 목록과 근거 문서를 따릅니다.
