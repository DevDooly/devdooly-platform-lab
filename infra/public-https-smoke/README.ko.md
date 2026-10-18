# 외부 HTTPS 조회 검증 실행기

GitHub hosted Linux에서 Lab 공개 API의 표준 HTTPS와 고정 6 GET, 거부 3개를 한 번 확인하기 위한 수동 실행기다. Windows Node 24.19.0에서 합성 offline 테스트 10개가 통과했으며 실제 외부 접속·TLS·라우트 완성은 아직 검증하지 않았다. 기존 웹 DTO 검증 소스를 직접 사용하며 npm 설치·API 작업 생성·배포는 하지 않는다.

실행 전 기존 Traefik을 유지하는 Lab 전용 라우트의 소유와 거부 경로를 확인해야 한다. 특히 POST가 기존 catchall로 전달되지 않는다는 metadata를 먼저 검토한다. 표준 CA 인증서·SNI와 외부 접속 준비가 끝나기 전에는 실행하지 않는다.

기본 설정은 저장소 변수 `LAB_PUBLIC_API_URL`의 명시적 HTTPS `/platform-lab/api` 또는 `/api` base다. Actions는 vars 값을 env에 표시할 수 있으므로, 이 실행기에만 동명 저장소 secret을 같은 값으로 등록해 자동 마스킹을 적용한다. workflow에는 secret 값과 vars·secret 일치 boolean만 전달된다. 미설정·불일치·확인 입력 누락이면 DNS·HTTP 0회로 실패한다. secret·variable 등록은 이 소스 준비에 포함하지 않았다.

수동 외부 검증은 offline job 성공 뒤, 이 저장소의 main과 확인 입력 2개가 모두 참일 때만 실행된다. Source commit은 정확한 checkout SHA에 바인딩된다. 출력은 검사별 boolean·HTTP status·검증된 공개 sourceCommit·UTC 시각과 고정 실패 enum뿐이다. 주소·응답 본문·예외문·인증서 상세·토큰·header 원문은 로그나 artifact에 남기지 않는다.

PR·main push는 실행기·workflow·재사용 검증기 5개·합성 fixture 경로가 바뀔 때 offline 테스트만 자동 실행한다. `smoke.test.mjs`는 기존 `apps/lab-web/src/data/snapshot.json`을 직접 읽고, 실행기를 import하기 전에 Node 기본 DNS·HTTPS·대기 함수를 mock으로 바꾼다. 공개 IPv4 바인딩·SNI, 불완전 설정의 IO 0, redirect·크기·시간 제한·관측 시각과 오류 비공개를 확인한다. fixture를 새로 복제하지 않으며 테스트가 실제 외부 API를 호출하지 않는다. Git checkout·Node 도구 준비 단계와 테스트 자체를 구분한다. 기존 웹 120개와 JMH는 이 workflow에서 반복하지 않는다.

표준 DNS lookup에서 보수적인 공개 IPv4 subset에 속한 주소 하나를 골라 9개 이하의 연결에 고정한다. private·loopback·link-local·예약 대역은 거부하며, IPv6 도달성을 검증했다고 주장하지 않는다. HTTPS hostname·SNI·Host와 표준 CA 검증을 유지하고 TLS 우회·프록시·인증·쿠키·redirect·주소 재시도는 사용하지 않는다. 요청별 15초, DNS 5초, 전체 150초, 응답 헤더 16KiB, 본문 총 1MiB로 제한하며 1.1초 간격으로 순차 실행한다.

GET은 summary → releases → run list → 고정 합성 run detail → jobs → Kafka 순서다. 기존 `isObservationRecord`·job validator·엄격 Kafka parser를 재사용한다. 모든 GET이 통과한 뒤 같은 base 내부의 잘못된 경로·거부 Origin·본문 없는 POST를 각 한 번 확인한다. 이 응답만으로 upstream 미도달이나 기존 서비스 전체 무변경을 독립 증명하지 않는다. 요청·헤더·본문 상한 또는 계약이 하나라도 실패하면 재시도와 후속 요청을 중단한다.

실제 실행은 루트의 [프로젝트 실행 목록](../../docs/NEXT_STEPS.md)과 라우트 소유 확인 뒤 수동 workflow로 진행한다. 기본 Pages 화면·`LAB_PUBLIC_API_URL` 변수·서버·인증서는 이 후보에서 변경하지 않는다.
