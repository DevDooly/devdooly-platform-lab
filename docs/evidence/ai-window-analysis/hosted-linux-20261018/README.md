# 별도 GitHub-hosted Linux JMH 재현

2026-10-18에 공개 합성 시간창 계산 예제를 GitHub-hosted Linux에서 한 번 측정했습니다. [수동 실행 39117473459](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39117473459)는 **10:03:33 UTC에 성공**했으며, source commit은 [`e2961aacb220c0f3c2ad7263319ff72b46ead6f9`](https://github.com/DevDooly/devdooly-platform-lab/tree/e2961aacb220c0f3c2ad7263319ff72b46ead6f9/examples/java-window-analysis)입니다. Maven 검증의 Java 테스트 20개는 PASS·skip 0이었습니다.

이 결과는 [기존 Windows 측정](../README.md)과 별도의 기록입니다. 원래 Windows 수치와 측정 당시 `sourceCommit:null`, 후속 게시 소스 일치 기록은 그대로 유지합니다. 회사 코드·데이터나 미니 PC·운영 서비스는 사용하거나 변경하지 않았습니다. 저장소 소유자의 사람 검토는 아직 `PENDING`입니다.

## 조건과 확인 범위

- runner label `ubuntu-24.04`, Temurin Java **21.0.12.1**, VM **21.0.12.1+1-LTS**, JMH **1.37**입니다.
- sparse/nested × 128·512·2,048·4,096개 × quadratic/sweep의 **16조합**, 조합별 새 JVM **3개**, fork마다 측정 interval **5개**로 총 **48 forks·240 intervals**입니다. 각 fork의 warmup은 2×500ms, 측정은 5×500ms입니다.
- thread 1개, G1 GC, 고정 heap 256MiB, Asia/Seoul timezone입니다. endpoint 자료구조 생성·정렬을 측정하며 UTC 파싱·fixture 생성·기대값 검증은 trial setup에서 수행합니다.
- 공개 summary의 source 16파일·고정 pins·JAR·fixture 연결과 전후 소스/JAR 불변을 확인했습니다. 독립 검증에서 각 조합의 15개 시간 표본 평균이 보고된 평균과 일치했습니다. 이는 실제 hosted 실행의 기록이며 원 Windows 측정을 다시 설명하는 값이 아닙니다.

공유 runner에서 부모 프로세스에 사용 가능한 CPU 하나로 affinity를 요청했습니다. fork 내부 affinity를 별도로 측정하지 않았고 전용 물리 코어·CPU quota·RSS 메모리 한도를 보장하지 않습니다. 256MiB는 fork의 Java heap 설정입니다.

## 실제 관측값과 오차

단위는 **평균 ± JMH scoreError, us/op**입니다. scoreError는 평균의 99.9% 신뢰구간 반폭이며 median·tail latency가 아닙니다. fork별 5개 시간 표본과 연산당 평균 할당량은 [public-summary.json](public-summary.json)에 보존했습니다.

| 합성 분포 | 세션 수 | quadratic O(n²), us/op | sweep O(n log n), us/op |
|---|---:|---:|---:|
| sparse | 128 | 86.091 ± 74.250 | 8.477 ± 0.434 |
| sparse | 512 | 1,368.646 ± 1,243.373 | 48.752 ± 1.431 |
| sparse | 2,048 | 8,159.432 ± 45.087 | 428.817 ± 9.625 |
| sparse | 4,096 | 33,327.424 ± 1,421.293 | 949.000 ± 21.729 |
| nested | 128 | 21.143 ± 0.494 | 4.586 ± 0.080 |
| nested | 512 | 248.058 ± 6.195 | 24.241 ± 0.621 |
| nested | 2,048 | 4,811.030 ± 810.974 | 228.926 ± 24.735 |
| nested | 4,096 | 18,550.497 ± 3,184.997 | 536.286 ± 36.443 |

**16조합 중 2개는 scoreError가 평균의 25% 이상입니다.** sparse quadratic의 128·512개 측정에서 fork 간 차이가 크므로 평균만으로 개선 배수를 보장하지 않습니다. 짧은 warmup이 JIT 안정성을 보장하지 않으며 공유 호스트의 영향을 분리 측정하지 않았습니다. Windows와 Linux의 절대값 차이를 OS의 효과로 해석하거나, 이 합성 결과를 회사 성과·AI의 인과적 효과·운영 처리량·SLA로 옮겨 적지 않습니다.

## 공개 파일과 재현

| 공개 파일 | bytes | SHA-256 |
|---|---:|---|
| [public-summary.json](public-summary.json) | 15,994 | `1c22416a201891d18ac0bfc48f0350f86ca8b54d7cad380d9e4e60b71bff291d` |
| [fixtures.tsv](fixtures.tsv) | 1,932 | `71181a19729919c94a3f91b5e2b8036fe520384a37da283ce1a9c5ed95631635` |

두 파일은 해당 실행 artifact의 원문 bytes를 그대로 복사했습니다. raw metadata·실행 로그·JAR는 이 문서나 artifact에 게시하지 않습니다. [수동 재현 안내](../../../../infra/benchmarks/java-window-jmh/HOSTED_REPRODUCTION.md)와 [실행 당시 workflow](https://github.com/DevDooly/devdooly-platform-lab/blob/e2961aacb220c0f3c2ad7263319ff72b46ead6f9/.github/workflows/window-jmh-manual.yml)를 함께 확인할 수 있습니다.

앞선 [workflow 등록 검사 실패](https://github.com/DevDooly/devdooly-platform-lab/actions/runs/39117223880)는 job 환경 설정의 context 위치 오류였으며 job이 생성되지 않았습니다. 이를 수정한 위 커밋에서 이번 수동 측정을 수행했습니다. 실패 기록을 없애거나 결과가 유리한 실행을 고르기 위해 벤치를 반복하지 않았습니다.
