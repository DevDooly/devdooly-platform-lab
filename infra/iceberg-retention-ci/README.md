# Iceberg closed-copy capture 후보

**SOURCE_ONLY / 새 실제 Cloud 실행 없음.** 이 디렉터리는 동결된 observer·loader·composite·Java decoder를 모은 패키지 후보입니다. 원래 Cloud producer `73e229…`, runtime manifest `c63aded…`, 기존 성공 기록 `127168…`과 retention planner `ec1ff5…`는 변경하지 않습니다. 기존 성공이 이 새 capture/decoder의 성공을 뜻하지 않습니다.

모듈 import는 workload를 실행하지 않습니다. 명시적인 `composite_entry.run(...)`은 source-pinned CLI가 원래 main을 observer 안에서 한 번 호출하고, 같은 실행의 기록과 실제 stopped actor를 검사한 뒤 승인된 whole copies만 RAM decoder에 전달하는 경계입니다. 임의 caller/module을 격리하는 sandbox가 아닙니다. 새 CLI·workflow는 검토된 source 후보이며 실제 prep/capture는 실행하지 않았습니다.

현재 **runtime 11개, 테스트 7개, WIRE 계약과 runtime manifest**를 원본 동결본에서 모았습니다. Prep 실행기·classpath archive·bounded process·명시적 CLI는 포함되지만 source 준비가 실제 Linux/Cloud 성공을 뜻하지 않습니다. 합성 Java fixture, Windows 검증 runner, private 실제 artifact 또는 자격증명은 runtime payload에 넣지 않습니다.

CLI는 첫 번째 시도인 GitHub-hosted Linux job에서 actual checkout/SOURCE_COMMIT/GITHUB_SHA와 모든 source pin을 확인한 뒤에만 동작합니다. `--ack-fresh-closed-copy-capture`가 필요하며, 과거 workflow run의 재실행을 받아들이지 않습니다. 준비는 원래 main/clock 전에 별도 최대600초로 제한하고 원래 workload600초는 유지합니다. [워크플로우 후보](../../.github/workflows/lab-ci.yml)의 `run_iceberg_capture_trial`은 기본false이며 기존 세 시험 플래그가 false인 경우 새 job만 선택합니다.

```text
python3 -I -B infra/iceberg-retention-ci/run_capture.py \
  --source-manifest-sha256 c8cecad8fc09ab20a78382c4a96daf5c9e761065cb774abd6cd9b65d0ee8be28 \
  --ack-fresh-closed-copy-capture
```

업로드 대상은 새 `.local/iceberg-closed-copy-public/summary.json` 하나입니다. Private tree·원래 producer summary·descriptor·graph·로그·Env를 업로드하지 않습니다. 관측되지 않은 count는 null이며 objectCandidate0은 KEEP-only 정책입니다. `normalizationReceiptCanonicalSha256`는 private receipt 하위 객체의 canonical SHA로서 전체 private 파일 SHA가 아닙니다.

## 보수적 범위

세 named JDBC checkpoint만으로 writer quiescence·전체 closure·pin authority를 추론하지 않습니다. source-bound 원래 summary, Spark/reader/clock, SELECT intent, stop 기록과 별도 actor 증거를 다시 묶습니다. enclosing root0700 안의 원래 proof0777/copy 소유권은 변경하지 않고 Linux held-FD/nofollow/whole SHA reader로 검사합니다.

Decoder는 format2 current metadata와 승인된 map 안의 manifest-list/manifest를 읽습니다. ADDED/EXISTING/**DELETED**, shared manifest 및 position-delete reference도 snapshot closure에 남깁니다. old metadata와 target 밖의 객체는 KEEP입니다. 미지원/누락/충돌은 UNDETERMINED이며 가짜 inventory를 만들지 않습니다. Parquet 내용·과거 metadata 복원·live table 독립검증은 하지 않습니다. Planner 후보도 **expiry/GC/apply/객체삭제를 실행하지 않고 모든 객체를 KEEP**합니다.

새 decoder의 예정 제한은 CPU1/512MiB/PID64, heap256MiB, user185, network-none/readonly-root와 readonly class/JAR mount 두 개입니다. 입력은 최대128객체·개별4MiB·합계32MiB, descriptor512KiB, reply4MiB, private stderr64KiB입니다. 기존 단일600초 안에서 `min(now+60, started+600-40)` cutoff를 사용하고 새 exact CID의 stop/wait/inspect 및 CLI reap을 별도로 확인합니다. Java relative watchdog만으로 컨테이너 종료를 주장하지 않습니다. [WIRE_CONTRACT.md](WIRE_CONTRACT.md)가 정확한 형식입니다.

## 검증 상태

원본 Windows 합성 suite는 observer6·loader8·composite10 PASS이며 Linux 전용3개는 skip입니다. Portable 복사본은 경로 식만 바꾸고 역치환 byte equality 및 나머지 AST equality를 확인했으며 숫자 재현 목적으로 재실행하지 않았습니다. Base27의 UID185 fixture에는 실제 격리 Linux 소유권 조건이 필요합니다.

Prep helper의 별도21개는 Windows에서 archive6·bounded4·prep6 PASS와 POSIX 전용5개 skip입니다. CLI의 별도8개 합성 테스트도 PASS/skip0입니다. 실제 Docker·Java·download 없이 합성 또는 mock으로 검사한 결과이며, **Linux 전체56개(base27+prep21+CLI8)는 pending**입니다. 새 CI 후보는 CLI와 runtime/원래 source 전체 및 테스트7개의 literal SHA를 import 전에 확인한 뒤 UID0·56개·skip0을 요구합니다. `sudo -n env -i` 검사는 새 temp fixture만 쓰며 저장소의 `.local`을 root 소유로 만들지 않습니다.

Java는 기존 locked Iceberg1.11 JAR와 로컬 JDK21의 실제 metadata/Avro writer 합성7그룹, clean compile(stderr0), blocked-stdin watchdog124, Python frame→Java→Python graph 및 closure 변조 거부를 통과했습니다. 실패1~5와 성공6~7은 원래 패킷에 보존됩니다. 로컬 SLF4J 지원은 Cloud payload가 아니며, 실제 Spark image/classpath prep 호환성은 아직 검증하지 않았습니다. 새 dependency 다운로드·실제 warehouse artifact 읽기·Cloud 실행은 하지 않았습니다.

## 고정 source provenance

다음 runtime bytes는 원본과 정확히 같습니다.

| 파일 | SHA-256 |
| --- | --- |
| `named_observer.py` | `39c4330db7b5b0ce78deb7bf1607aa540e3d3fa94c3a78e70bb8fcbd5bbf9840` |
| `copy_loader.py` | `7e894d29204271d75dd086d1901f9893e983a56f598599c5b37ca768b55c87c0` |
| `normalize_graph.py` | `8bea454b989148b68d107a7ce759b5fac13e2fa9d3d3b1c83236ff3a1b5af897` |
| `composite_entry.py` | `fa2aacdbe59a5755ac661a7275c6bbbd0ad13ea4ba2490b7c9eb3174bd44736f` |
| `lifecycle.py` | `0186c34faaaa516f2935ba4bf5ff578277c005950ac2e5dc7de3d6ae82836a36` |
| `decoder_lifecycle.py` | `4b6a2e061d1b92d828520d0b99fb81a63f102d68ca953ee7186f6141cb553d96` |
| `src/org/apache/iceberg/ClosedCopyDecoder.java` | `d7f9fbab4e1951e5364dcec7e78b8aa1b86531ba034a4c1748b47158a80399d9` |
| `prep_decoder.py` | `9a4edbd67abac55cff8c480a62216867fb20d424611e7ef5a6b1d3fa6cab672b` |
| `archive_classes.py` | `f7c6c37e589228afa2be7d6013fa5745f2c0bc924164ea241573f0e6b3be6be1` |
| `bounded_process.py` | `87ec98e6f4df8de69a413eeb01ccff30135e4d72b02675d9be6627564fe1ddc6` |
| `run_capture.py` | `9338364fc5563f6d7bec63f39519b0b03364e82e2f74de22f2caa83cc76ba216` |

Upstream manifest SHA는 observer `801f6aa7bbe7717ff26a9d925478d7608256741537cf6f0cf52381ccaca0c4c3`, loader `3241fc55b1d2b0c041cccba98c93456a1170152abdf774daf733a60f8bce2d5e`, composite `08a1d9d107f3c726b1c48ec429b5ba1647325c1ec9ff7b24a945087fb134709b`, Java `418ba424383bf2385929b4654f7e24b7319e757ee7b1988176e974e2844f7d8c`입니다. WIRE SHA는 `cf50399646013459b4ad71f882d387b6d9a2bcba1263c2b30ca6af3d6168dc34`입니다.

추가 prep source/test의 upstream manifest SHA는 `d8443327515812c401edcfe494be2c762afc4057c160089dc76c47774a403f50`입니다. 이 세 runtime과 세 테스트도 원본 bytes 그대로이며 실제 prep 실행 기록이 아닙니다.

CLI source/test의 upstream manifest SHA는 `d26b6ede7b8de02204cc48ff6d87f27b403e3d549b414308442e2b72a19f0fa1`이며 두 파일도 원본 bytes 그대로입니다. 통합 runtime manifest SHA는 `c8cecad8fc09ab20a78382c4a96daf5c9e761065cb774abd6cd9b65d0ee8be28`입니다. 원래 producer/runtime/planner/lock/역사적 성공 summary는 immutable input 다섯 개로 묶으며 새 결과로 덮지 않습니다.

Portable 테스트는 원본과 다른 SHA입니다. `PLATFORM_LAB_SOURCE_ROOT` 또는 최종 파일 위치의 저장소 루트에서 `infra/...` source를 찾도록 경로만 바꿨습니다.

| 테스트 | 원본 SHA-256 | Portable SHA-256 |
| --- | --- | --- |
| `test_named_observer.py` | `92b14fff5b2312cba6d325e9587603fd2f1a3cadd094a726e19b33ecd11498a1` | `85ff4307d821dcb0c4ba8a8eb9ec4e4927ac158d887f3899df62ac9cdca8a477` |
| `test_copy_loader.py` | `d796bf3cb7d1a68cd84337b6aa915cee739d4fb494e58787df025b2b4ba062e1` | `fb8ad9febef1d307244d57f4944d043985d1a756a4b5559a8e442fe752423196` |
| `test_composite.py` | `bae7acf4000a5e57cf738adece84e54dd16e56df0cf0d202d1ff48920e322f48` | `2f7080816959573c845281d023e1a7346ced6626593806c1e0a52c5be7e6173c` |
