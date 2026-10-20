# 부분 client 구성 실패의 자원 정리

2026-10-21 KST, 기존 Mockito로 static factory를 호출 전에 대체해 검증했습니다. 실제 S3·Kafka·DB·Spring context를 시작하지 않았습니다.

## 문제와 수정

실행 시작 전에 S3 client가 반환된 뒤 producer 생성에서 Error가 발생하거나, S3·producer가 반환된 뒤 consumer 생성에서 Error가 발생하면 이미 등록한 client가 닫히지 않았습니다. `openClients`의 RuntimeException 처리만으로 Error를 잡을 수 없고, 초기화가 실패한 try-with-resources도 아직 반환되지 않은 Clients를 닫아 주지 않습니다.

부분 목록에 등록한 client를 역순으로 모두 정리한 뒤 최초 construction Error 객체를 그대로 전파합니다. 후속 종료 Error나 Exception을 원 오류의 cause·suppressed에 추가하지 않습니다. 일반 구성 실패는 고정 메시지·cause 없음으로 유지하고, 이 경우 종료에서 처음 발생한 Error가 있다면 그 Error를 전파합니다.

검사를 위한 package-private `Clients`·`openClients` 경계만 열었으며 public API·실행 인자·운영 선언을 추가하지 않았습니다. factory가 반환하기 전 내부에서 만든 자원이나 메모리 부족으로 목록 등록 자체가 실패한 경우까지 정리한다고 주장하지 않습니다. 바깥 CLI의 context 등 try-with-resources 전체에서 suppressed가 없다는 보장도 아닙니다.

## 실제 재현과 회귀 검증

기존 코드에 검사 접근을 위한 두 private 제한만 제거하고 동작은 유지한 채 다음3개를 실행했습니다. 모두 기대한 close 호출이 없다는 이유로 실패했습니다.

1. producer 생성 Error 뒤 S3 close.
2. consumer 생성 Error 뒤 producer→S3의 역순 close.
3. construction Error와 종료 실패가 겹쳐도 원 Error 보존·나머지 close.

검토한 수정 후 새 검사7개가 모두 통과·skip0입니다. 위3개에 더해 일반 구성 실패 뒤 첫 종료 Error 우선, 일반 오류의 고정 메시지·진단 원문 미첨부, 정상 consumer→producer→S3 종료와 반복 close 무동작을 확인했습니다.

Windows Java21.0.9·Maven3.10.0의 기존 로컬 캐시로 빌드 결과가 없는 새 소스 폴더에서 production45개·test48개를 실제 컴파일했습니다. offline `mvn -o -B -ntp verify` 성공: 전체240개 중229개 실행 통과·실패0·오류0·기존 Linux 전용11개 생략, jar 재패키징 성공입니다.

PR162의 main `64be1e8e50e0a84eab4510c1bcc8188f550df96f`에서 [Linux CI39469985940](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39469985940)의 API240개 모두 통과·skip0, verify·공개 조회 gateway 성공을 확인했습니다. 같은 소스에는 [실행 중 Error 처리](../runtime-error-cleanup/README.md)의26개와 이 구성 경계7개, 합계33개 회귀 검사가 포함됩니다. CI 완료와 기존 미니 PC의 실제 image/source는 구분합니다.

이 결과는 합성 AssertionError와 반환된 mock client의 구성·정리 경계입니다. 실제 OOM 복구·전체 CLI/context 종료 성공·운영 배포·archive 기동 복원은 검증하지 않았습니다.

## 근거 목록 연결

Java·GitHub Linux CI 카드에 관련33개·전체240개와 immutable source64be1e8을 연결했습니다. 로컬1280px·390px에서 Error 검색+Java+CI 필터의 결과1개와 코드·근거 링크, 본문17px·모바일 링크44px·문서 폭375px를 확인했습니다. 기존 웹207개 검사·skip0, Astro47파일 오류·경고0, 프로젝트 경로 빌드도 통과했습니다.

PR164의 main `c5203cb41429e83757ff3279fc3326a7021fd337`은 [CI39472100483](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39472100483)의 verify·gateway를 통과했습니다. 최초 [push Pages39472100508](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39472100508)은 `WORKFLOW_HISTORY_CHANGED_DURING_READ`로 실패했습니다. 기존 게시기가 시작한 별도 [workflow_dispatch39472209197](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39472209197)의 같은 main build·deploy 성공과 구분하며 최초 결과를 성공으로 고치지 않습니다. 이력 보호를 완화하거나 중복 dispatch·재시도를 추가하지 않았습니다.

성공 실행의 정확한 artifact와 공개 GET 파일3개의 전체 bytes·SHA256가 일치했습니다. 이는 해당 게시 결과의 보존 확인이며 새로운 운영 수집 성공을 뜻하지 않습니다.

| 파일 | 바이트 | SHA256 |
| --- | ---: | --- |
| platform-observation.json | 1133 | `689f30fff20dd89237554e9b8fb07d4f21546782c8a5d58dc743a347647e4fe9` |
| jobs.latest.json | 5809 | `35f2e1fae516d295d5d56028dc30003c4b9c3f97ce0301aada04d7238aad4583` |
| kafka.latest.json | 562 | `b4e867495547de0d3031245802298f9c6451fc52deb78d6481301fc75f136a84` |

공개1280px·390px에서 초기19개 중6개, 준비 후 Error+Java+CI 결과1개·source/근거 링크·본문17px·모바일 링크44px·문서 폭375px를 확인했습니다. 첫 접속의 초기 입력 불일치는 별도 [검색 준비상태 수정](../evidence-input-readiness/README.md)으로 다룹니다.
