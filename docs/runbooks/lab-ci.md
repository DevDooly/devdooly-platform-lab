# Linux runner에서 Lab 컨테이너 검증

GitHub의 일회성 Ubuntu runner에서 실제 MariaDB·컨테이너·Nginx DNS 갱신 검증을 통과했습니다. [성공한 실행과 공개 응답](../evidence/compose-ci/README.md)을 확인합니다. 미니 PC와 Jenkins 운영 검증은 별도입니다.

[lab-ci.yml](../../.github/workflows/lab-ci.yml)은 관련 소스가 main에 push되거나 수동 실행할 때 동작합니다. `contents: read`만 사용하며 registry 게시·배포·GitOps 변경 권한은 없습니다. Jenkins 운영 환경을 설치하거나 대체했다는 의미도 아닙니다.

## 검증 순서

1. Java 21의 공식 bin Maven Wrapper로 API verify를 실행합니다.
2. Node 24.19.0에서 lockfile 기준 npm ci, check, test, build를 실행합니다.
3. 기존 비밀번호 생성기로 `.local/compose.env`를 만들고 일회성 runner의 CI 네트워크 override를 준비합니다. 비밀번호를 출력하지 않습니다.
4. 실제 Compose 이미지를 만들고 MariaDB·API·Nginx를 실행합니다. SOURCE_COMMIT에는 해당 GitHub commit을 주입합니다.
5. 3분의 한도를 두고 동일 origin의 API와 DB·저장된 샘플 준비를 기다립니다.
6. 기존 화면 smoke를 `http://127.0.0.1:4310/`와 같은 origin의 `/api`에 연결합니다. 별도 API 주소나 정적 snapshot을 성공 결과로 대신하지 않습니다.
7. MariaDB 상태, 12건 = 성공 7 + 실패 3 + 중복 2 + 대기 0, 12개 판정, 성공 차트 7건, 공개 POST 405와 source commit을 검증합니다.
8. API의 주소를 CI override에서 바꾸고 API만 force-recreate합니다. 기존 Nginx container가 재시작되지 않은 상태로 DNS를 갱신해 새 API에 연결하는지 확인합니다.
9. 이전 처리 시각·12개 결과·목록이 그대로이고 bootstrap 중복 실행이 없는지 확인합니다. JVM 런타임 시작 시각과 API container는 바뀌어야 합니다.
10. 성공·실패와 관계없이 Compose를 down 합니다. `-v`는 사용하지 않으며 volume은 runner 폐기 시 사라집니다.

## 격리와 공개 증거

CI는 run ID별 Compose project와 `.local/compose-ci.yaml`을 사용합니다. runner 안의 전용 subnet에서 API 주소를 `.10`에서 `.11`로 바꿉니다. 단순 재생성에서 같은 IP가 다시 배정돼 DNS 검증을 건너뛰는 일을 방지합니다. 기존 홈서버의 Compose 파일·네트워크·데이터는 변경하지 않습니다.

검증 스크립트는 Docker inspect 전체를 출력하지 않고 API 주소·container ID·Nginx 시작 시각만 메모리와 `.local/`에 보관합니다. 환경변수·전체 Compose config·비밀번호 파일은 로그나 artifact로 출력하지 않습니다.

artifact는 Surefire XML과 `artifacts/compose-before.json`, `artifacts/compose-after.json`만 허용하며 7일간 보관합니다. JSON에는 공개 API 결과와 관측 시각, source commit, 검증 결과만 들어갑니다. `.local/`과 인증정보는 artifact에 포함하지 않습니다. 실패 시 container 상태만 출력합니다.

## 첫 실행 후 기록할 것

- workflow run URL, 실제 commit과 runner 환경
- API·화면 테스트 결과, 실제 MariaDB migration 및 schema validation 성공
- 같은 origin의 화면 smoke와 12개 처리 판정 결과
- API 주소 변경과 Nginx 무재시작 복구, 저장된 처리 시각·결과 보존 여부
- 실패 원인과 수정 commit, 재실행 결과

GitHub Actions의 성공 결과와 artifact를 확인한 후에만 실제 컨테이너 통합 검증 완료로 기록합니다. 이 검증은 미니 PC의 SSH 접근·K3s·Jenkins·Argo CD 설치 검증과 별개입니다.

## 고정한 공식 액션

2026-10-11 공식 저장소의 latest release와 태그 commit을 확인했습니다.

| 액션 | 릴리스 | 고정 commit |
| --- | --- | --- |
| [checkout](https://github.com/actions/checkout/releases/tag/v7.0.1) | v7.0.1 | 3d3c42e5aac5ba805825da76410c181273ba90b1 |
| [setup-java](https://github.com/actions/setup-java/releases/tag/v6.0.1) | v6.0.1 | de7274f081f381c8f8158605e0321c36c376e2e6 |
| [setup-node](https://github.com/actions/setup-node/releases/tag/v7.1.0) | v7.1.0 | 949feb2413d6458794dcd2491c4babbbce0c15c1 |
| [upload-artifact](https://github.com/actions/upload-artifact/releases/tag/v7.0.2) | v7.0.2 | cf430e030ddbb5b0abf93d22962f4752f3646cd9 |
