# 작업 조회 응답의 완료 시한 검사

2026-10-23(KST)에 합성 HTTP 응답과 로컬 시계로 작업 수집기의 시한 처리를 재현했습니다. 공유 시한이 15초인데 응답 본문이 16초에 완료돼도 기존 CLI는 성공을 출력하고 이전 작업 관측 파일을 바꿨습니다. 요청 전 남은 시간 검사만으로는 이 늦은 완료를 거부하지 못했습니다.

[작업 수집기](../../../infra/observation/job_collector.py)는 본문 read와 응답 context의 close가 끝난 직후 공유 monotonic 시한을 다시 검사합니다. 정확한 시한과 초과 완료는 `JOB_CAPTURE_FAILED`로 처리하며 CLI는 이전 파일 바이트를 보존합니다. 명시적 시한이 없는 기존 함수 호출은 유지합니다.

## 오프라인 검증

[회귀 검사](../../../tests/observation/test_job_publication.py)의 `JobResponseDeadlineTests`는 실제 `collect_jobs`와 CLI를 합성 응답으로 호출합니다. 네트워크 요청이나 대기 없이 시계만 전진시킵니다.

| 반례·정상 경로 | 결과 |
| --- | --- |
| 본문이 시한 직전에 완료 | 정상 DTO 수락, 응답 close 확인 |
| 본문이 정확한 시한 또는 그 이후에 완료 | 실패 처리, 응답 close 확인 |
| 본문은 제때 끝났지만 close가 시한에 도달 | 실패 처리 |
| 요청 전 시한 만료 | 애플리케이션 open 0회 |
| CLI에서 15초 시한 뒤 16초에 본문 완료 | 실패 종료, 이전 파일 바이트 보존 |
| 응답 close 예외 | 실패 종료, 이전 파일 보존, 예외 세부 내용 비공개 |

수정 전 새 6개 검사에서 하위 사례를 포함한 실패 4건을 확인했고, 수정 후 6개 모두 통과했습니다. Windows 전체 관측 검사는 179개 중 171개 통과·기존 POSIX 8개 생략·실패 0입니다. 별도 독립 검토에서도 검사 줄을 제거한 대조본의 실패 4건과 `deadline=None`의 기존 성공 동작을 확인했습니다. Linux 실행 결과는 이 로컬 기록에 포함하지 않습니다.

```sh
python -B -m unittest discover -s tests/observation -p 'test_*.py' -v
```

## 범위

이 검사는 read·close가 반환한 뒤 늦은 성공을 거부합니다. 본문 수신을 시한 즉시 중단하거나 JSON 파싱·파일 저장까지 전체 시간을 보장하지 않습니다. 플랫폼 collector의 [완료 시한·OS 잠금 검증](../collector-completion-boundaries/README.md)과 구분합니다.

위 기록은 저장소 코드와 오프라인 검사의 범위입니다. 이후 **21:18:16(KST)의 [작업 수집기 한 파일 운영 교체](DEPLOYED.md)**와 별도 사후 점검에서 새 코드 pin·권한·다른 코드와 unit 보존을 확인했습니다. 이어 [21:42 자연 회차의 새 job 수집·Pages39955401692 게시](NATURAL_PUBLICATION.md)를 연결했으며, 기존 platform 수집기의 [별도 자연 회차](../collector-completion-boundaries/NATURAL_PUBLICATION.md)와 구분합니다. Pages 토큰 교체·별도 K3s/Jenkins 기동 복원·자원 예산 정책·PR #102 보류를 유지합니다.
