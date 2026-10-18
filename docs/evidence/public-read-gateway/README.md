# 공개 조회 gateway 격리 검증 기록

별도 Linux CI에서 digest 고정 Nginx와 공개 합성 upstream으로 조회 정책을 검증했다. [세 번째 실행](ATTEMPT_3.md)의 소스 `3f7d0cc5e0eb5da4d86b7f8d6f7da33e3121c9b2`는 HTTP 검사620개와 소유 자원 정리를 통과했다. 이는 실제 미니 PC·외부 TLS·공개 API 연결 결과가 아니다.

| 시도 | 당시 소스 | 결과와 범위 | 원본 공개 요약 |
| --- | --- | --- | --- |
| [1](ATTEMPT_1.md) | `d25caa0` | 실패. 원 workload 구간·원인과 정리 완료 미확인 | [375 bytes](attempt-1-summary.json) |
| [2](ATTEMPT_2.md) | `6c99a07` | DENIED_METHOD·checks376 실패. 실제 응답 코드 미측정, 소유 자원3개 정리 검증 통과 | [932 bytes](attempt-2-summary.json) |
| [3](ATTEMPT_3.md) | `3f7d0cc` | HTTP620 통과·실제 Nginx1.30.5·소유 자원3개 정리 검증 통과 | [1332 bytes](attempt-3-summary.json) |

첫 두 실패의 원본을 보존했다. 세 번째 성공을 앞선 실행의 구체적인 실패 원인이나 응답 코드 확인으로 소급하지 않는다.

세 번째 실행은 조회 경로6개 패턴·차단 URI25개·메서드10개 case와 헤더·body·CORS·쿠키·redirect·upstream 실패를 검사했다. 실제 access counter에서 rate 거부33회·connection 거부1회를 확인했다. 여러 독립 peer로 전역 임계값을 별도 포화시킨 결과는 아니다.

gateway 실행기는 소유 internal network1개·컨테이너2개만 사용하고 host port·DB/Kafka·Spark/JVM·실제 API·미니 PC·공개 endpoint를 사용하지 않았다. 같은 workflow의 기존 `verify` job은 별도 실행 범위다. 응답 byte 상한·전체 응답 deadline·외부 TLS·신뢰할 client IP·실제 Kubernetes 정책·배포는 후속이다.

[구현과 재현 절차](../../../infra/public-gateway/README.md)를 참고한다. 이후 문서가 바뀐 커밋은 당시 소스·manifest와 구분해 기록하며, 실제 검증한 조건만 완료로 표시한다.
