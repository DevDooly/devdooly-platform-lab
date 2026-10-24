# 서비스 화면 접속 안내

2026-10-24 09:04 KST 확인. [공개 서비스 목차](https://devdooly.github.io/devdooly-platform-lab/#services)에서 설치 구성, 공개 조회, 로그인 관리 화면과 보류 항목을 찾아갑니다. 아래 결과는 이 시점의 확인이며 상시 가용성·자연 인증서 갱신·재부팅 검증은 아닙니다.

| 화면 | 접속 | 로그인·확인 범위 |
| --- | --- | --- |
| Java REST API 안내 | [API 명세·직접 조회](https://devdooly.github.io/devdooly-platform-lab/api-guide/) | 공개 GET 6개만 사용자 클릭으로 요청. 실제 JSON·HTTP·수신/관측 시각·복사. Swagger 의존성을 추가하지 않은 조회 페이지 |
| Jenkins | [Jenkins UI](https://jenkins.devdooly-platform-lab.duckdns.org/login) | 기존 Jenkins 계정. 로그인 폼 200, 익명 `/api/json` 403 |
| Argo CD | [Argo CD UI](https://argocd.devdooly-platform-lab.duckdns.org/) | 기존 Argo CD 계정. UI HTML 200, 익명 applications API 401 |
| Kafka · Kafbat | [Kafbat UI](https://kafka.devdooly-platform-lab.duckdns.org/) | 브라우저 기본 인증 `lab-viewer`. 익명 HTML/API 401, 인증 후 UI·cluster·topics·consumer groups GET 200 |
| worker·export | [작업 관측](https://devdooly.github.io/devdooly-platform-lab/#job-observation) | 독립 관리 UI 대신 공개된 작업·export 상태와 출처·관측 시각 |
| MariaDB·Garage | [DB 복원](https://devdooly.github.io/devdooly-platform-lab/#db-restore) · [S3 전송](https://devdooly.github.io/devdooly-platform-lab/#s3-transport) | DB/S3 관리 포트를 공개하지 않고 기존 검증 기록과 조회 화면으로 연결 |

## 계정 확인

Jenkins·Argo CD는 계정이나 비밀번호를 변경하지 않았습니다. 기존 계정을 사용합니다. 초기 계정 파일의 확인 방법은 [기존 접속 안내](admin-access.md#최초-로그인과-tls-지문-확인)에 있습니다. 로그인한 계정의 권한에 따라 변경 기능도 보이므로 두 도구를 읽기 전용 UI로 설명하지 않습니다.

Kafka의 새 임의 비밀번호는 미니 PC의 rudy 전용 `~/.config/devdooly-platform-lab/kafbat-login.txt`에만 저장했습니다(권한 0600). 미니 PC의 본인 터미널에서 다음 명령으로 확인하고 브라우저 로그인 창에 직접 입력합니다.

```sh
cat ~/.config/devdooly-platform-lab/kafbat-login.txt
```

비밀번호·bcrypt 원문은 채팅·Git·공개 문서·화면 캡처에 넣지 않습니다. Kafka 인증은 해당 호스트의 모든 경로에 적용하며 upstream으로 Authorization을 전달하지 않습니다. Jenkins·Argo CD의 기본 인증 헤더와 세션은 별도로 유지합니다.

## 연결 구조와 보존

기존 Traefik 3.6의 file provider에 세 호스트의 HTTPS 라우트와 HTTP→HTTPS 리다이렉트만 추가했습니다. 기존 HTTP-01 resolver가 각 호스트 인증서를 발급했으며 외부 클라이언트의 기본 CA·hostname 검증을 통과했습니다. 새 공개 포트·NodePort·Ingress는 추가하지 않았습니다.

Jenkins·Argo CD는 기존 ClusterIP를 사용합니다. Argo upstream은 공개 `tls.crt`를 CA로 사용하고 `serverName: argocd-server`를 검증합니다. `insecureSkipVerify`나 Argo의 TLS 비활성화를 사용하지 않습니다. 해당 내부 인증서가 바뀌면 공개 인증서를 다시 확인해 trust 파일을 갱신해야 하며 현재 등록이 자동 갱신을 보장하지 않습니다.

Kafka에는 [별도 고정 manifest](../../infra/service-console/kafbat/manifests.yaml)로 ConfigMap·Deployment·ClusterIP만 추가했습니다. 기존 Argo Application이나 Helm release에 UI를 편입하지 않은 독립 배포입니다. 기존 API·worker·web·Kafka 이미지/source pin, 기존 workload 사양·UID, 기존 Traefik 파일은 전후 비교에서 같았습니다. 운영 주소·인증 파일·원본 점검은 비공개 경로에 보관합니다. [라우트 예시](../../infra/service-console/traefik.example.yaml)는 주소·비밀번호가 없는 설명용 템플릿입니다.

새 UI는 `read-only: true`, cluster ONLINE, 토픽·consumer group 각 1개를 조회했습니다. 이는 Kafbat 서버의 제한이며 broker ACL 보장은 아닙니다. 데이터 생성·발행·offset 변경·장애 주입은 하지 않았습니다. 처음 잘못 요청한 `/consumer-groups`는 404였고 이를 보존했습니다. 고정 버전 계약의 `/consumer-groups/paged`로 정정한 별도 GET은 200이었습니다. [Kafka 배포·한계](service-console-kafka.md)를 함께 읽습니다.

## 화면 확인과 남은 확인

위 운영 확인은 HTTP/TLS·인증 경계와 Kafka 인증 후 GET입니다. Jenkins·Argo CD의 로그인 후 조작이나 배포·빌드를 실행한 결과는 아닙니다. 공개 API 페이지와 서비스 목차의 브라우저·배포 결과는 PR과 후속 공개 확인 기록을 따릅니다. 현재 UI URL은 인증 후 접근용이며 공개 관측 JSON의 상태를 대체하지 않습니다.

Pages 토큰 교체·별도 환경 K3s/Jenkins 기동 복원·전체 자원 예산 정책·PR #102 보류는 유지합니다. 기존 이미지 제안 PR·일시 중지 자동화·기존 서비스/자료는 변경하지 않았습니다.

## 공식 근거

- [Traefik BasicAuth](https://doc.traefik.io/traefik/reference/routing-configuration/http/middlewares/basicauth/): Kafka bcrypt usersFile과 removeHeader
- [Traefik ServersTransport](https://doc.traefik.io/traefik/reference/routing-configuration/http/load-balancing/serverstransport/): Argo serverName·rootCAs
- [Jenkins reverse proxy](https://www.jenkins.io/doc/book/system-administration/reverse-proxy-configuration-troubleshooting/): 원 Host·HTTPS 전달과 URL 일치 점검
- [Kafbat 고정 버전 consumer group 계약](https://github.com/kafbat/kafka-ui/blob/afc9c918e13c4422268a3a5b7933c7b448746c82/contract-typespec/api/consumer-groups.tsp)