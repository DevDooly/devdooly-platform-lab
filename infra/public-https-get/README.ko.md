# 공개 GET 응답 계약의 수동 관측

실제 외부 실행은 아직 하지 않았다. 이 실행기는 기존 공개 API의 지정 GET6개만 확인한다. SSH나 공유 라우트의 POST 차단 확인 없이 읽기 응답을 점검하기 위한 별도 목적이다. [기존 GET6·거부3 검사](../public-https-smoke/README.ko.md)는 그대로 유지하며, 그 검사의 route 소유·POST 격리 확인을 대신하거나 실패한 검사를 우회하지 않는다.

## 고정한 범위

순서는 summary → releases → run list → `synthetic-v1-seed-42` detail → jobs → Kafka다. 모든 요청은 고정 Origin의 **GET**이며 본문·인증·쿠키가 없다. 잘못된 경로·거부 Origin·POST·HEAD·OPTIONS 요청은 보내지 않는다. URL이나 method를 workflow 입력으로 받지 않는다.

기존 `smoke.ts`의 공개 IPv4 선택·단일 HTTPS 요청·Lab DTO 검증을 import한다. 기존 파일에는 helper export 선언만 추가하고 full9 본문·guard·CLI·workflow를 변경하지 않는다. 기존 CLI의 import guard는 새 실행기에서 full9가 실행되는 것을 막는다. DTO·HTTP transport를 별도 복제하지 않는다.

허용된 저장소의 main·수동 실행·첫 attempt·40자리 검사기 SHA와 두 확인 입력이 필요하다. 기존 `LAB_PUBLIC_API_URL` variable이 비어 있지 않고 동명 secret과 같아야 한다. 이는 기존 설정을 쓰는 확인이며 새 PAT·secret·환경이나 후보 URL을 등록하지 않는다. `PUBLIC_GET_CONFIRM`, `PUBLIC_GET_TARGET_OWNERSHIP`, `PUBLIC_GET_VARIABLE_MATCH`가 모두 true가 아니면 DNS 전에 실패한다. 대상 소유 확인은 POST 차단을 확인했다는 뜻이 아니다.

CA·TLS 우회·proxy·debug·keylog 환경은 빈 값도 DNS 전에 거부한다. DNS1회에서 IPv4 1~16개를 모두 검사하고 private·예약 대역이 섞여도 거부한 뒤 첫 공개 IP에 고정한다. 원 hostname·SNI·443·기본 CA 검증을 유지한다. redirect·추가 주소·요청 재시도는 없다. DNS5초·요청15초·전체150초를 적용하고 실제 await 반환·DTO 검사·최종 판정에서도 monotonic 기한 미만인지 확인한다. 요청은1.1초 간격이며 헤더16KiB·본문 합계1MiB를 넘지 않는다. CLI는160초·job은5분으로 제한된다.

## 무엇을 확인하는가

Lab4개는 기존 golden12건(성공7·실패3·중복2·pending0)과 summary/release의 API source 일관성을 함께 대조한다. jobs는 `MINI_PC/DEPLOYED_RUNTIME`, Kafka는 엄격한 공개 관측 계약과 `MINI_PC/DEPLOYED_KAFKA`를 확인한다. 각 출처는40자리 SHA여야 하지만 운영 API·observer의 source가 검사기 checkout SHA와 같다고 가정하지 않는다.

기존 최대5초 미래 시각 허용과 원시각 보존 정책을 유지한다. 오래된 정상 DTO나 저장된 runtime 상태도 계약에 맞으면 응답 검사에 통과할 수 있다. 따라서 PASS는 해당 시점의 지정6개 HTTPS 응답·공개 DTO 범위다. 현재 worker 프로세스 생존·장기간 가용성·SLA·쓰기 차단·POST 거부·전체 서비스 무변경·인증서 자연 갱신을 증명하지 않는다. 표준 TLS 속성은 응답을 받은 연결에 대해 확인하며 실패 결과의 일부 이전 검사 성공을 전체 성공으로 바꾸지 않는다.

## 결과와 검증

새 결과의 kind는 `public-https-get-snapshot`, scope는 `PUBLIC_HTTPS_GET_CONTRACTS_ONLY`다. 실제 검사기 source·시작/완료 시각·대상 ACK·공개 IPv4/TLS boolean·지정6개 검사의 passed/HTTP status/DTO source/관측시각과 고정 오류만 담는다. `deniedRequestsTested=false`, `operatingConfigurationChanged=false`를 유지한다. 주소·IP·응답 본문·예외 원문·인증서·자격증명은 기록하지 않는다.

CLI는 새 파일을 `wx/0600`으로 먼저 열고4KiB 이하 JSON만 저장한다. console은 고정 status/errorCode만 출력한다. workflow artifact는 `public-https-get-<run>-1` 한 파일이며7일 보존한다. 실패 결과도 이전 관측을 덮어쓰지 않는다. 공개 문서나 화면을 자동 갱신하지 않는다.

오프라인 검사는 native DNS·HTTPS·대기를 import 전에 mock으로 대체한다. 정확 GET6·POST0, 사전 guard의 IO0, 오류 후 후속 요청 중단, DNS/HTTP 기한과 timer보다 늦게 관측한 반환, DTO 출처·시각·offset 계약, 비공개 canary 배제를 확인한다. 기존 full9 원문은 고정한 SHA와 export-only 차이로 대조하고 기존 route ACK 거부·성공9회 동작도 mock으로 확인한다. 실제 CA나 외부 연결 성공을 합성 검사 결과로 주장하지 않는다.

로컬 Node24.19.0에서 새 검사16개·기존 full9 검사15개·TLS 검사20개를 함께 실행해51개 통과·실패0·생략0을 확인했다. 네트워크를 mock으로 대체한 검사이며 실제 외부 응답이나 CA 성공 기록이 아니다. Linux 실행과 실제 GET 관측은 아직 예정이다.

수동 실행 입력은 `confirm_public_gets=true`, `confirm_target_ownership=true`다. 실행 응답이 불명확하면 기존 run부터 확인하고 반복 dispatch하지 않는다. attempt2·자동 주기·자동 재시도는 허용하지 않는다. 실제 결과는 source/run·artifact 원 bytes와 결합해 별도로 검토해야 한다.
