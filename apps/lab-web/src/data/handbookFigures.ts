export interface HandbookFigureData {
  file: string;
  alt: string;
  caption: string;
}

export const overviewFigures = {
  architecture: {
    file: '01-overview.png',
    alt: 'Java API가 접수한 작업을 Kafka로 worker에 전달하고 결과를 MariaDB에 저장하는 흐름. 결과·실패 파일은 Garage S3에서 검증하고 공개 화면에서는 API 결과와 검증 기록을 읽는다.',
    caption: '그림 1. 합성 데이터의 접수·처리·저장과 공개 조회 흐름.',
  },
  guide: {
    file: '06-handbook.png',
    alt: '기술 문서의 왼쪽 부·장·절 목차와 오른쪽 MariaDB·Garage S3 장의 코드 및 설정 변경 안내.',
    caption: '그림 6. 적용 예시를 읽고 수정할 파일을 찾는 흐름. 저장소 장의 공개 화면을 담았다.',
  },
} satisfies Record<string, HandbookFigureData>;

export const chapterFigures: Partial<Record<string, HandbookFigureData & { section: 'flow' | 'verify' | 'evidence' }>> = {
  kafka: {
    section: 'flow',
    file: '02-java-kafka.png',
    alt: 'DB 처리 완료 후 Kafka offset 확정 전에 프로세스를 중단했다. 재전달 뒤 작업 1건과 판정 결과 12건이 보존되고 최종 consumer lag가 0이었다.',
    caption: '그림 2. DB 커밋 직후 중단과 재전달을 확인한 격리 시험.',
  },
  storage: {
    section: 'verify',
    file: '03-storage-recovery.png',
    alt: 'DB 처리 완료 뒤 S3 결과·실패 파일 검증을 기다리며 슬롯을 점유한다. 슬롯 해제 SQL 실패 후 재시도에서 두 파일을 다시 확인하고 내보내기 완료와 슬롯 해제를 확정했다.',
    caption: '그림 3. DB 완료 처리 실패 후 남은 S3 파일을 재검증한 격리 시험.',
  },
  jenkins: {
    section: 'flow',
    file: '04-delivery.png',
    alt: 'Jenkins와 GitHub Actions가 같은 커밋을 검증하고 게시 조건을 통과하면 GHCR에 이미지를 게시한다. GitOps PR과 Argo CD로 배포하고 실패 차단과 이전 이미지 복귀를 관측했다.',
    caption: '그림 4. 같은 커밋의 검증에서 정상 배포, 실패 차단, 이전 이미지 복귀까지.',
  },
  lakehouse: {
    section: 'evidence',
    file: '05-experiments.png',
    alt: 'Lakehouse 실험에서 현재 Bronze 데이터 파일을 두 개에서 한 개로 병합하고 Silver 조회 결과 12행을 보존했다. 별도 AI 예제는 독립 기대값 2,000사례와 Java 테스트 20개 및 JMH로 검증했다.',
    caption: '그림 5. Lakehouse 격리 실험과 AI 제안 알고리즘 검증을 비교한 요약.',
  },
};
