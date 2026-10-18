# Iceberg decoder stdout의 합성 검증

2026-10-18 · Windows의 Java 21.0.9에서 공개 합성 fixture로 확인한 결과입니다. 실제 Cloud metadata capture와 별도이며, [8차 실행](ATTEMPT_8.md)의 strict JSON 검증 실패 원인을 입증하지 않습니다.

생산 Java 변경은 JSON mapper를 필요할 때 초기화하고, CLI 진입 시 원래 stdout을 응답 전용으로 보관한 뒤 일반 stdout 출력을 stderr로 보내는 것입니다. 원래 JSON 검증과 그래프 계산·종료 코드·크기 및 시간 제한을 유지합니다. 이 변환을 역변환하면 이전 Java 전체 SHA-256과 같습니다.

공개 fixture로 만든 같은 입력을 원본·개선본·출력 canary 두 개를 넣은 개선본에 각각 전달했습니다. 별도 자식 프로세스 13개에서 다음을 확인했습니다.

- 세 소스 모두 컴파일 성공. class 수는 원본 13개, 두 개선본 각 14개이며 허용한 class 이름과 상한 64개를 확인했습니다.
- 정상 입력: 세 응답 모두 exit 0, `DECODED`, 7,447 bytes 및 SHA-256 `7a1750956783a54fc21dad618ac8347522b17a55468b0fa017ef853775974925`로 같습니다.
- 잘못된 magic 입력: 세 응답 모두 exit 3, `REJECTED`/`FRAME_MAGIC`, 151 bytes 및 SHA-256 `7fc39db5122fb0931a6fae39e89f291b1d1f1369c2fb8f84a108376cb98ae6d2`로 같습니다.
- 두 출력 canary는 stderr에 각각 한 번만 나오며 JSON stdout에는 없습니다. 라이브러리의 class load와 직접 decode 호출은 전역 stdout 객체를 바꾸지 않았습니다.
- 입력 source·JAR·Java/Javac 실행 파일과 staging source의 전체 hash가 전후 같습니다. Java heap 상한 256MiB, 자식별 timeout 최대 30초, stdout 4MiB·stderr 64KiB 제한을 적용했습니다. OS CPU·메모리 한도를 측정한 결과는 아닙니다.

별도 source 정적 검사 1개도 통과했습니다. 이 검사는 위 Java 자식 실행과 별도의 실행이며, 아직 Linux 87개나 실제 capture 성공 결과로 표시하지 않습니다.

검증기 준비 중 발생한 실패도 보존합니다. 최초 두 호출은 Windows의 `lstat`/`fstat` 교차 시각·실행권한 표현 차이로 Java 실행 전에 중단됐습니다. 세 번째 호출은 원본 컴파일 exit 0 뒤 1,803 bytes의 stderr가 있다는 이유로 중단됐습니다. stderr의 내용과 종류는 수집하지 않았습니다. Windows에서는 각 조회 방식의 전후 메타데이터를 유지하고 실제 관측된 교차 차이만 제한적으로 처리했으며, 컴파일러의 bounded 진단 출력과 프로토콜 stdout 검사를 구분한 새 검증기로 위 결과를 확인했습니다. 이전 실패를 성공으로 바꾸지 않았습니다.

선택한 Java source는 `21556d45310fcdacf63707eccfff51600a98c61f0f03bf4df911242c9f9f107a`, 검증 runner는 `37f1a8f20440d3b596adba4f6f7a46e27ef3b3ed3af90b3637d536593cc1222b`입니다. 합성 실행 결과 JSON의 SHA-256은 `ab09b9b158ed09c727716b42e1e235de43e79b738429a088b4a03c66f340ea4c`입니다. 원문 child stdout/stderr는 게시하지 않습니다.

다음은 새 source의 Linux 계약 검증과 별도 fresh Cloud capture입니다. 실제8의 원인, Cloud classpath 동등성, 실제 graph·inventory·전체 KEEP, snapshot 만료·객체 삭제를 이 합성 검증으로 주장하지 않습니다.
