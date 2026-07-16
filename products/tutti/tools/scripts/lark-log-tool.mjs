#!/usr/bin/env node
import { spawnSync } from "node:child_process";
import { createReadStream } from "node:fs";
import { access, mkdir, readdir, readFile, stat } from "node:fs/promises";
import { homedir, tmpdir } from "node:os";
import { basename, dirname, extname, join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import readline from "node:readline";

const defaultPageSize = 20;
const defaultWindowMinutes = 30;
const defaultWatchIntervalMs = 1000;

if (isMainModule()) {
  main(process.argv.slice(2)).catch((error) => {
    process.stderr.write(`${error.message}\n`);
    process.exitCode = 1;
  });
}

export async function main(argv) {
  const { command, options, positionals } = parseArgs(argv);

  if (options.help || command === "help" || !command) {
    printUsage();
    return;
  }

  if (command === "fetch") {
    await runFetch(options);
    return;
  }

  if (command === "analyze") {
    await runAnalyze(positionals[0] ?? options.path, options);
    return;
  }

  throw new Error(`Unknown command: ${command}`);
}

async function runFetch(options) {
  options = await applyConfiguredDefaults(options);
  const outputDir = resolve(options.outputDir ?? join(tmpdir(), "tutti-lark"));
  await mkdir(outputDir, { recursive: true });

  const directFile = directFileSelection(options);
  const recordFile =
    directFile == null && hasRecordSelectionOptions(options)
      ? await findRecordFileSelection(options)
      : null;
  const selection =
    directFile ?? recordFile ?? (await findMessageFileSelection(options));
  const outputName = sanitizeOutputName(options.output ?? selection.file.name);

  log(
    `downloading ${selection.file.name} from ${selection.messageId} to ${join(outputDir, outputName)}`
  );
  const downloaded =
    selection.resourceType === "baseMedia"
      ? downloadDocumentMedia({
          fileToken: selection.file.key,
          outputPath: join(outputDir, outputName)
        })
      : downloadMessageResource({
          cwd: outputDir,
          fileKey: selection.file.key,
          messageId: selection.messageId,
          outputName
        });

  log(`saved ${downloaded.savedPath}`);
  if (downloaded.sizeBytes != null) {
    log(`size ${formatBytes(downloaded.sizeBytes)}`);
  }

  let analysisPath = downloaded.savedPath;
  if (options.extract || options.analyze || options.watch) {
    analysisPath = await ensureExtracted(
      downloaded.savedPath,
      options.extractDir
    );
    log(`extracted ${analysisPath}`);
  }

  if (options.analyze || options.watch) {
    await analyzeAndMaybeWatch(analysisPath, {
      ...options,
      anchor: options.anchor ?? selection.createTime
    });
  }
}

async function applyConfiguredDefaults(options) {
  if (!hasRecordSelectionOptions(options)) {
    return options;
  }
  const config = await loadFetcherConfig(options.config);
  return applyBugRecordDefaults(options, config);
}

export function applyBugRecordDefaults(options, config) {
  const bugRecord =
    config?.bugRecord ?? config?.defaultBugRecord ?? config?.record ?? config;
  if (!bugRecord || typeof bugRecord !== "object") {
    return options;
  }
  const merged = {
    ...options,
    attachmentField: options.attachmentField ?? bugRecord.attachmentField,
    attachmentIndex: options.attachmentIndex ?? bugRecord.attachmentIndex,
    baseUrl: options.baseUrl ?? bugRecord.baseUrl ?? bugRecord.base_url,
    baseToken: options.baseToken ?? bugRecord.baseToken ?? bugRecord.base_token,
    recordTimeField:
      options.recordTimeField ??
      options.recordAnchorField ??
      bugRecord.recordTimeField ??
      bugRecord.recordAnchorField,
    tableId: options.tableId ?? bugRecord.tableId ?? bugRecord.table_id,
    viewId: options.viewId ?? bugRecord.viewId ?? bugRecord.view_id
  };
  for (const key of Object.keys(merged)) {
    if (merged[key] === undefined) {
      delete merged[key];
    }
  }
  return merged;
}

async function loadFetcherConfig(explicitPath) {
  const paths = explicitPath
    ? [resolve(explicitPath)]
    : [
        resolve(process.cwd(), ".tutti-logger-fetcher.json"),
        join(homedir(), ".config", "tutti-logger-fetcher", "config.json"),
        join(
          homedir(),
          ".codex",
          "skills",
          "tutti-logger-fetcher",
          "config.json"
        )
      ];
  for (const path of paths) {
    const config = await readOptionalJSON(path);
    if (config) {
      log(`loaded config ${path}`);
      return config;
    }
  }
  return {};
}

async function runAnalyze(path, options) {
  if (!path) {
    throw new Error("analyze requires a zip file or extracted log directory");
  }
  await analyzeAndMaybeWatch(path, options);
}

async function analyzeAndMaybeWatch(inputPath, options) {
  const analysisPath = await ensureAnalysisDirectory(
    inputPath,
    options.extractDir
  );
  const report = await analyzeLogBundle(analysisPath, options);
  printAnalysisReport(report);

  if (options.watch) {
    const logsDir = report.logsDir;
    if (!logsDir) {
      throw new Error("watch mode requires a bundle with a logs directory");
    }
    await watchLogs(logsDir, {
      intervalMs: numberOption(options.intervalMs, defaultWatchIntervalMs)
    });
  }
}

function directFileSelection(options) {
  if (!options.messageId && !options.fileKey) {
    return null;
  }

  if (!options.messageId || !options.fileKey) {
    throw new Error("--message-id and --file-key must be provided together");
  }

  return {
    chatName: "",
    createTime: "",
    file: {
      key: options.fileKey,
      name: options.output ?? options.fileKey
    },
    messageId: options.messageId,
    resourceType: "messageResource",
    senderName: ""
  };
}

function hasRecordSelectionOptions(options) {
  return (
    options.recordUrl ||
    options.recordId ||
    options.baseToken ||
    options.tableId
  );
}

async function findRecordFileSelection(options) {
  const linkParts = parseFeishuRecordLink(options.recordUrl);
  const baseParts = parseFeishuBaseLink(options.baseUrl);
  const baseToken =
    options.baseToken ?? baseParts.baseToken ?? linkParts.baseToken;
  const tableId = options.tableId ?? baseParts.tableId ?? linkParts.tableId;
  const viewId = options.viewId ?? baseParts.viewId;
  let recordId = options.recordId ?? linkParts.recordId;

  if (!recordId) {
    throw new Error("Base record fetch requires --record-id or --record-url");
  }
  if (!baseToken || !tableId) {
    throw new Error(
      "Base record fetch requires --base-token and --table-id. The short /record/<id> link only exposes the record id."
    );
  }
  if (!isOpenAPIRecordId(recordId) && options.recordUrl) {
    recordId = resolveRecordShareToken({
      baseToken,
      recordUrl: options.recordUrl,
      recordToken: recordId,
      tableId,
      viewId
    });
    log(`resolved record share link to ${recordId}`);
  }

  const record = fetchBaseRecord({ baseToken, recordId, tableId });
  const fields = record.fields ?? {};
  const attachment = selectRecordAttachment(fields, {
    fieldName: options.attachmentField,
    index: numberOption(options.attachmentIndex, 0)
  });

  if (attachment) {
    const anchor = selectRecordAnchor(record, fields, options);
    log(
      `selected Base attachment ${attachment.name} from record ${recordId}${attachment.fieldName ? ` field ${attachment.fieldName}` : ""}`
    );
    return {
      chatName: "",
      createTime: anchor,
      file: {
        key: attachment.token,
        name: attachment.name
      },
      messageId: `base:${baseToken}/${tableId}/${recordId}`,
      record,
      resourceType: "baseMedia",
      senderName: record.created_by?.name ?? ""
    };
  }

  const linkedLog = selectRecordURL(fields, options.attachmentField);
  if (linkedLog) {
    log(
      `record has no attachment field match; using URL from field ${linkedLog.fieldName}`
    );
    return findMessageFileSelection({ ...options, url: linkedLog.url });
  }

  throw new Error(
    "No downloadable log attachment or Feishu log URL found in the Base record"
  );
}

function fetchBaseRecord({ baseToken, recordId, tableId }) {
  const args = [
    "base",
    "+record-get",
    "--as",
    "user",
    "--base-token",
    baseToken,
    "--table-id",
    tableId,
    "--format",
    "json",
    "--record-id",
    recordId
  ];
  const result = runCommand("lark-cli", args, { cwd: process.cwd() });
  const payload = parseCommandJSON(result.stdout, "lark-cli base record get");
  if (payload.ok === false) {
    throw new Error(
      `lark-cli base record get failed: ${payload.error?.message ?? result.stdout}`
    );
  }
  const data = payload.data ?? payload;
  return normalizeBaseRecord(data.record ?? data.item ?? data);
}

function normalizeBaseRecord(record) {
  if (Array.isArray(record?.fields) && Array.isArray(record?.data?.[0])) {
    return {
      fields: Object.fromEntries(
        record.fields.map((name, index) => [name, record.data[0][index]])
      ),
      record_id: record.record_id_list?.[0] ?? ""
    };
  }
  return record;
}

async function findMessageFileSelection(options) {
  const query = options.query ?? "";
  const pageSize = String(numberOption(options.pageSize, defaultPageSize));
  const args = [
    "im",
    "+messages-search",
    "--as",
    "user",
    "--query",
    query,
    "--include-attachment-type",
    "file",
    "--page-size",
    pageSize,
    "--format",
    "json"
  ];

  if (options.chatId) {
    args.push("--chat-id", options.chatId);
  }
  if (options.sender) {
    args.push("--sender", options.sender);
  }
  if (options.start) {
    args.push("--start", options.start);
  }
  if (options.end) {
    args.push("--end", options.end);
  }
  if (options.pageLimit) {
    args.push("--page-limit", String(numberOption(options.pageLimit, 1)));
  }

  if (options.url) {
    const resolved = await tryResolveApplinkLongLink(options.url);
    if (resolved && resolved !== options.url) {
      log(`resolved applink to ${resolved}`);
    } else {
      log(
        "applink did not resolve directly; falling back to visible file messages"
      );
    }
  }

  const result = runCommand("lark-cli", args, { cwd: process.cwd() });
  const payload = parseCommandJSON(result.stdout, "lark-cli message search");
  if (!payload.ok) {
    throw new Error(
      `lark-cli message search failed: ${payload.error?.message ?? result.stdout}`
    );
  }

  const candidates = (payload.data?.messages ?? [])
    .map((message) => messageToFileCandidate(message))
    .filter(Boolean)
    .sort(compareCandidatesNewestFirst);

  if (candidates.length === 0) {
    throw new Error("No visible file messages found");
  }

  const candidateIndex = numberOption(options.candidateIndex, 0);
  if (candidateIndex < 0 || candidateIndex >= candidates.length) {
    throw new Error(
      `--candidate-index ${candidateIndex} is out of range; found ${candidates.length} candidates`
    );
  }

  printCandidates(candidates.slice(0, 10));
  const selected = candidates[candidateIndex];
  log(
    `selected #${candidateIndex}: ${selected.file.name} (${selected.createTime}, ${selected.senderName || "unknown sender"})`
  );
  return selected;
}

function downloadMessageResource({ cwd, fileKey, messageId, outputName }) {
  const result = runCommand(
    "lark-cli",
    [
      "im",
      "+messages-resources-download",
      "--as",
      "user",
      "--message-id",
      messageId,
      "--file-key",
      fileKey,
      "--type",
      "file",
      "--output",
      outputName
    ],
    { cwd }
  );
  const payload = parseCommandJSON(result.stdout, "lark-cli resource download");
  if (!payload.ok) {
    throw new Error(
      `lark-cli resource download failed: ${payload.error?.message ?? result.stdout}`
    );
  }

  return {
    savedPath: payload.data?.saved_path ?? join(cwd, outputName),
    sizeBytes: payload.data?.size_bytes
  };
}

function downloadDocumentMedia({ fileToken, outputPath }) {
  const result = runCommand(
    "lark-cli",
    [
      "docs",
      "+media-download",
      "--as",
      "user",
      "--token",
      fileToken,
      "--output",
      basename(outputPath),
      "--overwrite"
    ],
    { cwd: dirname(outputPath) }
  );
  const payload = parseOptionalCommandJSON(result.stdout);
  return {
    savedPath:
      payload?.data?.saved_path ??
      payload?.data?.path ??
      payload?.saved_path ??
      outputPath,
    sizeBytes: payload?.data?.size_bytes
  };
}

async function tryResolveApplinkLongLink(input) {
  const url = new URL(
    `https://open.feishu.cn/open-apis/applink/longlink/v1/get?shortLink=${encodeURIComponent(
      input
    )}&businessTag=applink`
  );

  try {
    const response = await fetch(url);
    if (!response.ok) {
      return null;
    }
    const payload = await response.json();
    return payload?.data?.link || null;
  } catch {
    return null;
  }
}

export function messageToFileCandidate(message) {
  const file = parseMessageFileContent(message.content ?? "");
  if (!file) {
    return null;
  }

  return {
    chatName: message.chat_name ?? message.chat_type ?? "",
    createTime: message.create_time ?? "",
    file,
    messageId: message.message_id,
    resourceType: "messageResource",
    senderName: message.sender?.name ?? message.sender?.id ?? ""
  };
}

export function parseFeishuRecordLink(input) {
  if (!input) {
    return {};
  }

  let url;
  try {
    url = new URL(input);
  } catch {
    return {};
  }

  const pathParts = url.pathname.split("/").filter(Boolean);
  const query = url.searchParams;
  const result = {
    baseToken:
      query.get("base_token") ??
      query.get("baseToken") ??
      query.get("app_token") ??
      query.get("appToken") ??
      query.get("base") ??
      "",
    recordId:
      query.get("record_id") ??
      query.get("recordId") ??
      query.get("record") ??
      "",
    tableId:
      query.get("table_id") ?? query.get("tableId") ?? query.get("table") ?? ""
  };

  const recordIndex = pathParts.findIndex((part) => part === "record");
  if (!result.recordId && recordIndex !== -1) {
    result.recordId = pathParts[recordIndex + 1] ?? "";
  }

  const baseIndex = pathParts.findIndex((part) =>
    ["base", "bitable"].includes(part)
  );
  if (!result.baseToken && baseIndex !== -1) {
    result.baseToken = pathParts[baseIndex + 1] ?? "";
  }

  const tableIndex = pathParts.findIndex((part) => part === "table");
  if (!result.tableId && tableIndex !== -1) {
    result.tableId = pathParts[tableIndex + 1] ?? "";
  }

  return result;
}

export function parseFeishuBaseLink(input) {
  if (!input) {
    return {};
  }

  let url;
  try {
    url = new URL(input);
  } catch {
    return {};
  }

  const pathParts = url.pathname.split("/").filter(Boolean);
  const baseIndex = pathParts.findIndex((part) =>
    ["base", "bitable"].includes(part)
  );
  return {
    baseToken:
      url.searchParams.get("base_token") ??
      url.searchParams.get("baseToken") ??
      (baseIndex !== -1 ? (pathParts[baseIndex + 1] ?? "") : ""),
    tableId:
      url.searchParams.get("table") ??
      url.searchParams.get("table_id") ??
      url.searchParams.get("tableId") ??
      "",
    viewId:
      url.searchParams.get("view") ??
      url.searchParams.get("view_id") ??
      url.searchParams.get("viewId") ??
      ""
  };
}

function resolveRecordShareToken({
  baseToken,
  recordToken,
  recordUrl,
  tableId,
  viewId
}) {
  const candidates = listBaseRecordIds({ baseToken, tableId, viewId });
  for (let index = 0; index < candidates.length; index += 100) {
    const chunk = candidates.slice(index, index + 100);
    const links = createRecordShareLinks({
      baseToken,
      recordIds: chunk,
      tableId
    });
    for (const [recordId, link] of Object.entries(links)) {
      if (String(link) === recordUrl || String(link).includes(recordToken)) {
        return recordId;
      }
    }
  }
  throw new Error(`Could not resolve record share token ${recordToken}`);
}

function listBaseRecordIds({ baseToken, tableId, viewId }) {
  const ids = [];
  let offset = 0;
  const limit = 200;
  while (true) {
    const args = [
      "base",
      "+record-list",
      "--as",
      "user",
      "--base-token",
      baseToken,
      "--table-id",
      tableId,
      "--format",
      "json",
      "--limit",
      String(limit),
      "--offset",
      String(offset)
    ];
    if (viewId) {
      args.push("--view-id", viewId);
    }
    const payload = parseCommandJSON(
      runCommand("lark-cli", args, { cwd: process.cwd() }).stdout,
      "lark-cli base record list"
    );
    const recordIds = payload.data?.record_id_list ?? [];
    ids.push(...recordIds);
    if (!payload.data?.has_more) {
      return ids;
    }
    offset += recordIds.length || limit;
    if (offset > 5000) {
      throw new Error("Too many records while resolving share link");
    }
  }
}

function createRecordShareLinks({ baseToken, recordIds, tableId }) {
  const path = `/open-apis/base/v3/bases/${baseToken}/tables/${tableId}/records/share_links/batch`;
  const payload = parseCommandJSON(
    runCommand(
      "lark-cli",
      [
        "api",
        "POST",
        path,
        "--as",
        "user",
        "--data",
        JSON.stringify({ record_ids: recordIds })
      ],
      { cwd: process.cwd() }
    ).stdout,
    "lark-cli base record share link batch"
  );
  if (payload.ok === false) {
    throw new Error(
      `record share link batch failed: ${payload.error?.message ?? "unknown error"}`
    );
  }
  return payload.data?.record_share_links ?? payload.record_share_links ?? {};
}

function isOpenAPIRecordId(value) {
  return /^rec[A-Za-z0-9]{1,32}$/.test(String(value ?? ""));
}

export function selectRecordAttachment(fields, { fieldName, index = 0 } = {}) {
  const attachments = collectRecordAttachments(fields, fieldName);
  if (attachments.length === 0) {
    return null;
  }
  const sorted = attachments.sort(compareRecordAttachments);
  return sorted[index] ?? null;
}

function collectRecordAttachments(fields, fieldName) {
  const attachments = [];
  for (const [name, value] of Object.entries(fields ?? {})) {
    if (fieldName && name !== fieldName) {
      continue;
    }
    collectAttachmentValues(value, name, attachments);
  }
  return attachments;
}

function collectAttachmentValues(value, fieldName, attachments) {
  if (Array.isArray(value)) {
    for (const item of value) {
      collectAttachmentValues(item, fieldName, attachments);
    }
    return;
  }
  if (!value || typeof value !== "object") {
    return;
  }

  const token =
    value.file_token ??
    value.fileToken ??
    value.token ??
    value.tmp_url_token ??
    value.tmpUrlToken;
  const name =
    value.name ??
    value.file_name ??
    value.fileName ??
    value.title ??
    value.mime_type ??
    "record-attachment";

  if (token && looksLikeLogAttachmentName(name)) {
    attachments.push({ fieldName, name, token });
  }

  for (const nested of Object.values(value)) {
    if (nested && typeof nested === "object") {
      collectAttachmentValues(nested, fieldName, attachments);
    }
  }
}

function compareRecordAttachments(left, right) {
  return recordAttachmentScore(right) - recordAttachmentScore(left);
}

function recordAttachmentScore(attachment) {
  const name = attachment.name.toLowerCase();
  if (name.endsWith(".zip")) return 100;
  if (name.includes("tutti") && name.includes("log")) return 80;
  if (name.includes("diagnostic")) return 60;
  if (name.includes("log")) return 40;
  return 0;
}

function looksLikeLogAttachmentName(name) {
  const lower = String(name).toLowerCase();
  return (
    lower.endsWith(".zip") ||
    lower.includes("tutti") ||
    lower.includes("log") ||
    lower.includes("diagnostic")
  );
}

function selectRecordURL(fields, fieldName) {
  for (const [name, value] of Object.entries(fields ?? {})) {
    if (fieldName && name !== fieldName) {
      continue;
    }
    const url = findFirstURL(value);
    if (url) {
      return { fieldName: name, url };
    }
  }
  return null;
}

function findFirstURL(value) {
  if (typeof value === "string") {
    const match = value.match(/https?:\/\/[^\s"'<>]+/);
    return match?.[0] ?? null;
  }
  if (Array.isArray(value)) {
    for (const item of value) {
      const url = findFirstURL(item);
      if (url) return url;
    }
    return null;
  }
  if (!value || typeof value !== "object") {
    return null;
  }
  for (const key of ["url", "link", "href", "text"]) {
    const url = findFirstURL(value[key]);
    if (url) return url;
  }
  for (const nested of Object.values(value)) {
    const url = findFirstURL(nested);
    if (url) return url;
  }
  return null;
}

function selectRecordAnchor(record, fields, options) {
  if (options.anchor) {
    return options.anchor;
  }
  const preferredField = options.recordTimeField ?? options.recordAnchorField;
  if (preferredField && fields?.[preferredField] != null) {
    return normalizeRecordTime(fields[preferredField]);
  }

  for (const [name, value] of Object.entries(fields ?? {})) {
    if (
      /发送|创建|提交|反馈|发生|时间|time|date|created|reported/i.test(name)
    ) {
      const time = normalizeRecordTime(value);
      if (time) return time;
    }
  }

  return (
    normalizeRecordTime(record.created_time) ??
    normalizeRecordTime(record.createdTime) ??
    normalizeRecordTime(record.record_id) ??
    ""
  );
}

function normalizeRecordTime(value) {
  if (value == null) {
    return "";
  }
  if (Array.isArray(value)) {
    for (const item of value) {
      const normalized = normalizeRecordTime(item);
      if (normalized) return normalized;
    }
    return "";
  }
  if (typeof value === "object") {
    return normalizeRecordTime(
      value.timestamp ??
        value.time ??
        value.text ??
        value.value ??
        value.created_time ??
        value.createdTime
    );
  }
  if (typeof value === "number") {
    const millis = value < 10_000_000_000 ? value * 1000 : value;
    return new Date(millis).toISOString();
  }
  const text = String(value).trim();
  return parseCandidateTime(text) ? text : "";
}

export function parseMessageFileContent(content) {
  const match = content.match(/<file\s+([^>]+?)\/?\s*>/i);
  if (!match) {
    return null;
  }

  const attributes = {};
  for (const attribute of match[1].matchAll(/([A-Za-z0-9_-]+)="([^"]*)"/g)) {
    attributes[attribute[1]] = decodeXml(attribute[2]);
  }

  if (!attributes.key || !attributes.name) {
    return null;
  }

  return {
    key: attributes.key,
    name: attributes.name
  };
}

async function analyzeLogBundle(bundlePath, options = {}) {
  const directory = await ensureAnalysisDirectory(bundlePath);
  const exportSummary = await readOptionalJSON(
    join(directory, "export-summary.json")
  );
  const runtimeContext = await readOptionalJSON(
    join(directory, "runtime-context.json")
  );
  const logsDir = (await exists(join(directory, "logs")))
    ? join(directory, "logs")
    : directory;
  const logFiles = await listLogFiles(logsDir);
  const anchor = options.anchor ?? exportSummary?.exportedAt ?? "";
  const windowMinutes = numberOption(
    options.windowMinutes,
    defaultWindowMinutes
  );
  const windowRange = buildWindow(anchor, windowMinutes);
  const issueTerms = issueTermsFrom(options.issue);
  const logSummary = await summarizeLogFiles(logFiles, {
    issueTerms,
    windowRange
  });

  return {
    anchor,
    bundlePath: directory,
    exportSummary,
    issueTerms,
    logFiles,
    logSummary,
    logsDir,
    runtimeContext,
    windowMinutes
  };
}

async function ensureAnalysisDirectory(inputPath, extractDir) {
  const resolved = resolve(inputPath);
  const inputStat = await stat(resolved);
  if (inputStat.isDirectory()) {
    return resolved;
  }
  if (extname(resolved).toLowerCase() !== ".zip") {
    throw new Error(`Expected a .zip file or directory: ${resolved}`);
  }
  return ensureExtracted(resolved, extractDir);
}

async function ensureExtracted(zipPath, extractDir) {
  const outputDir =
    extractDir != null
      ? resolve(extractDir)
      : join(dirname(zipPath), basename(zipPath, extname(zipPath)));
  await mkdir(outputDir, { recursive: true });
  runCommand("unzip", ["-oq", zipPath, "-d", outputDir], {
    cwd: process.cwd()
  });
  return outputDir;
}

async function summarizeLogFiles(logFiles, options = {}) {
  const summary = createEmptyLogSummary();
  const windowSummary = createEmptyLogSummary();
  for (const logFile of logFiles) {
    await summarizeLogFile(logFile, summary, windowSummary, options);
  }
  finalizeLogSummary(summary);
  finalizeLogSummary(windowSummary);
  return { all: summary, windowed: windowSummary };
}

async function summarizeLogFile(logFile, summary, windowSummary, options = {}) {
  const rl = readline.createInterface({
    crlfDelay: Infinity,
    input: createReadStream(logFile, "utf8")
  });

  for await (const line of rl) {
    const event = parseLogLine(line);
    if (!event) {
      continue;
    }
    addLogEvent(summary, event, line, options.issueTerms);
    if (
      !options.windowRange ||
      isLogEventInWindow(event, options.windowRange)
    ) {
      addLogEvent(windowSummary, event, line, options.issueTerms);
    }
  }
}

export function summarizeLogLines(lines) {
  const summary = createEmptyLogSummary();
  for (const line of lines) {
    const event = parseLogLine(line);
    if (event) {
      addLogEvent(summary, event, line);
    }
  }
  finalizeLogSummary(summary);
  return summary;
}

function finalizeLogSummary(summary) {
  summary.topMessages = topEntries(summary.messageCounts, 12);
  summary.topDetailErrors = topEntries(summary.detailErrorCounts, 12);
}

function createEmptyLogSummary() {
  return {
    detailErrorCounts: new Map(),
    issueMatches: [],
    latestImportant: [],
    levels: new Map(),
    messageCounts: new Map(),
    topDetailErrors: [],
    topMessages: [],
    totalLines: 0
  };
}

function addLogEvent(summary, event, rawLine, issueTerms = []) {
  summary.totalLines += 1;
  incrementMap(summary.levels, event.level);
  if (event.message) {
    incrementMap(summary.messageCounts, event.message);
  }
  if (event.detailError) {
    incrementMap(summary.detailErrorCounts, event.detailError);
  }
  if (isImportantLevel(event.level)) {
    summary.latestImportant.push({ ...event, rawLine });
    if (summary.latestImportant.length > 20) {
      summary.latestImportant.shift();
    }
  }
  if (matchesIssueTerms(event, rawLine, issueTerms)) {
    summary.issueMatches.push({ ...event, rawLine });
    if (summary.issueMatches.length > 20) {
      summary.issueMatches.shift();
    }
  }
}

export function parseLogLine(line) {
  const level = extractTokenValue(line, "level");
  if (!level) {
    return null;
  }

  return {
    component: extractTokenValue(line, "component") ?? "",
    detailError: extractJSONField(line, "details", "error"),
    level: level.toLowerCase(),
    message: extractTokenValue(line, "msg") ?? "",
    rendererMessage: extractJSONField(line, "renderer_details", "message"),
    stderrMessage: extractTokenValue(line, "message"),
    time: extractTokenValue(line, "time") ?? ""
  };
}

function extractTokenValue(line, key) {
  const match = line.match(new RegExp(`(?:^|\\s)${escapeRegExp(key)}=`));
  if (!match) {
    return null;
  }

  const valueStart = match.index + match[0].length;
  if (line[valueStart] === '"') {
    return readQuotedTokenValue(line, valueStart);
  }

  const valueEnd = line.indexOf(" ", valueStart);
  return line.slice(valueStart, valueEnd === -1 ? undefined : valueEnd);
}

function readQuotedTokenValue(line, quoteStart) {
  let value = "";
  let escaped = false;

  for (let index = quoteStart + 1; index < line.length; index += 1) {
    const char = line[index];
    if (escaped) {
      value += decodeEscapedTokenChar(char);
      escaped = false;
    } else if (char === "\\") {
      escaped = true;
    } else if (char === '"') {
      return value;
    } else {
      value += char;
    }
  }

  return value;
}

function decodeEscapedTokenChar(char) {
  if (char === "n") {
    return "\n";
  }
  if (char === "t") {
    return "\t";
  }
  return char;
}

function extractJSONField(line, objectKey, fieldKey) {
  const start = line.indexOf(`${objectKey}=`);
  if (start === -1) {
    return null;
  }

  const jsonStart = line.indexOf("{", start);
  if (jsonStart === -1) {
    return null;
  }

  const jsonText = readBalancedJSON(line.slice(jsonStart));
  if (!jsonText) {
    return null;
  }

  try {
    const payload = JSON.parse(jsonText);
    return payload?.[fieldKey] ?? null;
  } catch {
    return null;
  }
}

function readBalancedJSON(text) {
  let depth = 0;
  let inString = false;
  let escaped = false;

  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    if (inString) {
      if (escaped) {
        escaped = false;
      } else if (char === "\\") {
        escaped = true;
      } else if (char === '"') {
        inString = false;
      }
      continue;
    }

    if (char === '"') {
      inString = true;
    } else if (char === "{") {
      depth += 1;
    } else if (char === "}") {
      depth -= 1;
      if (depth === 0) {
        return text.slice(0, index + 1);
      }
    }
  }

  return null;
}

async function watchLogs(logsDir, { intervalMs }) {
  log(`watching ${logsDir}; press Ctrl+C to stop`);
  const offsets = new Map();
  const buffers = new Map();

  for (const file of await listLogFiles(logsDir)) {
    const fileStat = await stat(file);
    offsets.set(file, fileStat.size);
    buffers.set(file, "");
  }

  const timer = setInterval(async () => {
    try {
      for (const file of await listLogFiles(logsDir)) {
        await readAppendedLogLines(file, offsets, buffers);
      }
    } catch (error) {
      process.stderr.write(`[lark-logs] watch error: ${error.message}\n`);
    }
  }, intervalMs);

  process.on("SIGINT", () => {
    clearInterval(timer);
    process.stdout.write("\n[lark-logs] stopped\n");
    process.exit(0);
  });

  await new Promise(() => {});
}

async function readAppendedLogLines(file, offsets, buffers) {
  const fileStat = await stat(file);
  const previousOffset = offsets.get(file) ?? 0;
  if (fileStat.size < previousOffset) {
    offsets.set(file, 0);
    buffers.set(file, "");
    return;
  }
  if (fileStat.size === previousOffset) {
    return;
  }

  const handle = await readFileRange(file, previousOffset, fileStat.size);
  offsets.set(file, fileStat.size);
  const buffered = `${buffers.get(file) ?? ""}${handle}`;
  const lines = buffered.split(/\r?\n/);
  buffers.set(file, lines.pop() ?? "");

  for (const line of lines) {
    const event = parseLogLine(line);
    if (event && isImportantLevel(event.level)) {
      printRealtimeEvent(file, event);
    }
  }
}

async function readFileRange(file, start, end) {
  const stream = createReadStream(file, {
    encoding: "utf8",
    end: end - 1,
    start
  });
  let content = "";
  for await (const chunk of stream) {
    content += chunk;
  }
  return content;
}

function printRealtimeEvent(file, event) {
  const detail = compactDetail(
    event.rendererMessage ?? event.detailError ?? event.stderrMessage ?? ""
  );
  const suffix = detail ? ` | ${detail}` : "";
  process.stdout.write(
    `[${event.time || "no-time"}] ${event.level.toUpperCase()} ${basename(file)} ${event.message}${suffix}\n`
  );
}

function printAnalysisReport(report) {
  const { exportSummary, issueTerms, logFiles, logSummary, runtimeContext } =
    report;
  console.log(`Bundle: ${report.bundlePath}`);
  if (exportSummary) {
    console.log(
      `Exported: ${exportSummary.exportedAt ?? "unknown"} | desktop ${exportSummary.desktopVersion ?? "unknown"} | ${formatBytes(
        exportSummary.totalSizeBytes ?? 0
      )}`
    );
  }
  if (runtimeContext?.runtime) {
    console.log(
      `Runtime: ${runtimeContext.runtime.platform ?? "unknown"} | Electron ${runtimeContext.runtime.electron ?? "unknown"} | Node ${runtimeContext.runtime.node ?? "unknown"} | env ${runtimeContext.runtime.tuttiEnv ?? "unknown"}`
    );
  }
  if (runtimeContext?.defaults?.state?.rootDir) {
    console.log(`State: ${runtimeContext.defaults.state.rootDir}`);
  }
  console.log(`Logs: ${logFiles.length} files`);
  console.log(
    `Anchor: ${report.anchor || "unknown"} | window: +/- ${report.windowMinutes} minutes`
  );

  printLogSummary("Window summary", logSummary.windowed);
  console.log("");
  printLogSummary("Whole bundle summary", logSummary.all);

  const issueMatches = logSummary.windowed.issueMatches.length
    ? logSummary.windowed.issueMatches
    : logSummary.all.issueMatches;
  if (issueTerms.length > 0 && issueMatches.length > 0) {
    console.log("Issue matches:");
    for (const event of issueMatches.slice(-8)) {
      const detail = compactDetail(
        event.rendererMessage ?? event.detailError ?? event.stderrMessage ?? ""
      );
      const suffix = detail ? ` | ${detail}` : "";
      console.log(
        `- ${event.time || "no-time"} ${event.level.toUpperCase()} ${event.component} ${event.message}${suffix}`
      );
    }
  }
}

function printLogSummary(title, logSummary) {
  console.log(
    `${title}: lines=${logSummary.totalLines} levels=${formatMap(logSummary.levels, ["error", "warn", "info", "debug"])}`
  );

  printTopEntries("Top messages", logSummary.topMessages);
  printTopEntries("Top detail errors", logSummary.topDetailErrors);

  if (logSummary.latestImportant.length > 0) {
    console.log("Recent important events:");
    for (const event of logSummary.latestImportant.slice(-8)) {
      const detail = compactDetail(
        event.rendererMessage ?? event.detailError ?? event.stderrMessage ?? ""
      );
      const suffix = detail ? ` | ${detail}` : "";
      console.log(
        `- ${event.time || "no-time"} ${event.level.toUpperCase()} ${event.component} ${event.message}${suffix}`
      );
    }
  }
}

function compactDetail(value, limit = 360) {
  const compacted = String(value)
    .replaceAll(/\s*\n\s*/g, " | ")
    .replaceAll(/\s+/g, " ")
    .trim();
  if (compacted.length <= limit) {
    return compacted;
  }
  return `${compacted.slice(0, limit - 3)}...`;
}

function printTopEntries(title, entries) {
  if (entries.length === 0) {
    return;
  }
  console.log(`${title}:`);
  for (const [value, count] of entries) {
    console.log(`- ${count} ${value}`);
  }
}

function printCandidates(candidates) {
  console.log("Candidates:");
  candidates.forEach((candidate, index) => {
    console.log(
      `- #${index} ${candidate.createTime || "unknown-time"} ${candidate.senderName || "unknown"} ${candidate.file.name} ${candidate.messageId}`
    );
  });
}

async function listLogFiles(logsDir) {
  const entries = await readdir(logsDir, { withFileTypes: true });
  return entries
    .filter((entry) => entry.isFile() && entry.name.endsWith(".log"))
    .map((entry) => join(logsDir, entry.name))
    .sort();
}

async function readOptionalJSON(path) {
  try {
    return JSON.parse(await readFile(path, "utf8"));
  } catch {
    return null;
  }
}

async function exists(path) {
  try {
    await access(path);
    return true;
  } catch {
    return false;
  }
}

function runCommand(command, args, options) {
  const result = spawnSync(command, args, {
    cwd: options.cwd,
    encoding: "utf8",
    env: process.env,
    maxBuffer: 64 * 1024 * 1024
  });

  if (result.error) {
    throw result.error;
  }
  if (result.status !== 0) {
    throw new Error(
      `${command} ${args.join(" ")} failed with exit code ${result.status}: ${result.stderr || result.stdout}`
    );
  }
  return result;
}

function parseCommandJSON(output, label) {
  try {
    return JSON.parse(output);
  } catch (error) {
    throw new Error(`${label} returned non-JSON output: ${error.message}`, {
      cause: error
    });
  }
}

function parseOptionalCommandJSON(output) {
  try {
    return JSON.parse(output);
  } catch {
    return null;
  }
}

function parseArgs(argv) {
  if (argv[0] === "--") {
    argv = argv.slice(1);
  }

  const [command, ...rest] = argv;
  const options = {};
  const positionals = [];

  for (let index = 0; index < rest.length; index += 1) {
    const arg = rest[index];
    if (!arg.startsWith("--")) {
      positionals.push(arg);
      continue;
    }

    const raw = arg.slice(2);
    const equalsIndex = raw.indexOf("=");
    const key = toCamelCase(
      equalsIndex === -1 ? raw : raw.slice(0, equalsIndex)
    );
    if (equalsIndex !== -1) {
      options[key] = raw.slice(equalsIndex + 1);
      continue;
    }

    const next = rest[index + 1];
    if (!next || next.startsWith("--")) {
      options[key] = true;
      continue;
    }

    options[key] = next;
    index += 1;
  }

  return { command, options, positionals };
}

function printUsage() {
  console.log(`Usage:
  pnpm lark:logs -- fetch --url <feishu-applink> [--analyze] [--watch]
  pnpm lark:logs -- fetch --record-url <feishu-record-url> [--analyze]
  pnpm lark:logs -- fetch --base-url <feishu-base-url> --record-url <feishu-record-url> [--analyze]
  pnpm lark:logs -- fetch --record-url <feishu-record-url> --base-token <base> --table-id <table> [--analyze]
  pnpm lark:logs -- fetch --base-token <base> --table-id <table> --record-id <rec> [--analyze]
  pnpm lark:logs -- fetch --message-id <om_xxx> --file-key <file_xxx> [--output-dir <dir>]
  pnpm lark:logs -- analyze <zip-or-extracted-dir> [--watch]

Fetch options:
  --url <url>              Original Feishu applink. Falls back to visible recent file messages when the link token cannot be resolved.
  --record-url <url>       Feishu Base record URL. Short /record/<id> links still need --base-token and --table-id.
  --base-url <url>         Feishu Base URL used to infer base/table/view for a record link.
  --base-token <token>     Base token for fetching a record attachment.
  --table-id <id|name>     Base table id or name for fetching a record attachment.
  --view-id <id>           Optional view id used to narrow share-link matching.
  --record-id <id>         Base record id. Parsed from --record-url when possible.
  --attachment-field <name> Prefer one record field when finding log attachments or URLs.
  --attachment-index <n>   Select a record attachment after zip/log ranking. Default: 0.
  --record-time-field <name> Record field used as analysis anchor.
  --config <path>           Config file for one-click Base bug record defaults.
  --candidate-index <n>    Select a candidate from the recent file list. Default: 0.
  --query <text>           Message search query. Default: empty.
  --chat-id <oc_xxx>       Restrict message search to a chat.
  --sender <ou_xxx>        Restrict message search to a sender.
  --start/--end <time>     Restrict message search to an ISO local time range.
  --page-size <n>          Message search page size. Default: ${defaultPageSize}.
  --page-limit <n>         Ask lark-cli to auto-paginate up to n pages.
  --output-dir <dir>       Download directory. Default: OS temp/tutti-lark.
  --output <name>          Local output file name.
  --extract                Extract zip after download.
  --analyze                Analyze after download.
  --watch                  Analyze, then stream new warn/error log lines.

Analyze options:
  --anchor <time>          Center analysis around this time.
  --issue <text>           Highlight log lines matching the issue terms.
  --window-minutes <n>     Time radius around --anchor. Default: ${defaultWindowMinutes}.
  --extract-dir <dir>      Extraction directory for zip inputs.
  --interval-ms <n>        Watch polling interval. Default: ${defaultWatchIntervalMs}.`);
}

function compareCandidatesNewestFirst(left, right) {
  return (
    parseCandidateTime(right.createTime) - parseCandidateTime(left.createTime)
  );
}

function parseCandidateTime(value) {
  if (!value) {
    return 0;
  }
  return Date.parse(value.replace(" ", "T")) || 0;
}

function buildWindow(anchor, minutes) {
  const center = parseCandidateTime(String(anchor ?? ""));
  if (!center) {
    return null;
  }
  const radius = minutes * 60 * 1000;
  return { end: center + radius, start: center - radius };
}

function isLogEventInWindow(event, windowRange) {
  const parsed = parseCandidateTime(event.time);
  return parsed >= windowRange.start && parsed <= windowRange.end;
}

function issueTermsFrom(issue) {
  return (
    String(issue ?? "")
      .toLowerCase()
      .match(/[\p{L}\p{N}_:-]{2,}/gu) ?? []
  );
}

function matchesIssueTerms(event, rawLine, issueTerms) {
  if (!issueTerms.length) {
    return false;
  }
  const value =
    `${event.message} ${event.rendererMessage ?? ""} ${event.detailError ?? ""} ${event.stderrMessage ?? ""} ${rawLine}`.toLowerCase();
  return issueTerms.some((term) => value.includes(term));
}

function sanitizeOutputName(name) {
  return basename(String(name || "download.bin")).replaceAll("/", "_");
}

function decodeXml(value) {
  return value
    .replaceAll("&quot;", '"')
    .replaceAll("&apos;", "'")
    .replaceAll("&lt;", "<")
    .replaceAll("&gt;", ">")
    .replaceAll("&amp;", "&");
}

function incrementMap(map, key) {
  map.set(key, (map.get(key) ?? 0) + 1);
}

function topEntries(map, limit) {
  return [...map.entries()]
    .sort((left, right) => right[1] - left[1])
    .slice(0, limit);
}

function isImportantLevel(level) {
  return (
    level === "warn" ||
    level === "warning" ||
    level === "error" ||
    level === "fatal"
  );
}

function formatMap(map, keys) {
  return keys.map((key) => `${key}=${map.get(key) ?? 0}`).join(" ");
}

function formatBytes(value) {
  if (!Number.isFinite(value)) {
    return "unknown-size";
  }
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function numberOption(value, fallback) {
  if (value == null || value === true) {
    return fallback;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function toCamelCase(value) {
  return value.replaceAll(/-([a-z])/g, (_, char) => char.toUpperCase());
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function log(message) {
  console.log(`[lark-logs] ${message}`);
}

function isMainModule() {
  return import.meta.url === pathToFileURL(process.argv[1]).href;
}
