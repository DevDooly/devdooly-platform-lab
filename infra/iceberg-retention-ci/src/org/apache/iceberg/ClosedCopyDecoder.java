package org.apache.iceberg;

import java.io.ByteArrayInputStream;
import java.io.DataInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.concurrent.atomic.AtomicBoolean;
import org.apache.iceberg.avro.AvroSchemaUtil;
import org.apache.iceberg.io.CloseableIterable;
import org.apache.iceberg.io.FileIO;
import org.apache.iceberg.io.InputFile;
import org.apache.iceberg.io.OutputFile;
import org.apache.iceberg.io.SeekableInputStream;
import org.apache.iceberg.shaded.com.fasterxml.jackson.core.JsonFactory;
import org.apache.iceberg.shaded.com.fasterxml.jackson.core.JsonParser;
import org.apache.iceberg.shaded.com.fasterxml.jackson.core.StreamReadConstraints;
import org.apache.iceberg.shaded.com.fasterxml.jackson.databind.JsonNode;
import org.apache.iceberg.shaded.com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.iceberg.shaded.com.fasterxml.jackson.databind.node.ArrayNode;
import org.apache.iceberg.shaded.com.fasterxml.jackson.databind.node.ObjectNode;
import org.apache.iceberg.shaded.org.apache.avro.file.DataFileStream;
import org.apache.iceberg.shaded.org.apache.avro.generic.GenericDatumReader;

/** Version-locked private graph decoding from one bounded RAM frame. No OS FileIO. */
public final class ClosedCopyDecoder {
  static final byte[] MAGIC = "ICCPY001".getBytes(StandardCharsets.US_ASCII);
  static final int MAX_DESCRIPTOR = 512 * 1024, MAX_OBJECT = 4 * 1024 * 1024;
  static final int MAX_TOTAL = 32 * 1024 * 1024, MAX_REPLY = 4 * 1024 * 1024;
  static final String PRODUCER = "73e2293210aba3d9522013d923f8d97bd292baa4623736239d55cc21d9321fe2";
  static final String RUNTIME = "c63aded0a891bb66cb1fb2de591d67e237467681eb4a4e5a337b9d1d1b02d5e8";
  static final Set<String> REASONS = Set.of("FRAME_MAGIC", "FRAME_BOUND", "FRAME_EOF", "DESCRIPTOR_INVALID",
      "OBJECT_MAP_INVALID", "OBJECT_BYTES_MISMATCH", "METADATA_INVALID", "UNSUPPORTED_FORMAT",
      "UNSUPPORTED_METADATA_FEATURE", "UNSUPPORTED_CODEC", "UNSUPPORTED_SCHEMA", "UNSUPPORTED_ENTRY_CONTENT",
      "MISSING_APPROVED_CHILD", "FOREIGN_REFERENCE", "GRAPH_CONFLICT", "MISSING_SNAPSHOT_REFERENCE",
      "REFERENCE_CYCLE", "GRAPH_BOUND", "DECODER_INTERNAL", "DECODER_BUDGET_EXPIRED");
  static final ObjectMapper JSON;
  static {
    JsonFactory factory = new JsonFactory();
    factory.enable(JsonParser.Feature.STRICT_DUPLICATE_DETECTION);
    factory.setStreamReadConstraints(StreamReadConstraints.builder().maxNestingDepth(64)
        .maxStringLength(8192).maxNumberLength(128).build());
    JSON = new ObjectMapper(factory);
  }

  static final class Problem extends RuntimeException {
    final String code;
    Problem(String value) { super(null, null, false, false); code = REASONS.contains(value) ? value : "DECODER_INTERNAL"; }
  }
  static void need(boolean value, String code) { if (!value) throw new Problem(code); }
  static String sha(byte[] value) {
    try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value)); }
    catch (Exception ignored) { throw new Problem("DECODER_INTERNAL"); }
  }
  static byte[] bytes(String value) { return value.getBytes(StandardCharsets.UTF_8); }
  static Set<String> names(JsonNode value) {
    need(value != null && value.isObject(), "METADATA_INVALID");
    Set<String> result = new HashSet<>(); value.fieldNames().forEachRemaining(result::add); return result;
  }
  static void exact(JsonNode value, String code, String... fields) {
    need(value != null && value.isObject() && names(value).equals(Set.of(fields)), code);
  }
  static void allowed(JsonNode value, String... fields) {
    need(Set.of(fields).containsAll(names(value)), "UNSUPPORTED_METADATA_FEATURE");
  }
  static String text(JsonNode value, String code) {
    need(value != null && value.isTextual() && !value.textValue().isEmpty() && value.textValue().length() <= 8192, code);
    return value.textValue();
  }
  static long number(JsonNode value, long low, long high, String code) {
    need(value != null && value.isIntegralNumber() && value.canConvertToLong(), code);
    long result = value.longValue(); need(result >= low && result <= high, code); return result;
  }
  static List<JsonNode> array(JsonNode value, int maximum, String code) {
    need(value != null && value.isArray() && value.size() <= maximum, code);
    List<JsonNode> result = new ArrayList<>(); value.forEach(result::add); return result;
  }
  static JsonNode strictJson(byte[] raw, String code) {
    try {
      String decoded = StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
          .onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(raw)).toString();
      need(!decoded.startsWith("\ufeff"), code);
      try (JsonParser parser = JSON.getFactory().createParser(decoded)) {
        JsonNode value = JSON.readTree(parser);
        need(value != null && parser.nextToken() == null, code);
        strictTree(value, 0, new int[] {0}, code); return value;
      }
    } catch (Problem problem) { throw problem; }
    catch (Exception ignored) { throw new Problem(code); }
  }
  static void strictTree(JsonNode value, int depth, int[] count, String code) {
    need(depth <= 64 && ++count[0] <= 100000, code);
    if (value.isFloatingPointNumber()) need(Double.isFinite(value.doubleValue()), code);
    if (value.isTextual()) need(value.textValue().length() <= 8192, code);
    if (value.isArray()) need(value.size() <= 10000, code);
    if (value.isContainerNode()) for (JsonNode child : value) strictTree(child, depth + 1, count, code);
  }
  static String hashArray(String prefix, String... values) {
    try { return prefix + sha(JSON.writeValueAsBytes(Arrays.asList(values))); }
    catch (Exception ignored) { throw new Problem("DECODER_INTERNAL"); }
  }
  static final class Budget {
    final long deadline;
    Budget(long millis) { need(millis > 0 && millis <= 60000, "DECODER_BUDGET_EXPIRED"); deadline = System.nanoTime() + millis * 1000000; }
    void check() { need(System.nanoTime() < deadline && !Thread.currentThread().isInterrupted(), "DECODER_BUDGET_EXPIRED"); }
  }
  static final class Item {
    final String key, uri, id, digest; final int size; byte[] data; String kind = "UNKNOWN";
    Item(String key, String uri, String id, String digest, int size) {
      this.key = key; this.uri = uri; this.id = id; this.digest = digest; this.size = size;
    }
  }
  static final class Frame {
    final JsonNode descriptor; final String descriptorSha, location, currentUri;
    final Map<String, Item> byUri = new LinkedHashMap<>();
    Frame(JsonNode value, String digest, String location, String current) {
      descriptor = value; descriptorSha = digest; this.location = location; currentUri = current;
    }
    boolean inTarget(Item item) { return item.uri.startsWith(location + "/"); }
    Item lookup(String uri) {
      Item item = byUri.get(uri);
      need(item != null, uri != null && uri.startsWith(location + "/") ? "MISSING_APPROVED_CHILD" : "FOREIGN_REFERENCE");
      need(inTarget(item), "FOREIGN_REFERENCE"); return item;
    }
    Item mark(String uri, String kind) {
      Item item = lookup(uri); need(item.kind.equals("UNKNOWN") || item.kind.equals(kind), "GRAPH_CONFLICT"); item.kind = kind; return item;
    }
  }
  static byte[] readBytes(DataInputStream input, int length, Budget budget) throws IOException {
    need(length >= 0 && length <= MAX_OBJECT, "FRAME_BOUND"); budget.check();
    byte[] raw = input.readNBytes(length); need(raw.length == length, "FRAME_EOF"); budget.check(); return raw;
  }
  static Frame readFrame(InputStream input, Budget budget, String[] digest) throws IOException {
    DataInputStream stream = new DataInputStream(input);
    need(Arrays.equals(stream.readNBytes(8), MAGIC), "FRAME_MAGIC");
    int length = stream.readInt(); need(length > 0 && length <= MAX_DESCRIPTOR, "FRAME_BOUND");
    byte[] raw = readBytes(stream, length, budget); digest[0] = sha(raw);
    JsonNode d = strictJson(raw, "DESCRIPTOR_INVALID");
    exact(d, "DESCRIPTOR_INVALID", "schemaVersion", "scope", "sourceCommit", "producerSha256", "runtimeManifestSha256",
        "captureMapSha256", "approvedBucket", "approvedPrefix", "targetTable", "objects");
    need(number(d.get("schemaVersion"), 1, 1, "DESCRIPTOR_INVALID") == 1
        && text(d.get("scope"), "DESCRIPTOR_INVALID").equals("CLOSED_COPY_ICEBERG_FORMAT2_DECODE")
        && text(d.get("sourceCommit"), "DESCRIPTOR_INVALID").matches("[a-f0-9]{40}")
        && text(d.get("producerSha256"), "DESCRIPTOR_INVALID").equals(PRODUCER)
        && text(d.get("runtimeManifestSha256"), "DESCRIPTOR_INVALID").equals(RUNTIME)
        && text(d.get("captureMapSha256"), "DESCRIPTOR_INVALID").matches("[a-f0-9]{64}"), "DESCRIPTOR_INVALID");
    String bucket = text(d.get("approvedBucket"), "DESCRIPTOR_INVALID"), prefix = text(d.get("approvedPrefix"), "DESCRIPTOR_INVALID");
    need(bucket.matches("[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]") && prefix.matches("[A-Za-z0-9._/-]{1,1024}")
        && !prefix.startsWith("/") && prefix.endsWith("/") && !prefix.contains("//")
        && !Arrays.asList(prefix.split("/")).contains(".."), "DESCRIPTOR_INVALID");
    JsonNode target = d.get("targetTable"); exact(target, "DESCRIPTOR_INVALID", "catalog", "namespace", "table", "currentMetadataUri", "tableLocation");
    for (String name : List.of("catalog", "namespace", "table"))
      need(text(target.get(name), "DESCRIPTOR_INVALID").matches("[A-Za-z_][A-Za-z0-9_]{0,79}"), "DESCRIPTOR_INVALID");
    String location = text(target.get("tableLocation"), "DESCRIPTOR_INVALID"), current = text(target.get("currentMetadataUri"), "DESCRIPTOR_INVALID");
    need(location.startsWith("s3://" + bucket + "/" + prefix) && !location.endsWith("/")
        && current.startsWith(location + "/metadata/"), "DESCRIPTOR_INVALID");
    Frame frame = new Frame(d, digest[0], location, current);
    List<JsonNode> records = array(d.get("objects"), 128, "OBJECT_MAP_INVALID");
    need(!records.isEmpty() && stream.readInt() == records.size(), "FRAME_BOUND");
    Set<String> aliases = new HashSet<>(), copies = new HashSet<>(); String previous = null; long total = 0;
    for (JsonNode record : records) {
      budget.check(); exact(record, "OBJECT_MAP_INVALID", "key", "size", "sha256", "copy", "alias");
      String key = text(record.get("key"), "OBJECT_MAP_INVALID"), id = text(record.get("alias"), "OBJECT_MAP_INVALID");
      String hash = text(record.get("sha256"), "OBJECT_MAP_INVALID"), copy = text(record.get("copy"), "OBJECT_MAP_INVALID");
      int size = (int) number(record.get("size"), 0, MAX_OBJECT, "OBJECT_MAP_INVALID");
      need(key.matches("[A-Za-z0-9._/-]{1,1024}") && key.startsWith(prefix) && !key.contains("//")
          && !Arrays.asList(key.split("/")).contains("..") && (previous == null || previous.compareTo(key) < 0)
          && hash.matches("[a-f0-9]{64}") && copy.equals(sha(bytes(key)) + ".bin")
          && id.equals(hashArray("f-", bucket, key)) && aliases.add(id) && copies.add(copy), "OBJECT_MAP_INVALID");
      previous = key; total += size; need(total <= MAX_TOTAL, "FRAME_BOUND");
      need(stream.readInt() == size, "OBJECT_BYTES_MISMATCH");
      Item item = new Item(key, "s3://" + bucket + "/" + key, id, hash, size);
      item.data = readBytes(stream, size, budget); need(sha(item.data).equals(hash), "OBJECT_BYTES_MISMATCH");
      need(frame.byUri.put(item.uri, item) == null, "OBJECT_MAP_INVALID");
    }
    need(stream.read() == -1, "FRAME_EOF"); budget.check(); frame.lookup(current); return frame;
  }

  static final class ClosedMapIO implements FileIO {
    final Frame frame; final Budget budget; final Set<SeekableInputStream> streams = new HashSet<>();
    ClosedMapIO(Frame frame, Budget budget) { this.frame = frame; this.budget = budget; }
    public OutputFile newOutputFile(String ignored) { throw new Problem("FOREIGN_REFERENCE"); }
    public void deleteFile(String ignored) { throw new Problem("FOREIGN_REFERENCE"); }
    public InputFile newInputFile(String uri) {
      Item item = frame.lookup(uri);
      return new InputFile() {
        public long getLength() { return item.size; }
        public String location() { return item.uri; }
        public boolean exists() { return true; }
        public SeekableInputStream newStream() {
          budget.check();
          SeekableInputStream stream = new SeekableInputStream() {
            int position; boolean closed;
            void active() { need(!closed, "DECODER_INTERNAL"); budget.check(); }
            public long getPos() { active(); return position; }
            public void seek(long next) { active(); need(next >= 0 && next <= item.size, "FRAME_BOUND"); position = (int) next; }
            public int read() { active(); return position == item.size ? -1 : item.data[position++] & 255; }
            public int read(byte[] target, int offset, int length) {
              active(); if (length == 0) return 0; if (position == item.size) return -1;
              int count = Math.min(length, item.size - position); System.arraycopy(item.data, position, target, offset, count); position += count; return count;
            }
            public void close() { if (!closed) { closed = true; streams.remove(this); } }
          };
          streams.add(stream); return stream;
        }
      };
    }
    public void close() { for (SeekableInputStream stream : new ArrayList<>(streams)) try { stream.close(); } catch (Exception ignored) {} }
  }

  static final class Graph {
    final Frame frame; final ObjectNode node = JSON.createObjectNode(), completeness, provenance;
    final ArrayNode metadata, snapshots, refs, edges, files;
    final Set<String> edgeKeys = new HashSet<>();
    Graph(Frame frame) {
      this.frame = frame; node.putNull("tableId"); node.put("currentMetadataId", frame.lookup(frame.currentUri).id); node.putNull("currentSnapshotId");
      metadata = node.putArray("metadataNodes"); snapshots = node.putArray("snapshotNodes"); refs = node.putArray("refNodes");
      files = node.putArray("fileNodes"); edges = node.putArray("edges"); completeness = node.putObject("completeness");
      completeness.put("metadataDecoded", false).put("refsDecoded", false).put("snapshotFileClosureDecoded", false);
      provenance = node.putObject("decoderProvenance");
      provenance.putNull("formatVersion").putNull("schemaCount").putNull("partitionSpecCount").putNull("sortOrderCount");
      provenance.put("mainRefDefaulted", false).put("allEntriesIncludingDeleted", false).put("streamsClosed", false);
      ArrayNode outside = provenance.putArray("outsideTarget");
      for (Item item : frame.byUri.values()) if (!frame.inTarget(item))
        outside.addObject().put("id", item.id).put("size", item.size).put("sha256", item.digest).put("action", "KEEP");
      provenance.put("networkImplemented", false).put("fileIoCreateDeleteSupported", false)
          .put("parquetContentsVerified", false).put("historicalMetadataRestoreVerified", false);
    }
    void edge(String source, String target, String kind, String status) {
      String identity = source + "|" + target + "|" + kind + "|" + status;
      if (edgeKeys.add(identity)) {
        need(edges.size() < 100000, "GRAPH_BOUND"); ObjectNode row = edges.addObject().put("source", source).put("target", target).put("kind", kind);
        if (status == null) row.putNull("status"); else row.put("status", status);
      }
    }
    void finish() {
      files.removeAll(); for (Item item : frame.byUri.values()) if (frame.inTarget(item))
        files.addObject().put("id", item.id).put("kind", item.kind).put("size", item.size).put("sha256", item.digest);
    }
  }

  static void schemaType(JsonNode type, Set<Integer> ids) {
    need(type != null, "UNSUPPORTED_SCHEMA");
    if (type.isTextual()) {
      String value = type.textValue();
      need(value.matches("boolean|int|long|float|double|date|time|timestamp|timestamptz|string|uuid|binary|fixed\\[[1-9][0-9]*\\]|decimal\\([1-9][0-9]*,[0-9]+\\)"), "UNSUPPORTED_SCHEMA"); return;
    }
    String name = text(type.get("type"), "UNSUPPORTED_SCHEMA");
    switch (name) {
      case "struct" -> { exact(type, "UNSUPPORTED_SCHEMA", "type", "fields"); schemaFields(type.get("fields"), ids); }
      case "list" -> {
        exact(type, "UNSUPPORTED_SCHEMA", "type", "element-id", "element", "element-required");
        need(ids.add((int) number(type.get("element-id"), 1, Integer.MAX_VALUE, "UNSUPPORTED_SCHEMA")) && type.get("element-required").isBoolean(), "UNSUPPORTED_SCHEMA");
        schemaType(type.get("element"), ids);
      }
      case "map" -> {
        exact(type, "UNSUPPORTED_SCHEMA", "type", "key-id", "key", "value-id", "value", "value-required");
        need(ids.add((int) number(type.get("key-id"), 1, Integer.MAX_VALUE, "UNSUPPORTED_SCHEMA"))
            && ids.add((int) number(type.get("value-id"), 1, Integer.MAX_VALUE, "UNSUPPORTED_SCHEMA")) && type.get("value-required").isBoolean(), "UNSUPPORTED_SCHEMA");
        schemaType(type.get("key"), ids); schemaType(type.get("value"), ids);
      }
      default -> throw new Problem("UNSUPPORTED_SCHEMA");
    }
  }
  static void schemaFields(JsonNode rows, Set<Integer> ids) {
    Set<String> names = new HashSet<>();
    for (JsonNode field : array(rows, 1000, "UNSUPPORTED_SCHEMA")) {
      allowed(field, "id", "name", "required", "type", "doc");
      need(ids.add((int) number(field.get("id"), 1, Integer.MAX_VALUE, "UNSUPPORTED_SCHEMA"))
          && names.add(text(field.get("name"), "UNSUPPORTED_SCHEMA")) && field.get("required") != null && field.get("required").isBoolean(), "UNSUPPORTED_SCHEMA");
      if (field.has("doc")) need(field.get("doc").isTextual(), "UNSUPPORTED_SCHEMA");
      schemaType(field.get("type"), ids);
    }
  }
  static void validateMetadata(JsonNode root) {
    allowed(root, "format-version", "table-uuid", "location", "last-sequence-number", "last-updated-ms", "last-column-id", "schemas",
        "current-schema-id", "partition-specs", "default-spec-id", "last-partition-id", "properties", "current-snapshot-id",
        "snapshots", "snapshot-log", "metadata-log", "sort-orders", "default-sort-order-id", "refs", "statistics", "partition-statistics");
    for (String optional : List.of("statistics", "partition-statistics")) if (root.has(optional))
      need(root.get(optional).isArray() && root.get(optional).isEmpty(), "UNSUPPORTED_METADATA_FEATURE");
    need(number(root.get("format-version"), 1, 3, "UNSUPPORTED_FORMAT") == 2, "UNSUPPORTED_FORMAT");
    need(text(root.get("table-uuid"), "METADATA_INVALID").matches("[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}"), "METADATA_INVALID");
    number(root.get("last-sequence-number"), 0, Long.MAX_VALUE, "METADATA_INVALID"); number(root.get("last-updated-ms"), 0, 253402300799999L, "METADATA_INVALID");
    number(root.get("last-column-id"), 0, Integer.MAX_VALUE, "METADATA_INVALID");
    Set<Integer> allIds = new HashSet<>(), schemaIds = new HashSet<>(), specIds = new HashSet<>(), sortIds = new HashSet<>();
    for (JsonNode schema : array(root.get("schemas"), 1000, "UNSUPPORTED_SCHEMA")) {
      allowed(schema, "type", "schema-id", "fields", "identifier-field-ids");
      need(text(schema.get("type"), "UNSUPPORTED_SCHEMA").equals("struct")
          && schemaIds.add((int) number(schema.get("schema-id"), 0, Integer.MAX_VALUE, "UNSUPPORTED_SCHEMA")), "UNSUPPORTED_SCHEMA");
      Set<Integer> ids = new HashSet<>(); schemaFields(schema.get("fields"), ids); allIds.addAll(ids);
      if (schema.has("identifier-field-ids")) for (JsonNode id : array(schema.get("identifier-field-ids"), 1000, "UNSUPPORTED_SCHEMA"))
        need(ids.contains((int) number(id, 1, Integer.MAX_VALUE, "UNSUPPORTED_SCHEMA")), "UNSUPPORTED_SCHEMA");
    }
    need(schemaIds.contains((int) number(root.get("current-schema-id"), 0, Integer.MAX_VALUE, "UNSUPPORTED_SCHEMA")), "UNSUPPORTED_SCHEMA");
    for (JsonNode spec : array(root.get("partition-specs"), 1000, "UNSUPPORTED_SCHEMA")) {
      exact(spec, "UNSUPPORTED_SCHEMA", "spec-id", "fields"); need(specIds.add((int) number(spec.get("spec-id"), 0, Integer.MAX_VALUE, "UNSUPPORTED_SCHEMA")), "UNSUPPORTED_SCHEMA");
      Set<Integer> fieldIds = new HashSet<>(); Set<String> fieldNames = new HashSet<>();
      for (JsonNode field : array(spec.get("fields"), 1000, "UNSUPPORTED_SCHEMA")) {
        exact(field, "UNSUPPORTED_SCHEMA", "name", "transform", "source-id", "field-id");
        need(allIds.contains((int) number(field.get("source-id"), 1, Integer.MAX_VALUE, "UNSUPPORTED_SCHEMA"))
            && fieldIds.add((int) number(field.get("field-id"), 1, Integer.MAX_VALUE, "UNSUPPORTED_SCHEMA"))
            && fieldNames.add(text(field.get("name"), "UNSUPPORTED_SCHEMA"))
            && text(field.get("transform"), "UNSUPPORTED_SCHEMA").matches("identity|void|year|month|day|hour|bucket\\[[1-9][0-9]*\\]|truncate\\[[1-9][0-9]*\\]"), "UNSUPPORTED_SCHEMA");
      }
    }
    need(specIds.contains((int) number(root.get("default-spec-id"), 0, Integer.MAX_VALUE, "UNSUPPORTED_SCHEMA")), "UNSUPPORTED_SCHEMA");
    number(root.get("last-partition-id"), 0, Integer.MAX_VALUE, "UNSUPPORTED_SCHEMA");
    for (JsonNode sort : array(root.get("sort-orders"), 1000, "UNSUPPORTED_SCHEMA")) {
      exact(sort, "UNSUPPORTED_SCHEMA", "order-id", "fields"); need(sortIds.add((int) number(sort.get("order-id"), 0, Integer.MAX_VALUE, "UNSUPPORTED_SCHEMA")), "UNSUPPORTED_SCHEMA");
      for (JsonNode field : array(sort.get("fields"), 1000, "UNSUPPORTED_SCHEMA")) {
        exact(field, "UNSUPPORTED_SCHEMA", "transform", "source-id", "direction", "null-order");
        need(allIds.contains((int) number(field.get("source-id"), 1, Integer.MAX_VALUE, "UNSUPPORTED_SCHEMA"))
            && Set.of("asc", "desc").contains(text(field.get("direction"), "UNSUPPORTED_SCHEMA"))
            && Set.of("nulls-first", "nulls-last").contains(text(field.get("null-order"), "UNSUPPORTED_SCHEMA"))
            && text(field.get("transform"), "UNSUPPORTED_SCHEMA").matches("identity|void|year|month|day|hour|bucket\\[[1-9][0-9]*\\]|truncate\\[[1-9][0-9]*\\]"), "UNSUPPORTED_SCHEMA");
      }
    }
    need(sortIds.contains((int) number(root.get("default-sort-order-id"), 0, Integer.MAX_VALUE, "UNSUPPORTED_SCHEMA")), "UNSUPPORTED_SCHEMA");
    if (root.has("properties")) for (JsonNode value : root.get("properties")) need(value.isTextual(), "METADATA_INVALID");
    if (root.has("refs")) for (JsonNode ref : root.get("refs")) {
      allowed(ref, "snapshot-id", "type", "min-snapshots-to-keep", "max-snapshot-age-ms", "max-ref-age-ms");
      number(ref.get("snapshot-id"), 1, Long.MAX_VALUE, "METADATA_INVALID");
      need(Set.of("branch", "tag").contains(text(ref.get("type"), "METADATA_INVALID")), "UNSUPPORTED_METADATA_FEATURE");
      for (String name : List.of("min-snapshots-to-keep", "max-snapshot-age-ms", "max-ref-age-ms")) if (ref.has(name)) number(ref.get(name), 1, Long.MAX_VALUE, "METADATA_INVALID");
    }
    for (JsonNode snapshot : array(root.get("snapshots"), 10000, "METADATA_INVALID")) {
      allowed(snapshot, "sequence-number", "snapshot-id", "parent-snapshot-id", "timestamp-ms", "summary", "manifest-list", "schema-id");
      number(snapshot.get("sequence-number"), 0, Long.MAX_VALUE, "METADATA_INVALID"); number(snapshot.get("snapshot-id"), 1, Long.MAX_VALUE, "METADATA_INVALID");
      if (snapshot.has("parent-snapshot-id")) number(snapshot.get("parent-snapshot-id"), 1, Long.MAX_VALUE, "METADATA_INVALID");
      number(snapshot.get("timestamp-ms"), 0, 253402300799999L, "METADATA_INVALID"); text(snapshot.get("manifest-list"), "METADATA_INVALID");
      if (snapshot.has("schema-id")) need(schemaIds.contains((int) number(snapshot.get("schema-id"), 0, Integer.MAX_VALUE, "METADATA_INVALID")), "METADATA_INVALID");
      need(snapshot.get("summary") != null && snapshot.get("summary").isObject(), "METADATA_INVALID");
      for (JsonNode value : snapshot.get("summary")) need(value.isTextual(), "METADATA_INVALID");
    }
    for (JsonNode row : array(root.get("snapshot-log"), 10000, "METADATA_INVALID")) {
      exact(row, "METADATA_INVALID", "timestamp-ms", "snapshot-id"); number(row.get("timestamp-ms"), 0, 253402300799999L, "METADATA_INVALID"); number(row.get("snapshot-id"), 1, Long.MAX_VALUE, "METADATA_INVALID");
    }
    for (JsonNode row : array(root.get("metadata-log"), 128, "METADATA_INVALID")) {
      exact(row, "METADATA_INVALID", "timestamp-ms", "metadata-file"); number(row.get("timestamp-ms"), 0, 253402300799999L, "METADATA_INVALID"); text(row.get("metadata-file"), "METADATA_INVALID");
    }
  }

  static void avroSchema(ClosedMapIO io, Item item, Schema expected) throws IOException {
    try (InputStream raw = io.newInputFile(item.uri).newStream();
         DataFileStream<Object> header = new DataFileStream<>(raw, new GenericDatumReader<>())) {
      need(AvroSchemaUtil.toIceberg(header.getSchema()).asStruct().equals(expected.asStruct()), "UNSUPPORTED_SCHEMA");
    }
  }
  static String buffer(ByteBuffer value) {
    if (value == null) return "NULL"; ByteBuffer copy = value.duplicate(); byte[] raw = new byte[copy.remaining()]; copy.get(raw); return sha(raw);
  }
  static String manifestIdentity(ManifestFile file) {
    need(file.keyMetadata() == null || file.keyMetadata().remaining() == 0, "UNSUPPORTED_METADATA_FEATURE");
    need(file.firstRowId() == null, "UNSUPPORTED_METADATA_FEATURE");
    StringBuilder parts = new StringBuilder();
    parts.append(file.length()).append('|').append(file.partitionSpecId()).append('|').append(file.content()).append('|')
        .append(file.sequenceNumber()).append('|').append(file.minSequenceNumber()).append('|').append(file.snapshotId()).append('|')
        .append(file.addedFilesCount()).append('|').append(file.existingFilesCount()).append('|').append(file.deletedFilesCount()).append('|')
        .append(file.addedRowsCount()).append('|').append(file.existingRowsCount()).append('|').append(file.deletedRowsCount());
    parts.append(file.partitions() == null ? "|NULL" : "|PRESENT");
    if (file.partitions() != null) for (ManifestFile.PartitionFieldSummary row : file.partitions())
      parts.append('|').append(row.containsNull()).append('|').append(row.containsNaN()).append('|').append(buffer(row.lowerBound())).append('|').append(buffer(row.upperBound()));
    return parts.toString();
  }
  static Set<String> manifest(ManifestFile manifest, TableMetadata table, ClosedMapIO io, Graph graph, Budget budget) throws IOException {
    Item parent = graph.frame.mark(manifest.path(), "MANIFEST");
    need(manifest.length() == parent.size && table.specsById().containsKey(manifest.partitionSpecId())
        && Set.of(ManifestContent.DATA, ManifestContent.DELETES).contains(manifest.content()), "GRAPH_CONFLICT");
    avroSchema(io, parent, V2Metadata.entrySchema(table.specsById().get(manifest.partitionSpecId()).partitionType()));
    Set<String> files = new TreeSet<>(), seen = new HashSet<>(); files.add(parent.id);
    try (ManifestReader<?> reader = ManifestFiles.open(manifest, io, table.specsById());
         CloseableIterable<? extends ManifestEntry<?>> entries = reader.entries()) {
      int count = 0;
      for (ManifestEntry<?> entry : entries) {
        budget.check(); need(++count <= 10000, "GRAPH_BOUND");
        String status = entry.status().name(); need(Set.of("ADDED", "EXISTING", "DELETED").contains(status), "UNSUPPORTED_ENTRY_CONTENT");
        ContentFile<?> file = entry.file(); boolean deletion = file instanceof DeleteFile;
        need(file.content() == FileContent.DATA && !deletion && manifest.content() == ManifestContent.DATA
            || file.content() == FileContent.POSITION_DELETES && deletion && manifest.content() == ManifestContent.DELETES, "UNSUPPORTED_ENTRY_CONTENT");
        need(file.keyMetadata() == null || file.keyMetadata().remaining() == 0, "UNSUPPORTED_METADATA_FEATURE");
        need(file.firstRowId() == null && (file.equalityFieldIds() == null || file.equalityFieldIds().isEmpty()), "UNSUPPORTED_ENTRY_CONTENT");
        need(file.recordCount() >= 0 && table.specsById().containsKey(file.specId()) && Set.of(FileFormat.PARQUET, FileFormat.ORC, FileFormat.AVRO).contains(file.format()), "UNSUPPORTED_ENTRY_CONTENT");
        Item child = graph.frame.mark(file.location(), deletion ? "DELETE" : "DATA");
        need(file.fileSizeInBytes() == child.size && seen.add(child.id), "GRAPH_CONFLICT"); files.add(child.id);
        graph.edge(parent.id, child.id, deletion ? "MANIFEST_DELETE" : "MANIFEST_DATA", status);
        if (deletion) {
          DeleteFile deleted = (DeleteFile) file;
          need(deleted.contentOffset() == null && deleted.contentSizeInBytes() == null, "UNSUPPORTED_ENTRY_CONTENT");
          if (deleted.referencedDataFile() != null) {
            Item referenced = graph.frame.mark(deleted.referencedDataFile(), "DATA"); files.add(referenced.id);
            graph.edge(child.id, referenced.id, "DELETE_REFERENCED_DATA", null);
          }
        }
      }
    }
    return files;
  }

  static void collect(Frame frame, Graph graph, ClosedMapIO io, Budget budget) throws IOException {
    need(frame.currentUri.endsWith(".metadata.json"), "UNSUPPORTED_CODEC");
    Item current = frame.mark(frame.currentUri, "METADATA");
    graph.metadata.addObject().put("id", current.id).put("role", "CURRENT");
    JsonNode raw = strictJson(current.data, "METADATA_INVALID"); validateMetadata(raw);
    need(text(raw.get("location"), "METADATA_INVALID").equals(frame.location), "FOREIGN_REFERENCE");
    TableMetadata table;
    try { table = TableMetadataParser.fromJson(frame.currentUri, raw); }
    catch (Exception ignored) { throw new Problem("METADATA_INVALID"); }
    need(table.formatVersion() == 2 && table.statisticsFiles().isEmpty() && table.partitionStatisticsFiles().isEmpty()
        && table.encryptionKeys().isEmpty(), "UNSUPPORTED_METADATA_FEATURE");
    JsonNode identity = frame.descriptor.get("targetTable");
    graph.node.put("tableId", hashArray("t-", identity.get("catalog").textValue(), identity.get("namespace").textValue(), identity.get("table").textValue(), table.uuid()));
    need(table.currentSnapshot() != null, "MISSING_SNAPSHOT_REFERENCE"); graph.node.put("currentSnapshotId", String.valueOf(table.currentSnapshot().snapshotId()));
    graph.provenance.put("formatVersion", 2).put("schemaCount", table.schemas().size()).put("partitionSpecCount", table.specs().size()).put("sortOrderCount", table.sortOrders().size());
    Set<String> metadataIds = new HashSet<>(); metadataIds.add(current.id);
    for (TableMetadata.MetadataLogEntry prior : table.previousFiles()) {
      Item child = frame.mark(prior.file(), "METADATA"); need(metadataIds.add(child.id), "GRAPH_CONFLICT");
      graph.metadata.addObject().put("id", child.id).put("role", "HISTORICAL"); graph.edge(current.id, child.id, "METADATA_LOG", null);
    }
    TreeMap<Long, Snapshot> snapshots = new TreeMap<>();
    need(table.snapshots().size() == raw.get("snapshots").size(), "GRAPH_CONFLICT");
    for (Snapshot snapshot : table.snapshots()) need(snapshots.put(snapshot.snapshotId(), snapshot) == null, "GRAPH_CONFLICT");
    for (Snapshot snapshot : snapshots.values()) {
      Set<Long> chain = new HashSet<>(); Snapshot parent = snapshot;
      while (parent != null) {
        budget.check(); need(chain.add(parent.snapshotId()), "REFERENCE_CYCLE");
        Long pid = parent.parentId(); if (pid == null) break;
        need(snapshots.containsKey(pid), "MISSING_SNAPSHOT_REFERENCE"); Snapshot next = snapshots.get(pid);
        need(next.timestampMillis() <= parent.timestampMillis(), "GRAPH_CONFLICT"); parent = next;
      }
      need(snapshot.sequenceNumber() <= table.lastSequenceNumber() && snapshot.schemaId() != null && table.schemasById().containsKey(snapshot.schemaId())
          && Set.of("append", "replace", "overwrite", "delete").contains(snapshot.operation())
          && snapshot.firstRowId() == null && snapshot.addedRows() == null && snapshot.keyId() == null, "UNSUPPORTED_METADATA_FEATURE");
    }
    for (HistoryEntry row : table.snapshotLog()) need(snapshots.containsKey(row.snapshotId()), "MISSING_SNAPSHOT_REFERENCE");
    for (Map.Entry<String, SnapshotRef> row : new TreeMap<>(table.refs()).entrySet()) {
      need(snapshots.containsKey(row.getValue().snapshotId()), "MISSING_SNAPSHOT_REFERENCE");
      graph.refs.addObject().put("name", "r-" + sha(bytes(row.getKey()))).put("kind", row.getValue().isBranch() ? "BRANCH" : "TAG").put("snapshotId", String.valueOf(row.getValue().snapshotId()));
    }
    if (!raw.has("refs")) {
      need(table.refs().size() == 1 && table.refs().containsKey("main") && table.refs().get("main").isBranch()
          && table.refs().get("main").snapshotId() == table.currentSnapshot().snapshotId(), "METADATA_INVALID");
      graph.provenance.put("mainRefDefaulted", true);
    } else need(table.refs().keySet().equals(names(raw.get("refs"))), "GRAPH_CONFLICT");
    graph.completeness.put("metadataDecoded", true).put("refsDecoded", true);
    Map<String, List<ManifestFile>> lists = new HashMap<>(); Map<String, Set<String>> decoded = new HashMap<>(); Map<String, String> identities = new HashMap<>();
    for (Snapshot snapshot : snapshots.values()) {
      budget.check(); Item list = frame.mark(snapshot.manifestListLocation(), "MANIFEST_LIST");
      graph.edge(String.valueOf(snapshot.snapshotId()), list.id, "SNAPSHOT_MANIFEST_LIST", null);
      if (!lists.containsKey(list.id)) {
        avroSchema(io, list, V2Metadata.MANIFEST_LIST_SCHEMA);
        List<ManifestFile> manifests = ManifestLists.read(io.newInputFile(list.uri)); need(manifests.size() <= 10000, "GRAPH_BOUND"); lists.put(list.id, manifests);
      }
      TreeSet<String> closure = new TreeSet<>(); closure.add(list.id);
      Set<String> manifestIds = new HashSet<>();
      for (ManifestFile manifest : lists.get(list.id)) {
        budget.check(); Item child = frame.mark(manifest.path(), "MANIFEST"); graph.edge(list.id, child.id, "LIST_MANIFEST", null);
        need(manifestIds.add(child.id), "GRAPH_CONFLICT");
        String fingerprint = manifestIdentity(manifest);
        need(!identities.containsKey(child.id) || identities.get(child.id).equals(fingerprint), "GRAPH_CONFLICT"); identities.put(child.id, fingerprint);
        if (!decoded.containsKey(child.id)) decoded.put(child.id, manifest(manifest, table, io, graph, budget));
        closure.addAll(decoded.get(child.id));
      }
      ObjectNode node = graph.snapshots.addObject().put("id", String.valueOf(snapshot.snapshotId())).put("committedAt", Instant.ofEpochMilli(snapshot.timestampMillis()).toString()).put("manifestListId", list.id);
      if (snapshot.parentId() == null) node.putNull("parentId"); else node.put("parentId", String.valueOf(snapshot.parentId()));
      ArrayNode ids = node.putArray("fileIds"); closure.forEach(ids::add);
    }
    graph.provenance.put("allEntriesIncludingDeleted", true); graph.completeness.put("snapshotFileClosureDecoded", true);
    need(frame.byUri.values().stream().noneMatch(item -> frame.inTarget(item) && item.kind.equals("UNKNOWN")), "UNSUPPORTED_METADATA_FEATURE");
  }

  static ObjectNode reply(String status, String reason, String descriptor, Graph graph) {
    ObjectNode result = JSON.createObjectNode().put("schemaVersion", 1).put("scope", "CLOSED_COPY_ICEBERG_FORMAT2_GRAPH").put("status", status);
    ArrayNode reasons = result.putArray("reasonCodes"); if (reason != null) reasons.add(reason);
    if (descriptor == null) result.putNull("descriptorSha256"); else result.put("descriptorSha256", descriptor);
    if (graph == null) result.putNull("graph"); else { graph.finish(); result.set("graph", graph.node); }
    return result;
  }
  static ObjectNode decode(InputStream input, long budgetMillis) {
    String[] digest = {null}; Frame frame = null; Graph graph = null;
    try {
      Budget budget = new Budget(budgetMillis); frame = readFrame(input, budget, digest); graph = new Graph(frame);
      try (ClosedMapIO io = new ClosedMapIO(frame, budget)) {
        try { collect(frame, graph, io, budget); }
        finally { io.close(); graph.provenance.put("streamsClosed", io.streams.isEmpty()); }
      }
      budget.check(); return reply("DECODED", null, digest[0], graph);
    } catch (Problem problem) {
      if (graph != null) graph.completeness.put("snapshotFileClosureDecoded", false);
      return reply(graph == null ? "REJECTED" : "UNDETERMINED", problem.code, digest[0], graph);
    } catch (java.io.EOFException ignored) {
      return reply(graph == null ? "REJECTED" : "UNDETERMINED", "FRAME_EOF", digest[0], graph);
    } catch (Exception ignored) {
      if (graph != null) graph.completeness.put("snapshotFileClosureDecoded", false);
      return reply(graph == null ? "REJECTED" : "UNDETERMINED", "DECODER_INTERNAL", digest[0], graph);
    }
  }
  public static void main(String[] args) {
    long millis;
    try {
      need(args.length == 2 && args[0].equals("--budget-millis") && args[1].matches("[1-9][0-9]{0,4}"), "DESCRIPTOR_INVALID");
      millis = Long.parseLong(args[1]); need(millis <= 60000, "DESCRIPTOR_INVALID");
    } catch (Throwable ignored) { System.err.println("DECODER_ARGUMENTS_REJECTED"); System.exit(3); return; }
    AtomicBoolean done = new AtomicBoolean();
    Thread watchdog = new Thread(() -> {
      try { Thread.sleep(millis); } catch (InterruptedException ignored) { return; }
      if (!done.get()) { System.err.println("DECODER_BUDGET_EXPIRED"); Runtime.getRuntime().halt(124); }
    }, "closed-copy-relative-budget"); watchdog.setDaemon(true); watchdog.start();
    try {
      ObjectNode result = decode(System.in, millis);
      byte[] raw = JSON.writeValueAsBytes(result);
      if (raw.length + 1 > MAX_REPLY) { result = reply("REJECTED", "GRAPH_BOUND", result.path("descriptorSha256").isTextual() ? result.path("descriptorSha256").textValue() : null, null); raw = JSON.writeValueAsBytes(result); }
      System.out.write(raw); System.out.write('\n'); System.out.flush();
      done.set(true); watchdog.interrupt();
      System.exit(result.path("status").asText().equals("DECODED") ? 0 : result.path("status").asText().equals("UNDETERMINED") ? 2 : 3);
    } catch (Throwable ignored) {
      done.set(true); watchdog.interrupt(); System.err.println("DECODER_FAILED_WITHOUT_COMPLETE_REPLY"); System.exit(3);
    }
  }
}
