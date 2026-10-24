import { publicReadUrl } from '../lib/public-api-base.ts';
import { boundedObservationText, discardObservationBody } from '../lib/observation-response-body.ts';

export const API_ENDPOINTS = [
  { id: 'runs', title: '합성 실행 목록', path: '/demo/runs',
    description: '최근 저장된 합성 실행 최대 20개를 읽습니다. 상세 조회에 사용할 실행 ID를 찾을 수 있습니다.',
    boundary: '새 작업을 실행하지 않습니다. 저장된 결과와 현재 처리 중인 작업은 서로 다른 기록입니다.',
    fields: [['items[]', '실행 ID·이름·상태·합성 데이터 여부와 seed'], ['items[].*Count', '입력·성공·실패·중복·대기 건수'], ['observedAt', 'API가 목록을 조회한 시각']] },
  { id: 'detail', title: '실행 한 건 자세히', path: '/demo/runs/{id}',
    description: '실행 ID에 해당하는 처리 결과, 이벤트별 판정과 성공 시계열을 읽습니다.',
    boundary: '존재하지 않는 ID는 404입니다. 데이터 생성이나 Java 처리 로직의 새 실행이 아닙니다.',
    fields: [['id · scenario', '선택한 실행과 합성 시나리오'], ['outcomes[]', '이벤트별 SUCCESS·FAILED·DUPLICATE·PENDING과 사유'], ['series[] · failureReasons[]', '성공 시계열과 실패 사유별 건수'], ['observedAt', 'API가 상세 결과를 조회한 시각']] },
  { id: 'summary', title: 'API와 DB 상태', path: '/platform/summary',
    description: 'API가 보고한 상태와 DB SELECT 1 확인 결과를 읽습니다.',
    boundary: 'components의 Jenkins·Argo CD·Kafka 항목은 전체 도구의 현재 상태를 검증한 값이 아닙니다. 배포·관측 화면의 출처도 함께 확인하세요.',
    fields: [['status · environment', 'API가 보고한 상태와 실행 환경'], ['components[]', '구성요소별 이름·상태·설명'], ['sourceCommit · observedAt', 'API 소스와 조회 시각'], ['publicExecutionEnabled', '공개 실행 허용 여부. 현재 공개 API는 조회 전용']] },
  { id: 'releases', title: 'API 런타임 버전', path: '/platform/releases',
    description: 'API 프로세스가 보고한 버전, 소스 커밋과 이미지 정보를 읽습니다.',
    boundary: 'deploymentStatus는 API 런타임의 표기입니다. Jenkins 빌드 성공이나 Argo CD 동기화 상태의 증명이 아닙니다.',
    fields: [['items[].version · sourceCommit', 'API 버전과 소스 커밋'], ['items[].imageDigest', '설정된 이미지 digest. 없으면 null'], ['items[].deploymentStatus · startedAt', '런타임 구분과 프로세스 시작 시각'], ['observedAt', 'API가 응답을 만든 시각']] },
  { id: 'jobs', title: '작업·export 관측', path: '/jobs/observation',
    description: 'DB에 커밋된 작업 상태, 실행 슬롯, worker 기록과 export 메타데이터를 읽습니다.',
    boundary: 'worker를 시작하거나 S3 파일을 새로 읽지 않습니다. heartbeat는 마지막 저장 시각이며 현재 프로세스 생존의 보장이 아닙니다.',
    fields: [['runtime', '저장된 상태·단계·heartbeat·실패 코드와 소스'], ['slot.occupiedRunId', 'DB에 기록된 실행 슬롯 소유자'], ['jobs[]', '최근 작업·처리 건수·export 상태·파일 크기·SHA-256'], ['capturedAt · scope', '관측 시각과 검증 범위']] },
  { id: 'kafka', title: 'Kafka offset·lag 관측', path: '/kafka/observation',
    description: '서버에 미리 설정된 한 대상의 offset과 consumer group 상태를 읽습니다.',
    boundary: 'broker·topic·group을 이 페이지에서 선택하지 않습니다. 발행·소비·offset 변경은 하지 않으며 미설정·불안정 시 오류를 반환할 수 있습니다.',
    fields: [['groupState · commitState', 'group 상태와 commit 관측 여부'], ['logStartOffset · readCommittedEndOffset', '관측한 partition의 시작·읽기 가능 끝 offset'], ['committedOffset · lag', 'commit과 lag. NO_COMMIT이면 null일 수 있음'], ['capturedAt · consistency', '관측 시각과 순차 조회의 범위']] },
] as const;

export type ApiEndpointId = typeof API_ENDPOINTS[number]['id'];
export const MAX_API_RESPONSE_BYTES = 256 * 1024;
export const API_REQUEST_TIMEOUT_MS = 8_000;
export const DEFAULT_RUN_ID = 'synthetic-v1-seed-42';
export function apiEndpointPath(id: ApiEndpointId, runId = DEFAULT_RUN_ID): string | null {
  const endpoint = API_ENDPOINTS.find(item => item.id === id);
  if (!endpoint) return null;
  if (id === 'detail') return /^[a-z0-9][a-z0-9._-]{0,79}$/.test(runId) ? `/demo/runs/${runId}` : null;
  return endpoint.path;
}

export type ApiReadFailureCode = 'INVALID_TARGET' | 'HTTP_ERROR' | 'INVALID_JSON' | 'BODY_REJECTED' | 'TIMEOUT' | 'NETWORK_ERROR';
export class ApiReadFailure extends Error {
  readonly code: ApiReadFailureCode;
  readonly status: number | null;
  constructor(code: ApiReadFailureCode, status: number | null = null) { super(code); this.code = code; this.status = status; }
}
export interface ApiReadResult {
  status: number;
  path: string;
  receivedAt: string;
  responseTime: string | null;
  json: string;
}
const responseTimestamp = (value: unknown): string | null => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const record = value as Record<string, unknown>;
  const candidate = record.observedAt ?? record.capturedAt;
  return typeof candidate === 'string' && candidate.length <= 50 && !Number.isNaN(Date.parse(candidate)) ? candidate : null;
};

/** An explicit single GET, without fallback, redirects, browser credentials or automatic retries. */
export async function readPublicApi(base: string, id: ApiEndpointId, runId?: string, fetcher: typeof fetch = fetch): Promise<ApiReadResult> {
  const path = apiEndpointPath(id, runId);
  const url = path && publicReadUrl(base, path);
  if (!path || !url) throw new ApiReadFailure('INVALID_TARGET');
  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<never>((_, reject) => {
    timer = setTimeout(() => { controller.abort(); reject(new ApiReadFailure('TIMEOUT')); }, API_REQUEST_TIMEOUT_MS);
  });
  const request = async (): Promise<ApiReadResult> => {
    const response = await fetcher(url, { method: 'GET', headers: { Accept: 'application/json' },
      cache: 'no-store', credentials: 'omit', redirect: 'error', signal: controller.signal });
    if (!response.ok) {
      discardObservationBody(response);
      throw new ApiReadFailure('HTTP_ERROR', response.status);
    }
    if (!/^application\/json(?:\s*;|$)/i.test(response.headers.get('content-type') ?? '')) {
      discardObservationBody(response);
      throw new ApiReadFailure('INVALID_JSON');
    }
    let text: string;
    try { text = await boundedObservationText(response, MAX_API_RESPONSE_BYTES); }
    catch { throw new ApiReadFailure(controller.signal.aborted ? 'TIMEOUT' : 'BODY_REJECTED'); }
    if (controller.signal.aborted) throw new ApiReadFailure('TIMEOUT');
    try {
      const value: unknown = JSON.parse(text);
      return { status: response.status, path, receivedAt: new Date().toISOString(), responseTime: responseTimestamp(value), json: JSON.stringify(value, null, 2) };
    } catch { throw new ApiReadFailure('INVALID_JSON'); }
  };
  try { return await Promise.race([request(), timeout]); }
  catch (error) { throw error instanceof ApiReadFailure ? error : new ApiReadFailure(controller.signal.aborted ? 'TIMEOUT' : 'NETWORK_ERROR'); }
  finally { clearTimeout(timer); }
}
