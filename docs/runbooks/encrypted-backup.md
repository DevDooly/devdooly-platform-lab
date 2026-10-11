# 암호화 백업 검증과 복호화

`infra/scripts/encrypted-backup.py`는 서버 연결 없이 로컬의 암호화 백업을 검증하거나 복호화합니다. Python 3.10 이상과 `cryptography` 패키지가 필요합니다. 별도 가상환경에서 `python -m pip install -r infra/scripts/backup-requirements.txt`로 검증한 버전을 설치합니다. 현재 잠금 버전은 `cryptography==50.0.2`이며, Windows의 Python 3.12.14에서 확인했습니다. [패키지 지원 범위](https://pypi.org/project/cryptography/50.0.2/)

실제 백업 파일과 32바이트 키는 Git에서 제외하고 서로 다른 비공개 위치에 보관합니다.

## 파일 형식

`DDPLAB01` 8바이트, 무작위 nonce 12바이트, AES-256-GCM 암호문, 인증 tag 16바이트 순서입니다. 앞의 20바이트 전체를 AAD로 인증합니다. 키 파일은 hex 문자열이나 Base64가 아닌 원본 32바이트입니다. 이 유틸은 암호화 기능이나 키 생성 기능을 제공하지 않습니다. 평문은 tag 검증이 끝나기 전까지 신뢰할 수 없으므로 성공한 `finalize()` 이후에만 최종 결과를 게시합니다. [cryptography의 GCM 안내](https://cryptography.io/en/stable/hazmat/primitives/symmetric-encryption/#cryptography.hazmat.primitives.ciphers.modes.GCM)

## 검증만 수행

아래 경로는 예시입니다. 기존 manifest의 **평문 SHA-256**을 확인해 `EXPECTED_SHA256` 대신 넣습니다. `--expected-sha256`은 생략할 수 있지만, 복구 대상이 맞는지 비교하기 위해 사용하는 편이 좋습니다.

```sh
python infra/scripts/encrypted-backup.py \
  --input /private/backups/lab.tar.gz.aesgcm \
  --key-file /private/keys/lab.aes256.key \
  --verify-only \
  --expected-sha256 EXPECTED_SHA256
```

인증을 통과한 평문 SHA-256과 바이트 수만 JSON으로 출력합니다. 평문 파일은 생성하지 않습니다. GCM 인증 성공은 올바른 키로 파일의 무결성을 확인했다는 뜻이며, K3s·Jenkins·DB를 실제 복원했다는 뜻은 아닙니다.

## 새 파일로 복호화

```sh
python infra/scripts/encrypted-backup.py \
  --input /private/backups/lab.tar.gz.aesgcm \
  --key-file /private/keys/lab.aes256.key \
  --output /private/restore/lab.tar.gz \
  --expected-sha256 EXPECTED_SHA256
```

출력 디렉터리는 미리 만들고 본인만 접근하게 설정합니다. Linux에서는 디렉터리 0700, 키 파일 0600 또는 0400을 사용합니다. Windows에서는 본인과 SYSTEM만 허용하는 NTFS ACL을 사용하며, 동기화·공유 폴더 밖에서 작업합니다. Windows PowerShell에서는 위 명령을 한 줄로 입력하거나 해당 셸의 줄 연결 방식을 사용합니다.

결과 파일이 이미 있으면 덮어쓰지 않습니다. 동일 출력 디렉터리의 임시 파일에 먼저 쓰고 GCM tag와 선택한 SHA-256 검증을 모두 통과한 뒤 원자적으로 이름을 변경합니다. Linux는 `renameat2(RENAME_NOREPLACE)`, Windows는 기존 파일을 대체하지 않는 rename을 사용합니다. 임시·결과 파일은 Linux 0600, Windows 본인·SYSTEM 전용 ACL로 제한합니다. 파일 시스템이 해당 동작을 지원하지 않으면 실패하며 기존 파일을 대체하는 방식으로 우회하지 않습니다.

인증 실패·해시 불일치·일반 오류에서는 임시 평문을 삭제하고 새 결과 파일을 게시하지 않습니다. 강제 종료나 전원 장애 시 임시 파일이 남을 수 있으므로 복구 디렉터리 접근 권한과 저장 장치 암호화를 함께 사용합니다. 파일 삭제는 저장 매체에서의 안전한 소거를 보장하지 않습니다. 유틸은 archive를 추출하거나 운영 데이터를 덮어쓰지 않습니다.

성공은 종료 코드 0, GCM 인증 실패는 2, 다른 처리 실패는 1입니다. 사용 방법 오류는 argparse의 종료 코드 2를 사용합니다.

## 실제 검증 범위

Windows Python 3.12.14·cryptography 50.0.2에서 20개 검증을 통과했습니다. Ubuntu Python 3.10.12·cryptography 46.0.5에서는 4MiB+73바이트 합성 파일의 복호화·해시·0600 권한·변조 차단·임시 파일 정리·Linux 원자적 이름 변경과 기존 파일 보존을 확인했습니다. [검증 원본](../evidence/recovery/README.md)을 함께 읽습니다. 두 환경의 패키지 버전은 서로 다릅니다.
