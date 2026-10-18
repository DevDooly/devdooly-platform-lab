# 공개 조회 게이트웨이 프로토타입

별도의 공개 조회 게이트웨이를 검토하기 위한 **미실행 후보**다. 기존 웹 프록시,
API 이미지, Kubernetes, 미니 PC, 공유기, DNS, 인증서, 터널, GitHub Pages 설정을
변경하지 않는다. 아래 CI 실행기도 공개 접속 주소를 만들지 않는다.

## 허용 요청

정확한 `GET`만 upstream으로 전달한다. Nginx가 해석한 다른 메서드는
`405`와 `Allow: GET`으로 거부한다. `HEAD`·`OPTIONS`도 허용하지 않는다.
소문자 `get` 등 요청 라인 해석 단계의 거부는 native 400일 수 있으며,
이때 본문까지 고정 JSON이라고 보장하지 않는다. parser 오류를 named location으로
돌리지 않는다. 유효한 헤더·entity 조건의 거부는 직접 고정 400 JSON을 반환한다.

| 경로 | 기존 백엔드의 조회 범위 |
| --- | --- |
| `/api/platform/summary` | 서비스와 DB `SELECT 1` 결과 |
| `/api/platform/releases` | 공개 API 소스·이미지 정보 |
| `/api/demo/runs` | 최근 합성 실행 결과 20개 |
| `/api/demo/runs/{id}` | 저장된 합성 결과·시계열, 실행 요청 없음 |
| `/api/jobs/observation` | 커밋된 DB 상태, worker·S3 호출 없음 |
| `/api/kafka/observation` | 기존 opt-in 설정의 고정 대상 Kafka 조회 |

상세 ID는 `[a-z0-9][a-z0-9._-]{0,79}`와 정확히 일치해야 하며 고정 샘플은
`synthetic-v1-seed-42`다. 이 Lab의 데이터는 모두 합성이며 기존 백엔드의 작업
입력은 최대 1,000개다. Demo 상세 자체는 저장된 outcome 전체를 조회한다.
게이트웨이가 DB 행 수·응답 바이트·응답 스키마·전체 응답 시간을 추가로 제한하지
않는다. 회사 데이터나 임의 데이터에 그대로 적용할 수 있는 설계로 간주하지 않는다.

원본 `$request_uri`를 대소문자 구분 정규식으로 검사한다. query와 빈 `?`,
percent encoding, dot segment, 중복 슬래시, 추가 하위 경로와 관리 경로는 차단한다.
비어 있지 않은 Authorization·Cookie·Content-Type·Transfer-Encoding·Expect와
0이 아닌 Content-Length도 거부한다. Nginx 변수는 없는 헤더와 빈 값의 헤더를
구분하지 못한다. 빈 값에는 인증 정보가 없으며 그대로 전달하지도 않는다.

원래 헤더와 body의 upstream 전달을 끄고 고정 `Host`, `Accept`, `Connection`만
재구성한다. 요청으로 접속 호스트·포트·Kafka broker/topic/group·비공개 경로를
선택할 수 없다. 리스너는 HTTP/1만 사용한다. HTTP/1 헤더·entity 검사와 upstream
body 0바이트를 검증하며, 추후 HTTPS edge의 모든 HTTP/2 DATA 거부까지 증명하지 않는다.

## CORS·제한·실패 처리

CORS Origin은 대소문자까지 `https://devdooly.github.io`와 정확히 일치해야 한다.
다른 비어 있지 않은 Origin은 403이며 Origin 없는 공개 조회 클라이언트는 허용한다.
Origin·CORS는 인증 수단이 아니다. `Vary: Origin`, `Cache-Control: no-store`를
적용하고 credentialed CORS는 허용하지 않는다. upstream 쿠키·redirect·CORS·cache
헤더를 숨기고 X-Accel 동작을 무시한다.

일반 요청은 peer별 초당 2개·burst 6개, 전체 초당 10개·burst 20개다. Kafka에는
peer별 분당 30개·burst 1개를 추가한다. 동시 처리 요청은 peer별 6개·전체 16개이며
초과하면 429다. 헤더가 해석된 처리 요청을 세므로 모든 미완성 TCP 연결 제한을
증명한 것으로 보지 않는다.

헤더·body·keepalive·전송 timeout은 5초, upstream connect/send/read timeout은
1/2/12초다. `proxy_read_timeout`은 읽기 사이의 **idle timeout**이며 전체 요청
시간 제한이 아니다. 임시 파일을 끄는 것도 응답 크기 제한은 아니다. 백엔드의
기존 실행 예산은 계속 적용한다. upstream 재시도와 cache는 사용하지 않는다.

upstream redirect·연결 중단·읽기 idle timeout·500/502/503/504는 고정 503 JSON으로
처리하고 404·429는 구분한다. parser의 이른 거부와 정책의 고정 JSON 거부는 구분한다.
현재 `/api/` 웹 프록시 전체를 공개하거나 쓰기·실행 경로를 추가하지 않는다.

후속 프런트엔드 연동에는 단순 GET·`Accept: application/json`, 명시적인
`credentials: 'omit'`, `redirect: 'error'`, live 조회 8초 취소가 필요하다.
현재 `api.ts`에 omit/error가 이미 구현됐다는 뜻은 아니다. 이 조건이면 preflight
없이 조회할 수 있다. 기존 **최근 관측 기록 → 합성 샘플** fallback을 유지하고
자동 재시도는 추가하지 않는다. 프런트엔드 변경은 이 후보에 포함하지 않았다.

## 격리된 실제 Nginx 검증

실행 대상은 검토된 **Linux amd64 CI runner**이며 미니 PC에서 실행하지 않는다.
`run_once.py`는 전달받은 manifest hash와 소스를 먼저 검증한 뒤 새 라벨이 있는
`--internal` bridge 1개와 컨테이너 최대 2개만 만든다. host port·host network·
Docker socket·자격증명·영속 volume을 연결하지 않고 DB·Kafka·Kubernetes에 접속하지
않는다. 각 컨테이너는 128MiB·0.25CPU·64PID, capability 없음, no-new-privileges,
read-only root, 16MiB tmpfs를 사용한다. 공개 fixture/config만 읽기 전용 mount한다.

게이트웨이는 기존 고정 Nginx 이미지를 재사용한다. fake upstream은 기존 Spark CI
이미지의 **stdlib Python3만** entrypoint를 바꿔 실행한다. Spark/JVM은 시작하지
않으며 이 이미지는 게이트웨이 운영 이미지가 아니다. 새 이미지·버전 도입은 없다.
`source-image-evidence.json`의 경로·hash·bytes·pin은 최종 main
`13447fa88987050f64e47c01684ecb9c233b34fb`의 실제 Git blob과 대조됐다. 이미지가
없으면 digest로 내려받은 후 격리 네트워크를 시작한다.

fake server와 stdlib HTTP probe는 같은 컨테이너에 있다. 다른 컨테이너의 실제
Nginx에 요청하여 6개 경로 패턴·80자 ID, 차단 경로·메서드·헤더, upstream 고정
헤더·body 0바이트, CORS·쿠키·redirect, rate·동시성 거부, 연결 중단·500·느린 응답의
고정503과 실패당 upstream 1회 호출을 확인한다. `CONNECT /api/...`와 `TRACE`는
해석 후 405, 소문자 `get`은 parser 400으로 구분해 upstream 호출 0을 검증한다.
요청 내용이 없는 제한된 Nginx access counter에서 rate·connection의 REJECTED도
확인한다. 전역 zone은 실제 `nginx -t`로 해석하지만, 두 컨테이너만으로 여러 peer의
**전역 임계값을 독립 포화시키지는 않는다**. 결과에도 그 한계를 기록한다.

검토 후 CI 실행:

```sh
python3 -I -B infra/public-gateway/run_once.py \
  --source-manifest-sha256 REVIEWED_MANIFEST_SHA256 \
  --ack-isolated-public-gateway
```

`ci-step-proposal.yml`은 실제 workflow 밖의 제안이다. 실제 `lab-ci.yml`에 job을
복사할 때만 hash를 주입하고 push paths에 `infra/public-gateway/**`를 추가한다.
제안 파일 자신에 manifest hash를 넣어 자기참조시키지 않는다. 소스 8개와 manifest는
모두 LF bytes로 고정한다.

준비·검증 예산은 600초, 이미지당 pull 최대180초, HTTP probe 최대180초다. 이후
별도의 제한된 정리를 수행한다. 실패한 컨테이너·HTTP suite를 재시작하지 않고
readiness GET도 자신의 합성 fixture만 조회한다. 기존 `.local/public-gateway-public`이
있으면 거부하여 이전 결과를 덮어쓰지 않는다. 정리는 정확한 nonce 라벨·ID가 일치하는
컨테이너와 비어 있는 소유 네트워크에만 허용한다. prune·compose down·전역 삭제·
로컬 재귀 삭제는 없다. 결과는 유한한 phase·count만 게시하며 예외·원문 로그·호스트
경로·mock 요청 내용을 내보내지 않는다. runner/process 강제 종료로 finally가 실행되지
않으면 정리가 중단될 수 있다. 정확한 소유 라벨을 확인하고 전역 정리하지 않는다.

## 아직 선택·배포하지 않은 부분

Cloudflare Tunnel의 계정·domain과 Tailscale Funnel의 tailnet·HTTPS·policy는 확인된
의존성이 아니다. DDNS·공유기 포트 사용 가능 여부도 미확인이다. HTTPS와 외부 노출
방식은 **미선정** 상태다. 격리 CI가 통과해도 실제 API·TLS·터널·미니 PC 검증으로
합치지 않는다. X-Forwarded-For·CF client-IP 헤더를 신뢰하지 않고 실제 edge가
정해질 때까지 immediate peer와 전역 카운터를 사용한다.

공식 근거: [Nginx core](https://nginx.org/en/docs/http/ngx_http_core_module.html),
[proxy](https://nginx.org/en/docs/http/ngx_http_proxy_module.html),
[map](https://nginx.org/en/docs/http/ngx_http_map_module.html),
[request rate](https://nginx.org/en/docs/http/ngx_http_limit_req_module.html),
[connection limits](https://nginx.org/en/docs/http/ngx_http_limit_conn_module.html).
