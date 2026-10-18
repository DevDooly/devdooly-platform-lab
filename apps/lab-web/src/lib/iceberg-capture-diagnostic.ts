/** Exact public diagnostic allowlist from reviewed CLI schema 2; no raw provider values. */
export const captureFailureCodes = [
  "ACTUAL_DECODER_COMPILE_STDERR_ZERO_REQUIRED",
  "ACTUAL_HOST_COMPILER_JAVA21_REQUIRED",
  "ACTUAL_LOCKED_ICEBERG_SHA256_SHA512_REQUIRED",
  "ALL_COMPILER_SOURCE_CLASSPATH_INPUTS_UNCHANGED",
  "ARCHIVE_CHANGED_DURING_UNPACK",
  "ARCHIVE_OPEN_IDENTITY_CHANGED",
  "BOUNDED_CALL_NAME_AND_ARGV_REQUIRED",
  "BOUNDED_OWN_REGULAR_ARCHIVE_REQUIRED",
  "CANONICAL_EXISTING_PRIVATE_FOLDER_REQUIRED",
  "CANONICAL_EXPORTED_CLASSPATH_ORDER",
  "CANONICAL_PRIVATE_DIRECTORY_REQUIRED",
  "CLASSES_ROOT_CHANGED",
  "CLASS_DIRECTORY_CHANGED_DURING_TREE_READ",
  "CLASS_DIRECTORY_OPEN_CHANGED",
  "CLASS_FILE_OPEN_CHANGED",
  "CLASS_IDENTITY_CHANGED_AFTER_TREE_READ",
  "COLD_PREP_CONFIGURATION_CHANGED",
  "COMPILED_CLASS_CHANGED_DURING_READ",
  "COMPILED_CLASS_COUNT_BOUND",
  "COMPILED_CLASS_IO_FAILED",
  "COMPLETE_COMPILED_CLASS_BYTES_REQUIRED",
  "DECODER_CLASS_SHADOW_IN_SPARK_JAR",
  "DIRECT_FRESH_ARCHIVE_FILENAME_REQUIRED",
  "DUPLICATE_TAR_MEMBER_REJECTED",
  "EXACT_BOUND_NEVER_STARTED_PREP_CONTAINER",
  "EXACT_DECODER_MAIN_CLASS_REQUIRED",
  "EXACT_EXISTING_DOWNLOADED_ARTIFACT_LOCK",
  "EXACT_FAILED_PREP_COLD_REMOVE",
  "EXACT_NEW_READONLY_JAR_REQUIRED",
  "EXACT_PREP_EXECUTOR_SOURCE_REQUIRED",
  "EXACT_PREP_HELPER_SOURCE_REQUIRED",
  "EXACT_SINGLE_DECODER_JAVA_SOURCE",
  "EXPLICIT_BOUNDED_STREAM_LIMITS_REQUIRED",
  "EXPORTED_CLASSPATH_BYTES_CHANGED",
  "FAILED_PREP_COLD_ABSENCE_REQUIRED",
  "FINITE_PREP_CUTOFF_AND_TIMEOUT_REQUIRED",
  "FIXED_ARGV_LIST_REQUIRED",
  "FRESH_CANONICAL_PRIVATE_PREP_ROOT",
  "FRESH_EMPTY_PRIVATE_JAR_OUTPUT_REQUIRED",
  "JAR_COUNT_AND_TOTAL_BOUND",
  "JAR_MANIFEST_ATTRIBUTE_REQUIRED",
  "JAR_MANIFEST_BYTES_BOUND",
  "JAR_MANIFEST_CLASSPATH_EXPANSION_REJECTED",
  "JAR_MANIFEST_CONTINUATION_REJECTED",
  "JAR_MANIFEST_DUPLICATE_ATTRIBUTE_REJECTED",
  "JAR_MANIFEST_UTF8_REQUIRED",
  "JAR_OUTPUT_ROOT_IDENTITY_CHANGED",
  "JAVA21_CLASS_HEADER_REQUIRED",
  "LARGE_STDOUT_MUST_STREAM_TO_ARCHIVE_FILE",
  "LINUX_PRIVATE_ARTIFACT_IO_REQUIRED",
  "LINUX_SELECTORS_PIPE_EXECUTION_REQUIRED",
  "NEW_CLASS_SEAL_FAILED",
  "NEW_JAR_CHANGED_DURING_ZIP_SCAN",
  "NEW_JAR_READBACK_BOUND",
  "NEW_JAR_READBACK_IDENTITY_CHANGED",
  "NEW_JAR_READBACK_WHOLE_SHA_CHANGED",
  "NONEMPTY_JARS_ROOT_REQUIRED",
  "NO_RUNNER_JAVA_OPTION_INJECTION",
  "ONE_EXACT_LOCKED_OFFICIAL_ICEBERG_ARTIFACT",
  "ONE_OWN_COLD_EXPORT_CONTAINER",
  "ONE_PINNED_PREP_IMAGE_REQUIRED",
  "ONE_UNAMBIGUOUS_JAR_MANIFEST_REQUIRED",
  "ONLY_BOUNDED_REGULAR_JAR_REQUIRED",
  "ONLY_EXACT_JARS_ROOT_REQUIRED",
  "ONLY_FRESH_PRIVATE_CLASSES_TARGET",
  "ONLY_LOCKED_RUNTIME_MAY_SUPPLY_ICEBERG_CLASSES",
  "ONLY_OWN_CLASS_PACKAGE_DIRECTORIES",
  "ONLY_OWN_SINGLE_LINK_JAVA21_CLASSES",
  "ONLY_UNIQUE_PAX_TIME_METADATA",
  "ONLY_USTAR_HEADER_REQUIRED",
  "OWNED_PRIVATE_DIRECTORY_REQUIRED",
  "OWN_COLD_EXPORT_ABSENCE_REQUIRED",
  "OWN_COLD_EXPORT_CLEANUP_UNVERIFIED_NO_RETRY",
  "OWN_COLD_EXPORT_REMOVE_RETURNED_EXACT_ID",
  "OWN_PREP_CHILD_REAP_UNVERIFIED",
  "OWN_PRIVATE_FOLDER_MODE700_REQUIRED",
  "PAX_EXACT_RECORD_LENGTH_REQUIRED",
  "PAX_TIME_METADATA_BOUND",
  "PREP_ABSOLUTE_CUTOFF_EXCEEDED",
  "PREP_ACTUAL_IMAGE_ENV_SHAPE",
  "PREP_ACTUAL_PINNED_IMAGE_WITHOUT_IMPLICIT_ACTORS",
  "PREP_BOUNDED_REGULAR_SINGLE_LINK_INPUT_REQUIRED",
  "PREP_BUDGET_AND_ORIGINAL_DISK_RESERVE",
  "PREP_CHILD_DEADLINE_ALREADY_EXPIRED",
  "PREP_CHILD_IO_FAILED_NO_RETRY",
  "PREP_CHILD_START_FAILED_NO_RETRY",
  "PREP_CHILD_TIMEOUT_NO_RETRY",
  "PREP_CREATED_FULL_CID_REQUIRED",
  "PREP_ENABLED_OOM_KILLER_REQUIRED",
  "PREP_FAILED_OR_UNKNOWN_NO_RETRY",
  "PREP_IMAGE_OPTION_INJECTION_REJECTED",
  "PREP_INPUT_IDENTITY_CHANGED",
  "PREP_KNOWN_CHILD_NONZERO_NO_RETRY",
  "PREP_ONLY_SAME_SOURCE_GITHUB_HOSTED_LINUX",
  "PREP_PRESERVE_EXISTING_EIGHT_GIB_RESERVE",
  "PREP_PRIVATE_RECORD_ALREADY_EXISTS_NO_RETRY",
  "PREP_STDERR_LIMIT_EXCEEDED_NO_RETRY",
  "PREP_STDOUT_LIMIT_EXCEEDED_NO_RETRY",
  "PREP_SUCCESS_NOT_OBSERVED",
  "PREP_WHOLE_INPUT_BOUND",
  "PRIVATE_DIRECTORY_IDENTITY_CHANGED",
  "PRIVATE_FOLDER_IDENTITY_CHANGED",
  "PRIVATE_JAR_IO_FAILED",
  "PRIVATE_PREP_FAILURE_RECEIPT_UNWRITABLE",
  "PRIVATE_PREP_ROOT_MODE",
  "SAME_EXISTING_SPARK_BASE_REFERENCE",
  "SEALED_CLASS_DIRECTORY_MODE_REQUIRED",
  "SEALED_CLASS_INVENTORY_READBACK",
  "SEALED_CLASS_WHOLE_BYTES_CHANGED",
  "STRICT_BOUNDED_JAR_MANIFEST_REQUIRED",
  "TAR_ASCII_NAME_REQUIRED",
  "TAR_BOUNDED_NAME_REQUIRED",
  "TAR_COMPLETE_BYTES_REQUIRED",
  "TAR_DIRECTORY_BOUND_REQUIRED",
  "TAR_HEADER_CHECKSUM_REQUIRED",
  "TAR_HEADER_COUNT_BOUND",
  "TAR_HIDDEN_TEXT_REJECTED",
  "TAR_LINK_TARGET_REJECTED",
  "TAR_OCTAL_FIELD_REQUIRED",
  "TAR_ONLY_DIRECTORY_OR_REGULAR_JAR",
  "TAR_PARENT_DIRECTORY_MUST_PRECEDE_CHILD",
  "TAR_SAFE_COMPONENTS_REQUIRED",
  "TAR_SAFE_RELATIVE_NAME_REQUIRED",
  "TAR_TRAILING_DATA_REJECTED",
  "TAR_TWO_ZERO_END_BLOCKS_REQUIRED",
  "TAR_ZERO_PADDING_REQUIRED",
  "VALID_BOUNDED_JAR_ZIP_REQUIRED",
  "ZIP_ENTRY_COUNT_BOUND",
  "ZIP_SAFE_ENTRY_NAME_REQUIRED"
] as const;
/** Additional literals belong only to the separately reviewed closed-classpath runtime. */
export const captureClasspathFailureCodes = [
  'JAR_MANIFEST_CLASSPATH_CLOSURE_BOUND',
  'JAR_MANIFEST_CLASSPATH_EXPORT_MAP_REQUIRED',
  'JAR_MANIFEST_CLASSPATH_REFERENCE_BOUND',
  'JAR_MANIFEST_CLASSPATH_TARGET_MISSING',
  'JAR_MANIFEST_CLASSPATH_TOKEN_REJECTED',
] as const;
/** Additional literals belong only to the separately reviewed bounded-manifest runtime. */
export const captureManifestBoundsFailureCodes = [
  'JAR_MANIFEST_DECLARED_EMPTY',
  'JAR_MANIFEST_DECLARED_SIZE_BOUND',
  'JAR_MANIFEST_READ_MISMATCH',
  'JAR_MANIFEST_AGGREGATE_BYTES_BOUND',
] as const;
/** Additional literals belong only to the separately reviewed verified-absence runtime. */
export const captureClasspathTreeFailureCodes = [
  'JAR_CLASSPATH_TREE_EXACT',
  'JAR_CLASSPATH_ABSENCE_UNVERIFIED',
  'JAR_CLASSPATH_TREE_REQUIRED',
  'JAR_CLASSPATH_CASE_ALIAS_REJECTED',
  'JAR_CLASSPATH_TREE_CHANGED',
  'JAR_CLASSPATH_TREE_IO_FAILED',
] as const;
/** Attempted validation phases only; these never identify an underlying cause. */
export const captureNormalizationPhaseCodes = [
  'NORMALIZE_AUTHORITY_UNVERIFIED',
  'NORMALIZE_DESCRIPTOR_UNVERIFIED',
  'NORMALIZE_DECODER_LIFECYCLE_UNVERIFIED',
  'NORMALIZE_PLANNER_SOURCE_UNVERIFIED',
  'NORMALIZE_REPLY_UNVERIFIED',
  'NORMALIZE_GRAPH_UNVERIFIED',
  'NORMALIZE_EXIT_BINDING_UNVERIFIED',
  'NORMALIZE_CLOCK_UNVERIFIED',
  'NORMALIZE_INVENTORY_UNVERIFIED',
  'NORMALIZE_PLAN_UNVERIFIED',
  'NORMALIZE_RESULT_UNVERIFIED',
] as const;
/** Additional attempted decoder guards belong only to their separately reviewed runtime. */
export const captureDecoderLifecyclePhaseCodes = [
  'NORMALIZE_DECODER_BUNDLE_UNVERIFIED',
  'NORMALIZE_DECODER_SOURCE_UNVERIFIED',
  'NORMALIZE_DECODER_IDENTITY_UNVERIFIED',
  'NORMALIZE_DECODER_CLOCK_UNVERIFIED',
  'NORMALIZE_DECODER_REPLY_BINDING_UNVERIFIED',
  'NORMALIZE_DECODER_WRITERS_AFTER_UNVERIFIED',
  'NORMALIZE_DECODER_ORDER_UNVERIFIED',
] as const;
/** Additional attempted reply guards belong only to the exact separately reviewed runtime. */
export const captureDecoderReplyPhaseCodes = [
  'NORMALIZE_DECODER_REPLY_PROOF_UNVERIFIED',
  'NORMALIZE_DECODER_REPLY_JSON_UNVERIFIED',
  'NORMALIZE_DECODER_REPLY_LINKS_UNVERIFIED',
] as const;
export type CaptureDiagnosticProfile = 'SCHEMA2_INITIAL' | 'SCHEMA2_CLOSED_CLASSPATH' | 'SCHEMA2_BOUNDED_MANIFEST' | 'SCHEMA2_VERIFIED_ABSENCE' | 'SCHEMA2_NORMALIZATION_PHASES' | 'SCHEMA2_DECODER_LIFECYCLE_PHASES' | 'SCHEMA2_DECODER_REPLY_PHASES';
export const captureStages = ["COMPLETED", "COMPOSITE", "DECODER", "LOAD_CLOSED_COPIES", "NORMALIZE", "ORIGINAL_MAIN", "PREP", "PRODUCER_PROOFS", "SUMMARY", "WRITERS_AFTER", "WRITERS_BEFORE"] as const;
export const prepChildClasses = {
  "compiler-java-version": "JAVA_VERSION",
  "compiler-javac-version": "JAVAC_VERSION",
  "pinned-image-pull": "IMAGE_PULL",
  "pinned-image-inspect": "IMAGE_INSPECT",
  "cold-export-create": "COLD_CREATE",
  "cold-export-before": "COLD_INSPECT",
  "export-classpath": "CLASSPATH_EXPORT",
  "cold-export-after": "COLD_INSPECT",
  "locked-iceberg-download": "ICEBERG_DOWNLOAD",
  "compile-main-only": "MAIN_COMPILE",
  "cold-export-before-remove": "COLD_INSPECT",
  "cold-export-remove": "COLD_REMOVE",
  "cold-export-absence": "COLD_ABSENCE",
  "failed-prep-cold-before-remove": "COLD_INSPECT",
  "failed-prep-cold-remove": "COLD_REMOVE",
  "failed-prep-cold-absence": "COLD_ABSENCE"
} as const;
export const prepChildOutcomes = ["EXITED_NONZERO", "EXITED_ZERO", "OUTPUT_OR_CONTROL_IO_FAILED", "OWN_CHILD_REAP_UNVERIFIED", "PREP_CUTOFF_EXCEEDED", "PRIVATE_OUTPUT_IO_UNVERIFIED", "START_FAILED", "STDERR_LIMIT_EXCEEDED", "STDOUT_LIMIT_EXCEEDED", "TIMED_OUT"] as const;

export type CaptureDiagnostic = {
  stageAttempted: typeof captureStages[number]; failureCode: typeof captureFailureCodes[number] | typeof captureClasspathFailureCodes[number] | typeof captureManifestBoundsFailureCodes[number] | typeof captureClasspathTreeFailureCodes[number] | typeof captureNormalizationPhaseCodes[number] | typeof captureDecoderLifecyclePhaseCodes[number] | typeof captureDecoderReplyPhaseCodes[number] | 'UNKNOWN' | null;
  lastPrepChild: { name: keyof typeof prepChildClasses; class: typeof prepChildClasses[keyof typeof prepChildClasses];
    outcome: typeof prepChildOutcomes[number]; returnCode: number | null; stdoutBytes: number; stderrBytes: number;
    timedOut: boolean; childStarted: boolean; childReaped: boolean } | null;
  prepCleanup: { knownColdCid: boolean; coldIdentityBound: boolean; coldRemovalAttempted: boolean; coldRemovedAndAbsent: boolean } | null;
};
const object = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === 'object' && !Array.isArray(value);
const exact = (value: Record<string, unknown>, keys: readonly string[]) => Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));
const integer = (value: unknown, minimum: number, maximum: number): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value >= minimum && value <= maximum;
export function parseCaptureDiagnostic(value: unknown, passed: boolean, profile: CaptureDiagnosticProfile = 'SCHEMA2_INITIAL'): CaptureDiagnostic | null {
  if (profile !== 'SCHEMA2_INITIAL' && profile !== 'SCHEMA2_CLOSED_CLASSPATH' && profile !== 'SCHEMA2_BOUNDED_MANIFEST' && profile !== 'SCHEMA2_VERIFIED_ABSENCE' && profile !== 'SCHEMA2_NORMALIZATION_PHASES' && profile !== 'SCHEMA2_DECODER_LIFECYCLE_PHASES' && profile !== 'SCHEMA2_DECODER_REPLY_PHASES') return null;
  if (!object(value) || !exact(value, ['stageAttempted', 'failureCode', 'lastPrepChild', 'prepCleanup'])
    || typeof value.stageAttempted !== 'string' || !(captureStages as readonly string[]).includes(value.stageAttempted)) return null;
  if (passed ? value.failureCode !== null : typeof value.failureCode !== 'string'
    || !(value.failureCode === 'UNKNOWN' || (captureFailureCodes as readonly string[]).includes(value.failureCode)
      || ((profile === 'SCHEMA2_CLOSED_CLASSPATH' || profile === 'SCHEMA2_BOUNDED_MANIFEST' || profile === 'SCHEMA2_VERIFIED_ABSENCE' || profile === 'SCHEMA2_NORMALIZATION_PHASES' || (profile === 'SCHEMA2_DECODER_LIFECYCLE_PHASES' || profile === 'SCHEMA2_DECODER_REPLY_PHASES'))
        && (captureClasspathFailureCodes as readonly string[]).includes(value.failureCode))
      || ((profile === 'SCHEMA2_BOUNDED_MANIFEST' || profile === 'SCHEMA2_VERIFIED_ABSENCE' || profile === 'SCHEMA2_NORMALIZATION_PHASES' || (profile === 'SCHEMA2_DECODER_LIFECYCLE_PHASES' || profile === 'SCHEMA2_DECODER_REPLY_PHASES'))
        && (captureManifestBoundsFailureCodes as readonly string[]).includes(value.failureCode))
      || ((profile === 'SCHEMA2_VERIFIED_ABSENCE' || profile === 'SCHEMA2_NORMALIZATION_PHASES' || (profile === 'SCHEMA2_DECODER_LIFECYCLE_PHASES' || profile === 'SCHEMA2_DECODER_REPLY_PHASES'))
        && (captureClasspathTreeFailureCodes as readonly string[]).includes(value.failureCode))
      || ((profile === 'SCHEMA2_NORMALIZATION_PHASES' || (profile === 'SCHEMA2_DECODER_LIFECYCLE_PHASES' || profile === 'SCHEMA2_DECODER_REPLY_PHASES')) && value.stageAttempted === 'NORMALIZE'
        && (captureNormalizationPhaseCodes as readonly string[]).includes(value.failureCode))
      || ((profile === 'SCHEMA2_DECODER_LIFECYCLE_PHASES' || profile === 'SCHEMA2_DECODER_REPLY_PHASES') && value.stageAttempted === 'NORMALIZE'
        && (captureDecoderLifecyclePhaseCodes as readonly string[]).includes(value.failureCode))
      || (profile === 'SCHEMA2_DECODER_REPLY_PHASES' && value.stageAttempted === 'NORMALIZE'
        && (captureDecoderReplyPhaseCodes as readonly string[]).includes(value.failureCode)))) return null;
  const child = value.lastPrepChild;
  if (child !== null) {
    if (!object(child) || !exact(child, ['name', 'class', 'outcome', 'returnCode', 'stdoutBytes', 'stderrBytes', 'timedOut', 'childStarted', 'childReaped'])
      || typeof child.name !== 'string' || !Object.hasOwn(prepChildClasses, child.name)
      || child.class !== prepChildClasses[child.name as keyof typeof prepChildClasses]
      || typeof child.outcome !== 'string' || !(prepChildOutcomes as readonly string[]).includes(child.outcome)
      || !(child.returnCode === null || integer(child.returnCode, -128, 255))
      || !integer(child.stdoutBytes, 0, 1040 * 1024 ** 2) || !integer(child.stderrBytes, 0, 65536)
      || !['timedOut', 'childStarted', 'childReaped'].every(key => typeof child[key] === 'boolean')
      || (child.childReaped && (!child.childStarted || child.returnCode === null))
      || (child.outcome === 'TIMED_OUT' && child.timedOut !== true)
      || (['EXITED_ZERO', 'EXITED_NONZERO'].includes(child.outcome)
        && (!child.childStarted || !child.childReaped || child.timedOut || child.returnCode === null))
      || (child.outcome === 'EXITED_ZERO' && child.returnCode !== 0)
      || (child.outcome === 'EXITED_NONZERO' && child.returnCode === 0)) return null;
  }
  const cleanup = value.prepCleanup;
  if (cleanup !== null && (!object(cleanup)
    || !exact(cleanup, ['knownColdCid', 'coldIdentityBound', 'coldRemovalAttempted', 'coldRemovedAndAbsent'])
    || !Object.values(cleanup).every(item => typeof item === 'boolean')
    || (cleanup.coldIdentityBound && !cleanup.knownColdCid)
    || (cleanup.coldRemovalAttempted && !cleanup.coldIdentityBound)
    || (cleanup.coldRemovedAndAbsent && !cleanup.coldRemovalAttempted))) return null;
  return value as unknown as CaptureDiagnostic;
}
