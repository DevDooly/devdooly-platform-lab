const repository = 'https://github.com/DevDooly/devdooly-platform-lab';

/** Static reading route only. No runtime observation or execution is attached to these steps. */
export const firstVisitTourSteps = [
  {
    number: 1,
    title: 'Java 처리 결과',
    target: '#lab',
    action: '입력 건수의 합을 확인하고, 실패 건수를 눌러 이벤트별 사유를 봅니다.',
    evidence: [{ label: 'worker 고정 입력 검증', href: `${repository}/blob/main/docs/evidence/current-worker-fixture/README.md` }],
  },
  {
    number: 2,
    title: 'Kafka 재개',
    target: '#kafka-lag-recovery',
    action: '저장된 3·4단계를 선택해 lag 14 → 0과 committed offset을 비교합니다.',
    evidence: [{ label: '격리 소비자 복구 검증', href: `${repository}/blob/main/docs/evidence/kafka-lag-recovery/README.md` }],
  },
  {
    number: 3,
    title: 'CI/CD',
    target: '#platform',
    action: '배포 흐름을 보고, 게시된 배포·Pod 기록의 출처와 시각을 확인합니다.',
    evidence: [{ label: '정상 배포와 실패 차단 근거', href: `${repository}/blob/main/docs/evidence/cicd-gate/README.md` }],
  },
  {
    number: 4,
    title: 'AI와 Java 개선',
    target: '#ai-window',
    action: '수정 전후 코드를 펼치고, 분포·세션 수에 따른 기대값과 측정 표를 비교합니다.',
    evidence: [
      { label: 'AI 활용 범위', href: `${repository}/blob/main/examples/java-window-analysis/PROVENANCE.md` },
      { label: 'Java·JMH 측정 근거', href: `${repository}/blob/main/docs/evidence/ai-window-analysis/README.md` },
    ],
  },
  {
    number: 5,
    title: '데이터 보존',
    target: '#iceberg-capture',
    action: '캡처한 snapshot·참조·객체 수와 KEEP 판정의 근거를 봅니다.',
    evidence: [{ label: '9차 metadata capture 근거', href: `${repository}/blob/main/docs/evidence/iceberg-capture/ATTEMPT_9.md` }],
  },
] as const;

export type FirstVisitTourStepNumber = typeof firstVisitTourSteps[number]['number'];
