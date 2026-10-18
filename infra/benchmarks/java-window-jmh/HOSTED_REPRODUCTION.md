# GitHub-hosted Linux에서 별도로 재현하기

기존 Windows 측정 기록은 [검증 근거](../../../docs/evidence/ai-window-analysis/README.md)에 보존합니다. 이 실행은 같은 공개 합성 예제를 Java 21과 GitHub-hosted Linux에서 다시 측정하는 별도 기록입니다. **2026-10-18의 실제 Linux 측정은 [별도 검증 근거](../../../docs/evidence/ai-window-analysis/hosted-linux-20261018/README.md)에 기록했습니다.** 회사 데이터나 운영 서비스는 사용하지 않습니다.

`.github/workflows/window-jmh-manual.yml`은 확인 입력을 켠 수동 실행만 지원합니다. PR·push·일정에 따라 벤치를 자동 실행하지 않습니다. 실행 commit과 고정 소스 16개를 확인한 뒤 독립 모듈을 Maven verify하고 기존 JMH runner를 한 번 사용합니다. 16조합 × 새 JVM 3개 × 측정 5개, heap 256MiB와 같은 옵션을 유지합니다. 추가 소스나 symlink는 거부하며 모듈 루트의 `target`·`results`·`.git`, 모든 깊이의 `__pycache__`만 소스 목록에서 제외합니다.

공유 runner에서 사용 가능한 CPU 하나로 affinity를 요청하지만 전용 물리 코어·CPU quota·RSS 한도를 제공하지는 않습니다. fork 안의 affinity를 별도로 측정한 결과도 아닙니다. 기존 JMH 자식 실행의 420초 제한과 빌드·fixture·정리 시간은 구분합니다.

공개 artifact는 검증한 수치의 `public-summary.json`과 합성 입력 지문의 `fixtures.tsv`뿐입니다. 소스·JAR·fixture의 연결, JVM 버전과 환경 한계를 함께 남기며 raw metadata·실행 로그·JAR는 artifact로 올리지 않습니다. 실패하거나 일부 결과가 빠지면 `FAILED_OR_PARTIAL`로 남기고 자동 재시도하지 않습니다. 이 재현만으로 회사 성과, AI의 개선 효과, 운영 SLA나 사람 검토 완료를 주장하지 않습니다.
