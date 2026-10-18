# 공개 조회 gateway 두 번째 격리 CI 실패

2026-10-18 UTC의 [실행 39108684105](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39108684105)은 소스 `6c99a07fe3360690ed8eb14918705abd8656cd04`를 사용했다. [원본 공개 요약](attempt-2-summary.json) 932 bytes를 그대로 보존한다. [첫 실패](ATTEMPT_1.md)도 유지한다.

전체 결과는 `passed=false`, `workloadPhase=ACTUAL_HTTP_PROBES`, `validationCheckpoint=HTTP_PROBE_RESULT`다. 검증한 HTTP probe 결과는 `passed=false`, `phase=DENIED_METHOD`, `checks=376`, `returnCode=1`이었다.

해당 소스의 고정 검사 수를 대조하면 376은 CONNECT 응답 코드 assertion 위치와 일치한다. 그러나 원 요약에는 실제 case·응답 코드·본문·upstream count 차이가 없다. 실제 응답이 400·500 등이었다거나 이것이 구체적인 실패 원인이었다고 단정하지 않는다. 고정 Nginx 바이너리의 실제 버전도 이 실행에서는 관측하지 않았다.

gateway·fake·network의 `cleanupStatuses`는 모두 `REMOVED_VERIFIED`, `ownedResourcesRemoved=true`였다. 마지막 cleanup 명령은 NETWORK_LIST·반환0이다. 이 실행의 소유 자원 제거와 부재 확인은 통과했으며, 첫 실행의 정리 미확인 상태를 소급 변경하지 않는다. 미니 PC 접촉·외부 공개·host port 게시·DB/Kafka·Spark/JVM 시작은 모두 false다.

후속 후보는 정책이 반환하는 405 JSON과 Nginx가 먼저 거부하는 TRACE·CONNECT의 본문 계약을 구분한다. 정책 메서드6개, parser TRACE1개, 고정 CONNECT2form과 소문자get1개를 합쳐10개 case를 검사한다. parser 거부에서는 본문을 단정하지 않고 upstream 호출0과 해당 응답 조건을 확인한다.

새 결과에는 유한한 실패 case·실제 관측 status·합성 upstream count 차이와 검증한 Nginx 숫자 버전만 추가한다. 같은 소스를 재실행하지 않고 수정된 새 소스의 별도 CI로 확인한다. 실제 API·미니 PC·외부 TLS 검증과는 구분한다.
