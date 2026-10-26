export const technologyScreens: Record<string, { file: string; caption: string; path: string }> = {
  java: { file: 'api-guide.jpg', caption: '공개 API 안내: 여섯 GET 경로의 역할과 응답을 확인하는 화면입니다. 캡처에서는 요청을 실행하지 않았습니다.', path: 'api-guide/' },
  kafka: { file: 'kafka-recovery.jpg', caption: 'Kafka 재개 실험의 저장 기록: 소비자 종료와 재개 단계를 비교합니다. 운영 broker의 실시간 lag 화면이 아닙니다.', path: '#kafka-lag-recovery' },
  storage: { file: 'export-record.jpg', caption: '결과 파일 손상 후 수리 실험의 저장 기록: export 확인과 슬롯 해제의 경계를 설명합니다.', path: '#export-integrity-runtime' },
  jenkins: { file: 'delivery-record.jpg', caption: '공개 배포 관측: 수집 당시 Jenkins의 검증 SHA와 Argo CD 선언을 나란히 봅니다. 관리자 UI의 캡처가 아닙니다.', path: '#platform-record' },
  kubernetes: { file: 'delivery-record.jpg', caption: '공개 배포 관측: Argo CD의 Synced·Healthy와 배포 선언을 읽습니다. 2026-10-26 07:45 UTC 수집 기록이며 현재 상태를 보장하지 않습니다.', path: '#platform-record' },
  lakehouse: { file: 'lakehouse-record.jpg', caption: '격리 Cloud 검증의 저장 기록: 현재 snapshot의 파일 2→1과 행 보존을 보여줍니다. 상시 운영 데이터 플랫폼은 아닙니다.', path: '#cloud-lakehouse' },
  web: { file: 'java-result.jpg', caption: '공개 GET으로 읽은 합성 실행 결과: 입력 12건을 성공 7·실패 3·중복 2건으로 구분합니다. 화면의 관측 시각과 실행 시각은 별개입니다.', path: '#lab' },
  ai: { file: 'java-case.jpg', caption: '개인 Java 시간창 예제: UTC 오류 수정과 알고리즘 비교를 설명합니다. 사람 검토 대기 상태를 함께 표시합니다.', path: '#ai-window' },
};
