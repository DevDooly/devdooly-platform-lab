# 공개 조회 gateway 세 번째 격리 CI 통과

2026-10-18 UTC의 [실행39109326243](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39109326243)은 소스 `3f7d0cc5e0eb5da4d86b7f8d6f7da33e3121c9b2`를 사용했다. `public-read-gateway`와 기존 `verify` job 모두 성공했다. [원본 공개 요약](attempt-3-summary.json)1332 bytes를 그대로 보존한다.

당시 source manifest는 `2eb8a146c1e0babc925f0ab6468b404d29e84b077465829d4b491ef13063cf94`다. 결과는 `passed=true`, `phase=COMPLETE`, HTTP620 checks·반환0이며 실제 고정 이미지에서 읽은 Nginx 버전은 `1.30.5`다. 공식1.28 소스의 정적 검토와 이 실행의 실제 바이너리 관측을 구분한다.

조회 경로6개 패턴·차단 URI25개·메서드10개 case를 검사했다. 정책 메서드6개는405·Allow·고정 JSON을 검사했고 HEAD의 body는 제외했다. parser TRACE·고정 CONNECT2form·소문자get을 별도로 검사하며 parser 본문을 고정 JSON으로 단정하지 않았다. 성공 요약의 case/status/delta는 null이므로 CONNECT 각 form의 구체적인 응답 코드까지 이 요약에서 복원하지 않는다.

실제 제한 신호는 rate REJECTED33회·connection REJECTED1회였다. `globalMultiPeerLimitIndependentlyExercised=false`를 유지하며 전역 임계값을 여러 peer로 독립 포화시켰다고 주장하지 않는다.

gateway·fake·network 모두 `REMOVED_VERIFIED`, `ownedResourcesRemoved=true`였다. nonce 라벨·소유 ID·빈 네트워크 확인으로 제한한 제거와 부재 확인을 통과했다. 미니 PC 접촉·공개 endpoint·host port·DB/Kafka·Spark/JVM 시작은 이 gateway 실행기 범위에서 모두 false다.

이는 합성 upstream에 대한 Linux Docker 검증이다. 실제 API·클러스터 NetworkPolicy·외부 TLS·공개망·브라우저 cookie/CORS·운영 용량·SLA 검증은 포함하지 않는다. [첫 실패](ATTEMPT_1.md)와 [두 번째 실패](ATTEMPT_2.md)의 원문·미확인 상태는 변경하지 않는다.
