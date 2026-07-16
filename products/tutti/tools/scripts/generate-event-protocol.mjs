import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import {
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  writeFileSync
} from "node:fs";
import { dirname, relative, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { format } from "prettier";

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(__dirname, "../..");
const protocolRoot = resolve(repoRoot, "packages/events/protocol");
const protocolSchemasDir = resolve(protocolRoot, "schemas");
const sharedSchemasDir = resolve(protocolSchemasDir, "topics");
const coreSchemasDir = resolve(protocolSchemasDir, "core");
const definitionsDir = resolve(protocolRoot, "definitions");
const tsGeneratedDir = resolve(protocolRoot, "src/generated");
const goOutputPath = resolve(
  repoRoot,
  "services/tuttid/api/events/generated/protocol.gen.go"
);
const prettierConfigPath = resolve(
  repoRoot,
  "packages/configs/prettier/base.mjs"
);
const checkOnly = process.argv.includes("--check");

const { default: prettierConfig } = await import(
  pathToFileURL(prettierConfigPath).href
);

const definitionSchemaPath = resolve(
  coreSchemasDir,
  "event-definition.schema.json"
);
const envelopeSchemaPath = resolve(
  coreSchemasDir,
  "event-envelope.schema.json"
);
const clientFrameSchemaPath = resolve(
  coreSchemasDir,
  "client-frame.schema.json"
);
const serverFrameSchemaPath = resolve(
  coreSchemasDir,
  "server-frame.schema.json"
);

const jsonDocumentCache = new Map();

const definitionSchema = loadJson(definitionSchemaPath);
const sharedSchemas = loadSharedSchemas();
const eventDefinitions = loadEventDefinitions(definitionSchema);
const envelopeSchema = resolveSchemaRefs(
  loadJson(envelopeSchemaPath),
  envelopeSchemaPath
);
const clientFrameSchema = resolveSchemaRefs(
  loadJson(clientFrameSchemaPath),
  clientFrameSchemaPath
);
const serverFrameSchema = resolveSchemaRefs(
  loadJson(serverFrameSchemaPath),
  serverFrameSchemaPath
);

validateSupportedSchema(envelopeSchema, "core event envelope schema");
validateSupportedSchema(clientFrameSchema, "core client frame schema");
validateSupportedSchema(serverFrameSchema, "core server frame schema");

const frameMetadata = buildFrameMetadata(clientFrameSchema, serverFrameSchema);
const scopeNames = readScopeNames(definitionSchema);
const directionNames = readDirectionNames(definitionSchema);
const protocolVersion = readServerProtocolVersion(serverFrameSchema);
const catalogRevision = buildCatalogRevision({
  eventDefinitions,
  frameMetadata,
  protocolVersion,
  sharedSchemas
});

const generatedFiles = new Map();
generatedFiles.set(
  resolve(tsGeneratedDir, "index.ts"),
  await formatTypeScript(renderTSIndex())
);
generatedFiles.set(
  resolve(tsGeneratedDir, "schemas.ts"),
  await formatTypeScript(
    renderTSSchemas({
      clientFrameSchema,
      envelopeSchema,
      eventDefinitions,
      serverFrameSchema,
      sharedSchemas
    })
  )
);
generatedFiles.set(
  resolve(tsGeneratedDir, "contracts.ts"),
  await formatTypeScript(
    renderTSContracts({
      directionNames,
      eventDefinitions,
      frameMetadata,
      protocolVersion,
      scopeNames,
      sharedSchemas
    })
  )
);
generatedFiles.set(
  resolve(tsGeneratedDir, "registry.ts"),
  await formatTypeScript(
    renderTSRegistry({
      catalogRevision,
      eventDefinitions
    })
  )
);
generatedFiles.set(
  resolve(tsGeneratedDir, "validators.ts"),
  await formatTypeScript(renderTSValidators())
);
generatedFiles.set(
  goOutputPath,
  formatGo(
    renderGoProtocol({
      catalogRevision,
      eventDefinitions,
      frameMetadata,
      protocolVersion,
      sharedSchemas
    })
  )
);

for (const [outputPath, source] of generatedFiles) {
  writeGeneratedFile(outputPath, source);
}

function loadSharedSchemas() {
  return collectFiles(sharedSchemasDir, (entry) =>
    entry.endsWith(".schema.json")
  )
    .map((filePath) => {
      const relativePath = relative(sharedSchemasDir, filePath);
      const rawSchema = loadJson(filePath);
      const resolvedSchema = resolveSchemaRefs(rawSchema, filePath);
      validateSupportedSchema(resolvedSchema, `shared schema ${relativePath}`);
      const baseName = relativePath.replace(/\.schema\.json$/, "");

      return {
        filePath,
        goTypeName: toPascalCase(baseName),
        relativePath,
        resolvedSchema,
        schemaConstantName: `${toCamelCase(baseName)}Schema`,
        tsTypeName: `${toPascalCase(baseName)}V1`
      };
    })
    .sort((left, right) => left.relativePath.localeCompare(right.relativePath));
}

function loadEventDefinitions(schema) {
  const topics = new Set();
  const topicVersions = new Set();

  return collectFiles(definitionsDir, (entry) => entry.endsWith(".event.json"))
    .map((filePath) => {
      const relativePath = relative(definitionsDir, filePath);
      const definition = loadJson(filePath);
      const issues = [];
      validateAgainstSchema(definition, schema, "definition", issues);
      if (issues.length > 0) {
        throw new Error(
          `Invalid event definition ${relativePath}: ${formatIssues(issues)}`
        );
      }

      const topic = definition.topic;
      const topicVersionKey = `${definition.topic}@${definition.version}`;
      if (topics.has(topic)) {
        throw new Error(`Duplicate event topic ${topic} in ${relativePath}`);
      }
      if (topicVersions.has(topicVersionKey)) {
        throw new Error(
          `Duplicate event topic/version ${topicVersionKey} in ${relativePath}`
        );
      }
      topics.add(topic);
      topicVersions.add(topicVersionKey);

      const payloadSchema = resolveSchemaRefs(
        definition.payloadSchema,
        filePath
      );
      if (!isPlainObject(payloadSchema) || payloadSchema.type !== "object") {
        throw new Error(
          `Event payload schema must resolve to an object in ${relativePath}`
        );
      }
      validateSupportedSchema(payloadSchema, `payload schema for ${topic}`);

      const baseName = toPascalCase(topic);
      return {
        direction: definition.direction,
        filePath,
        goEventTypeName: `${baseName}Event`,
        goPayloadTypeName: `${baseName}Payload`,
        owner: definition.owner,
        payloadSchema,
        payloadSchemaConstantName: `${toCamelCase(topic)}PayloadSchema`,
        relativePath,
        scope: definition.scope,
        topic,
        topicConstantName: `businessEventTopic${baseName}`,
        tsEventTypeName: `${baseName}EventV1`,
        tsPayloadTypeName: `${baseName}PayloadV1`,
        version: definition.version
      };
    })
    .sort((left, right) => left.topic.localeCompare(right.topic));
}

function buildFrameMetadata(clientSchema, serverSchema) {
  const clientVariants = extractFrameVariants(clientSchema, "client");
  const serverVariants = extractFrameVariants(serverSchema, "server");

  return {
    clientKinds: clientVariants.map((variant) => variant.kind),
    serverKinds: serverVariants.map((variant) => variant.kind)
  };
}

function extractFrameVariants(schema, label) {
  if (!Array.isArray(schema.oneOf) || schema.oneOf.length === 0) {
    throw new Error(`Expected ${label} frame schema to use oneOf`);
  }

  return schema.oneOf.map((variant) => {
    const kind = variant?.properties?.kind?.const;
    if (typeof kind !== "string" || kind.trim() === "") {
      throw new Error(`Expected ${label} frame schema variant to declare kind`);
    }
    return { kind };
  });
}

function readScopeNames(schema) {
  const values = schema?.properties?.scope?.enum;
  if (!Array.isArray(values) || values.length === 0) {
    throw new Error("Expected event definition scope enum");
  }
  return values.map((value) => String(value));
}

function readDirectionNames(schema) {
  const values = schema?.properties?.direction?.enum;
  if (!Array.isArray(values) || values.length === 0) {
    throw new Error("Expected event definition direction enum");
  }
  return values.map((value) => String(value));
}

function readServerProtocolVersion(serverSchema) {
  const readyVariant = serverSchema.oneOf.find(
    (variant) => variant?.properties?.kind?.const === "ready"
  );
  const version = readyVariant?.properties?.protocolVersion?.const;
  if (!Number.isInteger(version)) {
    throw new Error("Expected ready frame protocolVersion const");
  }
  return version;
}

function buildCatalogRevision(input) {
  const hash = createHash("sha256");
  hash.update(
    JSON.stringify(
      {
        clientKinds: input.frameMetadata.clientKinds,
        definitions: input.eventDefinitions.map((definition) => ({
          direction: definition.direction,
          payloadSchema: definition.payloadSchema,
          scope: definition.scope,
          topic: definition.topic,
          version: definition.version
        })),
        protocolVersion: input.protocolVersion,
        serverKinds: input.frameMetadata.serverKinds,
        sharedSchemas: input.sharedSchemas.map((schema) => ({
          name: schema.relativePath,
          schema: schema.resolvedSchema
        }))
      },
      null,
      2
    )
  );
  return `sha256:${hash.digest("hex").slice(0, 16)}`;
}

function renderTSIndex() {
  return `// Code generated by tools/scripts/generate-event-protocol.mjs. DO NOT EDIT.

export * from "./contracts.ts";
export * from "./registry.ts";
export * from "./validators.ts";
`;
}

function renderTSSchemas(input) {
  const payloadEntries = input.eventDefinitions
    .map(
      (definition) =>
        `  ${JSON.stringify(definition.topic)}: ${definition.payloadSchemaConstantName}`
    )
    .join(",\n");

  return `// Code generated by tools/scripts/generate-event-protocol.mjs. DO NOT EDIT.

${input.sharedSchemas
  .map((schema) =>
    renderSchemaConstant(schema.schemaConstantName, schema.resolvedSchema)
  )
  .join("\n\n")}

${input.eventDefinitions
  .map((definition) =>
    renderSchemaConstant(
      definition.payloadSchemaConstantName,
      definition.payloadSchema
    )
  )
  .join("\n\n")}

${renderSchemaConstant("businessEventEnvelopeSchema", input.envelopeSchema)}

${renderSchemaConstant("businessEventClientFrameSchema", input.clientFrameSchema)}

${renderSchemaConstant("businessEventServerFrameSchema", input.serverFrameSchema)}

export const businessEventPayloadSchemas = {
${payloadEntries}
} as const;
`;
}

function renderTSContracts(input) {
  const sharedDeclarations = input.sharedSchemas
    .map((schema) =>
      renderTSNamedDeclaration(schema.tsTypeName, schema.resolvedSchema)
    )
    .join("\n\n");

  const payloadDeclarations = input.eventDefinitions
    .map((definition) =>
      renderTSNamedDeclaration(
        definition.tsPayloadTypeName,
        unresolvedSchemaFromDefinition(definition.filePath).payloadSchema,
        {
          currentFilePath: definition.filePath,
          refTypeNames: buildTSRefTypeNames(input.sharedSchemas)
        }
      )
    )
    .join("\n\n");

  const eventAliases = input.eventDefinitions
    .map(
      (
        definition
      ) => `export type ${definition.tsEventTypeName} = BusinessEventEnvelopeV1<
  ${JSON.stringify(definition.topic)},
  ${definition.tsPayloadTypeName},
  ${definition.version}
>;`
    )
    .join("\n\n");

  const clientTopics = input.eventDefinitions
    .filter((definition) => definition.direction === "client->server")
    .map((definition) => JSON.stringify(definition.topic))
    .join(" | ");
  const serverTopics = input.eventDefinitions
    .filter((definition) => definition.direction === "server->client")
    .map((definition) => JSON.stringify(definition.topic))
    .join(" | ");

  return `// Code generated by tools/scripts/generate-event-protocol.mjs. DO NOT EDIT.

export const businessEventProtocolVersion = ${input.protocolVersion} as const;

export type BusinessEventDirection = ${input.directionNames
    .map((value) => JSON.stringify(value))
    .join(" | ")};

export type BusinessEventScopeName = ${input.scopeNames
    .map((value) => JSON.stringify(value))
    .join(" | ")};

export type BusinessEventTopic = ${input.eventDefinitions
    .map((definition) => JSON.stringify(definition.topic))
    .join(" | ")};

export interface BusinessEventScopeV1 {
  workspaceId?: string;
}

export interface BusinessEventEnvelopeBaseV1 {
  id: string;
  topic: string;
  version: number;
  emittedAt: string;
  scope?: BusinessEventScopeV1;
  payload: unknown;
}

export type BusinessEventEnvelopeV1<
  TTopic extends string = string,
  TPayload = unknown,
  TVersion extends number = number
> = Omit<BusinessEventEnvelopeBaseV1, "payload" | "topic" | "version"> & {
  topic: TTopic;
  version: TVersion;
  payload: TPayload;
};

${sharedDeclarations}

${payloadDeclarations}

${eventAliases}

export type ClientToServerEventTopic = ${clientTopics};

export type ServerToClientEventTopic = ${serverTopics};

export type ClientToServerEventV1 = ${input.eventDefinitions
    .filter((definition) => definition.direction === "client->server")
    .map((definition) => definition.tsEventTypeName)
    .join(" | ")};

export type ServerToClientEventV1 = ${input.eventDefinitions
    .filter((definition) => definition.direction === "server->client")
    .map((definition) => definition.tsEventTypeName)
    .join(" | ")};

export type BusinessEventV1 = ClientToServerEventV1 | ServerToClientEventV1;

export interface BusinessEventSubscribeFrameV1 {
  kind: "subscribe";
  requestId: string;
  topics: readonly ServerToClientEventTopic[];
  scope?: BusinessEventScopeV1;
}

export interface BusinessEventUnsubscribeFrameV1 {
  kind: "unsubscribe";
  requestId: string;
  topics: readonly ServerToClientEventTopic[];
  scope?: BusinessEventScopeV1;
}

export interface BusinessEventPublishFrameV1 {
  kind: "publish";
  requestId: string;
  event: ClientToServerEventV1;
}

export interface BusinessEventPingFrameV1 {
  kind: "ping";
  requestId: string;
  sentAt: string;
}

export type BusinessEventClientFrameV1 =
  | BusinessEventSubscribeFrameV1
  | BusinessEventUnsubscribeFrameV1
  | BusinessEventPublishFrameV1
  | BusinessEventPingFrameV1;

export interface BusinessEventReadyFrameV1 {
  kind: "ready";
  protocolVersion: typeof businessEventProtocolVersion;
  catalogRevision: string;
  serverTime: string;
}

export interface BusinessEventAckFrameV1 {
  kind: "ack";
  requestId: string;
  acceptedAt: string;
}

export interface BusinessEventEventFrameV1 {
  kind: "event";
  event: ServerToClientEventV1;
}

export interface BusinessEventErrorFrameV1 {
  kind: "error";
  requestId?: string | null;
  code: string;
  message: string;
  retryable?: boolean;
}

export interface BusinessEventPongFrameV1 {
  kind: "pong";
  requestId: string;
  sentAt: string;
}

export type BusinessEventServerFrameV1 =
  | BusinessEventReadyFrameV1
  | BusinessEventAckFrameV1
  | BusinessEventEventFrameV1
  | BusinessEventErrorFrameV1
  | BusinessEventPongFrameV1;
`;
}

function renderTSRegistry(input) {
  const definitions = input.eventDefinitions
    .map(
      (definition) => `  {
    topic: ${JSON.stringify(definition.topic)},
    version: ${definition.version},
    direction: ${JSON.stringify(definition.direction)},
    owner: ${JSON.stringify(definition.owner)},
    scope: ${JSON.stringify(definition.scope)}
  }`
    )
    .join(",\n");

  const byTopic = input.eventDefinitions
    .map(
      (definition) => `  ${JSON.stringify(definition.topic)}: {
    topic: ${JSON.stringify(definition.topic)},
    version: ${definition.version},
    direction: ${JSON.stringify(definition.direction)},
    owner: ${JSON.stringify(definition.owner)},
    scope: ${JSON.stringify(definition.scope)}
  }`
    )
    .join(",\n");

  return `// Code generated by tools/scripts/generate-event-protocol.mjs. DO NOT EDIT.

import type {
  BusinessEventDirection,
  BusinessEventScopeName,
  BusinessEventTopic,
  ClientToServerEventTopic,
  ServerToClientEventTopic
} from "./contracts.ts";

${input.eventDefinitions
  .map(
    (definition) =>
      `export const ${definition.topicConstantName} = ${JSON.stringify(definition.topic)} as const;`
  )
  .join("\n")}

export interface BusinessEventDefinition {
  topic: BusinessEventTopic;
  version: number;
  direction: BusinessEventDirection;
  owner: string;
  scope: BusinessEventScopeName;
}

export const businessEventCatalogRevision = ${JSON.stringify(
    input.catalogRevision
  )} as const;

export const businessEventDefinitions = [
${definitions}
] as const satisfies readonly BusinessEventDefinition[];

export const businessEventDefinitionByTopic = {
${byTopic}
} as const satisfies Record<BusinessEventTopic, BusinessEventDefinition>;

export const businessEventTopics = businessEventDefinitions.map(
  (definition) => definition.topic
) as readonly BusinessEventTopic[];

export const clientToServerEventTopics = businessEventDefinitions
  .filter((definition) => definition.direction === "client->server")
  .map((definition) => definition.topic) as readonly ClientToServerEventTopic[];

export const serverToClientEventTopics = businessEventDefinitions
  .filter((definition) => definition.direction === "server->client")
  .map((definition) => definition.topic) as readonly ServerToClientEventTopic[];

export function getBusinessEventDefinition(
  topic: string
): BusinessEventDefinition | null {
  return businessEventDefinitionByTopic[topic as BusinessEventTopic] ?? null;
}

export function isBusinessEventTopic(topic: string): topic is BusinessEventTopic {
  return topic in businessEventDefinitionByTopic;
}

export function isClientToServerEventTopic(
  topic: string
): topic is ClientToServerEventTopic {
  return clientToServerEventTopics.includes(topic as ClientToServerEventTopic);
}

export function isServerToClientEventTopic(
  topic: string
): topic is ServerToClientEventTopic {
  return serverToClientEventTopics.includes(topic as ServerToClientEventTopic);
}
`;
}

function renderTSValidators() {
  return `// Code generated by tools/scripts/generate-event-protocol.mjs. DO NOT EDIT.

import type {
  BusinessEventClientFrameV1,
  BusinessEventServerFrameV1,
  BusinessEventV1
} from "./contracts.ts";
import {
  getBusinessEventDefinition,
  isClientToServerEventTopic,
  isServerToClientEventTopic
} from "./registry.ts";
import {
  businessEventClientFrameSchema,
  businessEventEnvelopeSchema,
  businessEventPayloadSchemas,
  businessEventServerFrameSchema
} from "./schemas.ts";

export interface BusinessEventProtocolValidationIssue {
  path: string;
  message: string;
}

export interface BusinessEventProtocolValidationResult {
  ok: boolean;
  issues: BusinessEventProtocolValidationIssue[];
}

export function validateEventPayload(
  topic: string,
  value: unknown
): BusinessEventProtocolValidationResult {
  const schema = businessEventPayloadSchemas[topic as keyof typeof businessEventPayloadSchemas];
  if (!schema) {
    return resultFromIssues([
      {
        path: "payload.topic",
        message: "unknown business event topic"
      }
    ]);
  }

  const issues: BusinessEventProtocolValidationIssue[] = [];
  validateAgainstSchema(value, schema, "payload", issues);
  return resultFromIssues(issues);
}

export function validateEventEnvelope(
  value: unknown
): BusinessEventProtocolValidationResult {
  return validateEventEnvelopeInternal(value, "event", null);
}

export function validateClientEvent(
  value: unknown
): BusinessEventProtocolValidationResult {
  return validateEventEnvelopeInternal(value, "event", "client->server");
}

export function validateServerEvent(
  value: unknown
): BusinessEventProtocolValidationResult {
  return validateEventEnvelopeInternal(value, "event", "server->client");
}

export function validateClientFrame(
  value: unknown
): BusinessEventProtocolValidationResult {
  const issues: BusinessEventProtocolValidationIssue[] = [];
  validateAgainstSchema(value, businessEventClientFrameSchema, "frame", issues);

  if (isRecord(value)) {
    if (value.kind === "publish") {
      issues.push(
        ...validateClientEvent(value.event).issues.map((issue) => ({
          path: issue.path.replace(/^event/, "frame.event"),
          message: issue.message
        }))
      );
    }

    if (value.kind === "subscribe" || value.kind === "unsubscribe") {
      validateSubscriptionTopics(value.topics, issues);
    }
  }

  return resultFromIssues(issues);
}

export function validateServerFrame(
  value: unknown
): BusinessEventProtocolValidationResult {
  const issues: BusinessEventProtocolValidationIssue[] = [];
  validateAgainstSchema(value, businessEventServerFrameSchema, "frame", issues);

  if (isRecord(value) && value.kind === "event") {
    issues.push(
      ...validateServerEvent(value.event).issues.map((issue) => ({
        path: issue.path.replace(/^event/, "frame.event"),
        message: issue.message
      }))
    );
  }

  return resultFromIssues(issues);
}

export function assertValidEventEnvelope(
  value: unknown
): asserts value is BusinessEventV1 {
  assertValidResult(validateEventEnvelope(value));
}

export function assertValidClientFrame(
  value: unknown
): asserts value is BusinessEventClientFrameV1 {
  assertValidResult(validateClientFrame(value));
}

export function assertValidServerFrame(
  value: unknown
): asserts value is BusinessEventServerFrameV1 {
  assertValidResult(validateServerFrame(value));
}

export function formatBusinessEventProtocolValidationIssues(
  issues: readonly BusinessEventProtocolValidationIssue[]
): string {
  if (issues.length === 0) {
    return "business event protocol value is valid";
  }

  return issues.map((issue) => \`\${issue.path}: \${issue.message}\`).join("; ");
}

function validateEventEnvelopeInternal(
  value: unknown,
  rootPath: string,
  direction: "client->server" | "server->client" | null
): BusinessEventProtocolValidationResult {
  const issues: BusinessEventProtocolValidationIssue[] = [];
  validateAgainstSchema(value, businessEventEnvelopeSchema, rootPath, issues);

  if (!isRecord(value)) {
    return resultFromIssues(issues);
  }

  const topic = typeof value.topic === "string" ? value.topic : null;
  if (!topic) {
    return resultFromIssues(issues);
  }

  const definition = getBusinessEventDefinition(topic);
  if (!definition) {
    issues.push({
      path: \`\${rootPath}.topic\`,
      message: "unknown business event topic"
    });
    return resultFromIssues(issues);
  }

  if (value.version !== definition.version) {
    issues.push({
      path: \`\${rootPath}.version\`,
      message: \`event version must be \${definition.version} for topic \${definition.topic}\`
    });
  }

  if (direction === "client->server" && !isClientToServerEventTopic(topic)) {
    issues.push({
      path: \`\${rootPath}.topic\`,
      message: "topic is not publishable from client to server"
    });
  }

  if (direction === "server->client" && !isServerToClientEventTopic(topic)) {
    issues.push({
      path: \`\${rootPath}.topic\`,
      message: "topic is not publishable from server to client"
    });
  }

  issues.push(
    ...validateEventPayload(topic, value.payload).issues.map((issue) => ({
      path: issue.path.replace(/^payload/, \`\${rootPath}.payload\`),
      message: issue.message
    }))
  );

  return resultFromIssues(issues);
}

function validateSubscriptionTopics(
  value: unknown,
  issues: BusinessEventProtocolValidationIssue[]
) {
  if (!Array.isArray(value)) {
    return;
  }

  value.forEach((topic, index) => {
    if (typeof topic !== "string") {
      return;
    }
    if (!isServerToClientEventTopic(topic)) {
      issues.push({
        path: \`frame.topics[\${index}]\`,
        message: "clients may only subscribe to server->client topics"
      });
    }
  });
}

function validateAgainstSchema(
  value: unknown,
  schema: unknown,
  path: string,
  issues: BusinessEventProtocolValidationIssue[]
) {
  if (schema === true) {
    return;
  }
  if (!isRecord(schema)) {
    issues.push({ path, message: "invalid generated schema" });
    return;
  }

  if (schema.const !== undefined) {
    if (value !== schema.const) {
      issues.push({
        path,
        message: \`value must equal \${JSON.stringify(schema.const)}\`
      });
    }
    return;
  }

  if (Array.isArray(schema.oneOf)) {
    const branchErrors = schema.oneOf.map((branch) => {
      const branchIssues: BusinessEventProtocolValidationIssue[] = [];
      validateAgainstSchema(value, branch, path, branchIssues);
      return branchIssues;
    });
    if (!branchErrors.some((entry) => entry.length === 0)) {
      issues.push({
        path,
        message: "value does not match any allowed shape"
      });
    }
    return;
  }

  if (Array.isArray(schema.enum)) {
    if (!schema.enum.some((entry) => entry === value)) {
      issues.push({
        path,
        message: \`value must be one of \${schema.enum
          .map((entry) => JSON.stringify(entry))
          .join(", ")}\`
      });
    }
  }

  const schemaTypes = normalizeSchemaTypes(schema.type);
  if (schemaTypes.length > 0) {
    const matchedType = schemaTypes.find((type) => matchesSchemaType(value, type));
    if (!matchedType) {
      issues.push({
        path,
        message: \`value must be \${schemaTypes.join(" or ")}\`
      });
      return;
    }

    if (matchedType === "null") {
      return;
    }
    if (matchedType === "string") {
      validateStringSchema(value, schema, path, issues);
      return;
    }
    if (matchedType === "boolean") {
      return;
    }
    if (matchedType === "integer" || matchedType === "number") {
      validateNumberSchema(value, schema, path, issues);
      return;
    }
    if (matchedType === "array") {
      validateArraySchema(value, schema, path, issues);
      return;
    }
    if (matchedType === "object") {
      validateObjectSchema(value, schema, path, issues);
      return;
    }
  }
}

function validateStringSchema(
  value: unknown,
  schema: Record<string, unknown>,
  path: string,
  issues: BusinessEventProtocolValidationIssue[]
) {
  if (typeof value !== "string") {
    return;
  }
  if (
    typeof schema.minLength === "number" &&
    value.length < schema.minLength
  ) {
    issues.push({
      path,
      message: \`value must be at least \${schema.minLength} characters\`
    });
  }
  if (typeof schema.pattern === "string" && !(new RegExp(schema.pattern).test(value))) {
    issues.push({
      path,
      message: "value does not match the expected pattern"
    });
  }
}

function validateNumberSchema(
  value: unknown,
  schema: Record<string, unknown>,
  path: string,
  issues: BusinessEventProtocolValidationIssue[]
) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return;
  }
  if (schema.type === "integer" && !Number.isInteger(value)) {
    issues.push({
      path,
      message: "value must be an integer"
    });
  }
  if (typeof schema.minimum === "number" && value < schema.minimum) {
    issues.push({
      path,
      message: \`value must be at least \${schema.minimum}\`
    });
  }
}

function validateArraySchema(
  value: unknown,
  schema: Record<string, unknown>,
  path: string,
  issues: BusinessEventProtocolValidationIssue[]
) {
  if (!Array.isArray(value)) {
    return;
  }
  if (typeof schema.minItems === "number" && value.length < schema.minItems) {
    issues.push({
      path,
      message: \`value must contain at least \${schema.minItems} items\`
    });
  }
  value.forEach((entry, index) => {
    validateAgainstSchema(entry, schema.items, \`\${path}[\${index}]\`, issues);
  });
}

function validateObjectSchema(
  value: unknown,
  schema: Record<string, unknown>,
  path: string,
  issues: BusinessEventProtocolValidationIssue[]
) {
  if (!isRecord(value)) {
    return;
  }
  const properties = isRecord(schema.properties) ? schema.properties : {};
  const required = Array.isArray(schema.required) ? schema.required : [];

  for (const property of required) {
    if (!(property in value)) {
      issues.push({
        path: \`\${path}.\${property}\`,
        message: "value is required"
      });
    }
  }

  if (schema.additionalProperties === false) {
    for (const key of Object.keys(value)) {
      if (!(key in properties)) {
        issues.push({
          path: \`\${path}.\${key}\`,
          message: "unexpected property"
        });
      }
    }
  }

  for (const [key, propertySchema] of Object.entries(properties)) {
    if (!(key in value)) {
      continue;
    }
    validateAgainstSchema(value[key], propertySchema, \`\${path}.\${key}\`, issues);
  }
}

function normalizeSchemaTypes(value: unknown): string[] {
  if (typeof value === "string") {
    return [value];
  }
  if (Array.isArray(value)) {
    return value.filter((entry) => typeof entry === "string");
  }
  return [];
}

function matchesSchemaType(value: unknown, type: string): boolean {
  switch (type) {
    case "array":
      return Array.isArray(value);
    case "boolean":
      return typeof value === "boolean";
    case "integer":
      return typeof value === "number" && Number.isInteger(value);
    case "null":
      return value === null;
    case "number":
      return typeof value === "number" && !Number.isNaN(value);
    case "object":
      return isRecord(value);
    case "string":
      return typeof value === "string";
    default:
      return false;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function resultFromIssues(
  issues: readonly BusinessEventProtocolValidationIssue[]
): BusinessEventProtocolValidationResult {
  return {
    ok: issues.length === 0,
    issues: [...issues]
  };
}

function assertValidResult(result: BusinessEventProtocolValidationResult) {
  if (!result.ok) {
    throw new Error(
      formatBusinessEventProtocolValidationIssues(result.issues)
    );
  }
}
`;
}

function renderGoProtocol(input) {
  const clientTopicConsts = input.eventDefinitions
    .filter((definition) => definition.direction === "client->server")
    .map((definition) => `\t${toGoTopicConstant(definition.topic)},`)
    .join("\n");
  const serverTopicConsts = input.eventDefinitions
    .filter((definition) => definition.direction === "server->client")
    .map((definition) => `\t${toGoTopicConstant(definition.topic)},`)
    .join("\n");

  return `// Code generated by tools/scripts/generate-event-protocol.mjs. DO NOT EDIT.

package generated

import "encoding/json"

const (
\tBusinessEventProtocolVersion = ${input.protocolVersion}
\tBusinessEventCatalogRevision = ${goString(input.catalogRevision)}
)

type Topic string

const (
${input.eventDefinitions
  .map(
    (definition) =>
      `\t${toGoTopicConstant(definition.topic)} Topic = ${goString(definition.topic)}`
  )
  .join("\n")}
)

type Direction string

const (
\tDirectionClientToServer Direction = "client->server"
\tDirectionServerToClient Direction = "server->client"
)

type ScopeName string

const (
\tScopeNameGlobal ScopeName = "global"
\tScopeNameDesktop ScopeName = "desktop"
\tScopeNameWorkspace ScopeName = "workspace"
)

type EventDefinition struct {
\tTopic     Topic
\tVersion   int
\tDirection Direction
\tOwner     string
\tScope     ScopeName
}

type EventScope struct {
\tWorkspaceID *string \`json:"workspaceId,omitempty"\`
}

type EventEnvelope struct {
\tID        string          \`json:"id"\`
\tTopic     Topic           \`json:"topic"\`
\tVersion   int             \`json:"version"\`
\tEmittedAt string          \`json:"emittedAt"\`
\tScope     *EventScope     \`json:"scope,omitempty"\`
\tPayload   json.RawMessage \`json:"payload"\`
}

${input.sharedSchemas
  .map((schema) =>
    renderGoNamedStruct(schema.goTypeName, schema.resolvedSchema)
  )
  .join("\n\n")}

${input.eventDefinitions
  .map((definition) =>
    renderGoNamedStruct(
      definition.goPayloadTypeName,
      unresolvedSchemaFromDefinition(definition.filePath).payloadSchema,
      {
        currentFilePath: definition.filePath
      }
    )
  )
  .join("\n\n")}

${input.eventDefinitions
  .map(
    (definition) => `type ${definition.goEventTypeName} struct {
\tID        string                     \`json:"id"\`
\tTopic     Topic                      \`json:"topic"\`
\tVersion   int                        \`json:"version"\`
\tEmittedAt string                     \`json:"emittedAt"\`
\tScope     *EventScope                \`json:"scope,omitempty"\`
\tPayload   ${definition.goPayloadTypeName} \`json:"payload"\`
}`
  )
  .join("\n\n")}

type ClientSubscribeFrame struct {
\tKind      string \`json:"kind"\`
\tRequestID string \`json:"requestId"\`
\tTopics    []Topic \`json:"topics"\`
\tScope     *EventScope \`json:"scope,omitempty"\`
}

type ClientUnsubscribeFrame struct {
\tKind      string \`json:"kind"\`
\tRequestID string \`json:"requestId"\`
\tTopics    []Topic \`json:"topics"\`
\tScope     *EventScope \`json:"scope,omitempty"\`
}

type ClientPublishFrame struct {
\tKind      string        \`json:"kind"\`
\tRequestID string        \`json:"requestId"\`
\tEvent     EventEnvelope \`json:"event"\`
}

type ClientPingFrame struct {
\tKind      string \`json:"kind"\`
\tRequestID string \`json:"requestId"\`
\tSentAt    string \`json:"sentAt"\`
}

type ServerReadyFrame struct {
\tKind            string \`json:"kind"\`
\tProtocolVersion int    \`json:"protocolVersion"\`
\tCatalogRevision string \`json:"catalogRevision"\`
\tServerTime      string \`json:"serverTime"\`
}

type ServerAckFrame struct {
\tKind      string \`json:"kind"\`
\tRequestID string \`json:"requestId"\`
\tAcceptedAt string \`json:"acceptedAt"\`
}

type ServerEventFrame struct {
\tKind  string        \`json:"kind"\`
\tEvent EventEnvelope \`json:"event"\`
}

type ServerErrorFrame struct {
\tKind      string  \`json:"kind"\`
\tRequestID *string \`json:"requestId,omitempty"\`
\tCode      string  \`json:"code"\`
\tMessage   string  \`json:"message"\`
\tRetryable *bool   \`json:"retryable,omitempty"\`
}

type ServerPongFrame struct {
\tKind      string \`json:"kind"\`
\tRequestID string \`json:"requestId"\`
\tSentAt    string \`json:"sentAt"\`
}

var BusinessEventDefinitions = []EventDefinition{
${input.eventDefinitions
  .map(
    (definition) => `\t{
\t\tTopic: ${toGoTopicConstant(definition.topic)},
\t\tVersion: ${definition.version},
\t\tDirection: ${toGoDirectionConstant(definition.direction)},
\t\tOwner: ${goString(definition.owner)},
\t\tScope: ${toGoScopeConstant(definition.scope)},
\t},`
  )
  .join("\n")}
}

var businessEventDefinitionByTopic = map[Topic]EventDefinition{
${input.eventDefinitions
  .map(
    (definition) =>
      `\t${toGoTopicConstant(definition.topic)}: BusinessEventDefinitions[${input.eventDefinitions.indexOf(definition)}],`
  )
  .join("\n")}
}

var ClientToServerTopics = []Topic{
${clientTopicConsts}
}

var ServerToClientTopics = []Topic{
${serverTopicConsts}
}

func LookupEventDefinition(topic Topic) (EventDefinition, bool) {
\tdefinition, ok := businessEventDefinitionByTopic[topic]
\treturn definition, ok
}

func IsKnownTopic(topic Topic) bool {
\t_, ok := businessEventDefinitionByTopic[topic]
\treturn ok
}

func IsClientToServerTopic(topic Topic) bool {
\tswitch topic {
${input.eventDefinitions
  .filter((definition) => definition.direction === "client->server")
  .map(
    (definition) =>
      `\tcase ${toGoTopicConstant(definition.topic)}:\n\t\treturn true`
  )
  .join("\n")}
\tdefault:
\t\treturn false
\t}
}

func IsServerToClientTopic(topic Topic) bool {
\tswitch topic {
${input.eventDefinitions
  .filter((definition) => definition.direction === "server->client")
  .map(
    (definition) =>
      `\tcase ${toGoTopicConstant(definition.topic)}:\n\t\treturn true`
  )
  .join("\n")}
\tdefault:
\t\treturn false
\t}
}

func PayloadPrototypeForTopic(topic Topic) (any, bool) {
\tswitch topic {
${input.eventDefinitions
  .map(
    (definition) =>
      `\tcase ${toGoTopicConstant(definition.topic)}:\n\t\treturn &${definition.goPayloadTypeName}{}, true`
  )
  .join("\n")}
\tdefault:
\t\treturn nil, false
\t}
}

func EventPrototypeForTopic(topic Topic) (any, bool) {
\tswitch topic {
${input.eventDefinitions
  .map(
    (definition) =>
      `\tcase ${toGoTopicConstant(definition.topic)}:\n\t\treturn &${definition.goEventTypeName}{}, true`
  )
  .join("\n")}
\tdefault:
\t\treturn nil, false
\t}
}
`;
}

function renderSchemaConstant(name, schema) {
  return `export const ${name} = ${JSON.stringify(schema, null, 2)} as const;`;
}

function renderTSNamedDeclaration(name, schema, options = {}) {
  if (isObjectSchema(schema) && !Array.isArray(schema.oneOf)) {
    return `export interface ${name} ${renderTSObjectLiteral(schema, options, 0)}`;
  }
  return `export type ${name} = ${renderTSTypeExpression(schema, options, 0)};`;
}

function renderTSTypeExpression(schema, options, depth) {
  if (schema === true) {
    return "unknown";
  }
  if (schema?.$ref) {
    const refPath = resolveRefPath(schema.$ref, options.currentFilePath);
    const refTypeName = options.refTypeNames?.get(refPath);
    if (!refTypeName) {
      throw new Error(`Unsupported TypeScript schema reference ${schema.$ref}`);
    }
    return refTypeName;
  }
  if (schema?.const !== undefined) {
    return JSON.stringify(schema.const);
  }
  if (Array.isArray(schema?.enum)) {
    return schema.enum.map((value) => JSON.stringify(value)).join(" | ");
  }
  if (Array.isArray(schema?.oneOf)) {
    return schema.oneOf
      .map((entry) => renderTSTypeExpression(entry, options, depth))
      .join(" | ");
  }
  if (Array.isArray(schema?.type)) {
    return schema.type
      .map((entry) =>
        entry === "null"
          ? "null"
          : renderTSTypeExpression({ type: entry }, options, depth)
      )
      .join(" | ");
  }

  switch (schema?.type) {
    case "array":
      return `readonly (${renderTSTypeExpression(schema.items ?? true, options, depth + 1)})[]`;
    case "boolean":
      return "boolean";
    case "integer":
    case "number":
      return "number";
    case "object":
      return renderTSObjectLiteral(schema, options, depth);
    case "string":
      return "string";
    default:
      return "unknown";
  }
}

function renderTSObjectLiteral(schema, options, depth) {
  const properties = Object.entries(schema.properties ?? {});
  const required = new Set(schema.required ?? []);
  if (properties.length === 0) {
    if (
      schema.additionalProperties &&
      typeof schema.additionalProperties === "object"
    ) {
      return `Record<string, ${renderTSTypeExpression(
        schema.additionalProperties,
        options,
        depth + 1
      )}>`;
    }
    return "Record<string, unknown>";
  }

  const indent = "  ".repeat(depth + 1);
  const closingIndent = "  ".repeat(depth);
  const lines = properties.map(([key, propertySchema]) => {
    const propertyName = isValidTSIdentifier(key) ? key : JSON.stringify(key);
    const optional = required.has(key) ? "" : "?";
    const propertyType = renderTSTypeExpression(
      propertySchema,
      options,
      depth + 1
    );
    return `${indent}${propertyName}${optional}: ${propertyType};`;
  });

  return `{\n${lines.join("\n")}\n${closingIndent}}`;
}

function renderGoNamedStruct(name, schema, options = {}) {
  return `type ${name} struct {
${renderGoStructFields(schema, 1, options)}
}`;
}

function renderGoStructFields(schema, depth, options = {}) {
  const properties = Object.entries(schema.properties ?? {});
  const required = new Set(schema.required ?? []);
  const indent = "\t".repeat(depth);

  return properties
    .map(([key, propertySchema]) => {
      const fieldName = toPascalCase(key);
      const optional = !required.has(key);
      const fieldType = renderGoType(propertySchema, optional, options);
      const omitempty = optional ? ",omitempty" : "";
      return `${indent}${fieldName} ${fieldType} \`json:"${key}${omitempty}"\``;
    })
    .join("\n");
}

function renderGoType(schema, optional, options = {}) {
  if (schema === true) {
    return "any";
  }
  if (schema?.$ref) {
    if (typeof options.currentFilePath !== "string") {
      throw new Error(
        `Missing current file path for Go schema ref ${schema.$ref}`
      );
    }
    const refPath = resolveRefPath(schema.$ref, options.currentFilePath);
    const match = sharedSchemas.find((entry) => entry.filePath === refPath);
    if (!match) {
      throw new Error(`Unsupported Go schema reference ${schema.$ref}`);
    }
    return optional ? `*${match.goTypeName}` : match.goTypeName;
  }

  const schemaTypes = normalizeSchemaTypes(schema?.type);
  if (schemaTypes.includes("null")) {
    const nextSchema = {
      ...schema,
      type: schemaTypes.find((type) => type !== "null")
    };
    return renderGoType(nextSchema, true, options);
  }

  switch (schema?.type) {
    case "array":
      return `[]${renderGoType(schema.items ?? true, false, options)}`;
    case "boolean":
      return optional ? "*bool" : "bool";
    case "integer":
      if (schema.format === "int64") {
        return optional ? "*int64" : "int64";
      }
      return optional ? "*int" : "int";
    case "number":
      return optional ? "*float64" : "float64";
    case "object":
      if (!isObjectSchema(schema)) {
        return optional ? "*map[string]any" : "map[string]any";
      }
      if (Object.keys(schema.properties ?? {}).length === 0) {
        if (
          schema.additionalProperties &&
          typeof schema.additionalProperties === "object"
        ) {
          return `${optional ? "*" : ""}map[string]${renderGoType(
            schema.additionalProperties,
            false,
            options
          )}`;
        }
        return optional ? "*map[string]any" : "map[string]any";
      }
      return optional
        ? `*struct {\n${renderGoStructFields(schema, 2, options)}\n\t}`
        : `struct {\n${renderGoStructFields(schema, 2, options)}\n\t}`;
    case "string":
      return optional ? "*string" : "string";
    default:
      return "any";
  }
}

function writeGeneratedFile(outputPath, content) {
  mkdirSync(dirname(outputPath), { recursive: true });
  if (checkOnly) {
    if (!existsSync(outputPath)) {
      throw new Error(
        `Missing generated file: ${relative(repoRoot, outputPath)}`
      );
    }
    const existing = readFileSync(outputPath, "utf8");
    if (existing !== content) {
      throw new Error(
        `Generated file is out of date: ${relative(repoRoot, outputPath)}`
      );
    }
    return;
  }
  writeFileSync(outputPath, content, "utf8");
}

function loadJson(filePath) {
  if (jsonDocumentCache.has(filePath)) {
    return jsonDocumentCache.get(filePath);
  }
  const value = JSON.parse(readFileSync(filePath, "utf8"));
  jsonDocumentCache.set(filePath, value);
  return value;
}

function collectFiles(rootDir, predicate) {
  const files = [];

  walk(rootDir);
  return files;

  function walk(currentDir) {
    for (const entry of readdirSync(currentDir, { withFileTypes: true })) {
      const entryPath = resolve(currentDir, entry.name);
      if (entry.isDirectory()) {
        walk(entryPath);
        continue;
      }
      if (predicate(entry.name, entryPath)) {
        files.push(entryPath);
      }
    }
  }
}

function resolveSchemaRefs(value, currentFilePath, stack = []) {
  if (Array.isArray(value)) {
    return value.map((entry) =>
      resolveSchemaRefs(entry, currentFilePath, stack)
    );
  }
  if (!isPlainObject(value)) {
    return value;
  }
  if (typeof value.$ref === "string") {
    if (Object.keys(value).length !== 1) {
      throw new Error(
        `Schema refs with sibling keywords are unsupported: ${value.$ref}`
      );
    }
    const refKey = `${currentFilePath}::${value.$ref}`;
    if (stack.includes(refKey)) {
      throw new Error(
        `Circular schema ref detected: ${stack.join(" -> ")} -> ${refKey}`
      );
    }
    const resolved = resolveRef(value.$ref, currentFilePath);
    return resolveSchemaRefs(resolved.value, resolved.filePath, [
      ...stack,
      refKey
    ]);
  }

  return Object.fromEntries(
    Object.entries(value).map(([key, entry]) => [
      key,
      resolveSchemaRefs(entry, currentFilePath, stack)
    ])
  );
}

function resolveRef(ref, currentFilePath) {
  const [filePart, pointerPart = ""] = ref.split("#");
  const filePath =
    filePart.trim() === ""
      ? currentFilePath
      : resolve(dirname(currentFilePath), filePart);
  const targetDocument = loadJson(filePath);
  return {
    filePath,
    value:
      pointerPart === ""
        ? targetDocument
        : resolveJsonPointer(targetDocument, pointerPart)
  };
}

function resolveJsonPointer(root, pointer) {
  const segments = pointer
    .split("/")
    .filter(Boolean)
    .map((segment) => segment.replaceAll("~1", "/").replaceAll("~0", "~"));

  let current = root;
  for (const segment of segments) {
    if (!isPlainObject(current) && !Array.isArray(current)) {
      throw new Error(`Unable to resolve JSON pointer segment ${segment}`);
    }
    current = current[segment];
  }
  return current;
}

function validateAgainstSchema(value, schema, path, issues) {
  if (schema === true) {
    return;
  }
  if (!isPlainObject(schema)) {
    issues.push({ path, message: "invalid generator schema" });
    return;
  }
  if (schema.const !== undefined) {
    if (value !== schema.const) {
      issues.push({
        path,
        message: `value must equal ${JSON.stringify(schema.const)}`
      });
    }
    return;
  }
  if (Array.isArray(schema.oneOf)) {
    const branchMatches = schema.oneOf.some((entry) => {
      const branchIssues = [];
      validateAgainstSchema(value, entry, path, branchIssues);
      return branchIssues.length === 0;
    });
    if (!branchMatches) {
      issues.push({ path, message: "value does not match any allowed shape" });
    }
    return;
  }
  if (Array.isArray(schema.enum) && !schema.enum.includes(value)) {
    issues.push({
      path,
      message: `value must be one of ${schema.enum.map((entry) => JSON.stringify(entry)).join(", ")}`
    });
  }

  const schemaTypes = normalizeSchemaTypes(schema.type);
  if (schemaTypes.length > 0) {
    if (!schemaTypes.some((type) => matchesSchemaType(value, type))) {
      issues.push({
        path,
        message: `value must be ${schemaTypes.join(" or ")}`
      });
      return;
    }
    if (value === null) {
      return;
    }
  }

  if (typeof schema.pattern === "string" && typeof value === "string") {
    if (!new RegExp(schema.pattern).test(value)) {
      issues.push({
        path,
        message: "value does not match the expected pattern"
      });
    }
  }
  if (typeof schema.minLength === "number" && typeof value === "string") {
    if (value.length < schema.minLength) {
      issues.push({
        path,
        message: `value must be at least ${schema.minLength} characters`
      });
    }
  }
  if (typeof schema.minimum === "number" && typeof value === "number") {
    if (value < schema.minimum) {
      issues.push({
        path,
        message: `value must be at least ${schema.minimum}`
      });
    }
  }
  if (typeof schema.minItems === "number" && Array.isArray(value)) {
    if (value.length < schema.minItems) {
      issues.push({
        path,
        message: `value must contain at least ${schema.minItems} items`
      });
    }
  }

  if (isPlainObject(value) && schema.type === "object") {
    const properties = isPlainObject(schema.properties)
      ? schema.properties
      : {};
    const required = Array.isArray(schema.required) ? schema.required : [];

    for (const property of required) {
      if (!(property in value)) {
        issues.push({
          path: `${path}.${property}`,
          message: "value is required"
        });
      }
    }

    if (schema.additionalProperties === false) {
      for (const key of Object.keys(value)) {
        if (!(key in properties)) {
          issues.push({
            path: `${path}.${key}`,
            message: "unexpected property"
          });
        }
      }
    }

    for (const [key, propertySchema] of Object.entries(properties)) {
      if (!(key in value)) {
        continue;
      }
      validateAgainstSchema(
        value[key],
        propertySchema,
        `${path}.${key}`,
        issues
      );
    }
  }

  if (Array.isArray(value) && schema.type === "array") {
    value.forEach((entry, index) => {
      validateAgainstSchema(
        entry,
        schema.items ?? true,
        `${path}[${index}]`,
        issues
      );
    });
  }
}

function validateSupportedSchema(schema, label) {
  walkSchema(schema, label);
}

function walkSchema(schema, label) {
  if (schema === true) {
    return;
  }
  if (!isPlainObject(schema)) {
    throw new Error(`Unsupported schema node in ${label}`);
  }
  if (schema.$ref !== undefined) {
    throw new Error(`Unresolved schema ref remained in ${label}`);
  }
  if (schema.anyOf !== undefined || schema.allOf !== undefined) {
    throw new Error(`Unsupported schema composition in ${label}`);
  }

  const schemaTypes = normalizeSchemaTypes(schema.type);
  for (const type of schemaTypes) {
    if (
      ![
        "array",
        "boolean",
        "integer",
        "null",
        "number",
        "object",
        "string"
      ].includes(type)
    ) {
      throw new Error(`Unsupported schema type ${type} in ${label}`);
    }
  }

  if (Array.isArray(schema.oneOf)) {
    schema.oneOf.forEach((entry, index) =>
      walkSchema(entry, `${label}.oneOf[${index}]`)
    );
  }
  if (isPlainObject(schema.properties)) {
    for (const [key, value] of Object.entries(schema.properties)) {
      walkSchema(value, `${label}.properties.${key}`);
    }
  }
  if (schema.items !== undefined) {
    walkSchema(schema.items, `${label}.items`);
  }
}

function unresolvedSchemaFromDefinition(filePath) {
  return loadJson(filePath);
}

function buildTSRefTypeNames(sharedSchemaEntries) {
  return new Map(
    sharedSchemaEntries.map((entry) => [entry.filePath, entry.tsTypeName])
  );
}

function resolveRefPath(ref, currentFilePath) {
  const [filePart] = ref.split("#");
  if (filePart.trim() === "") {
    return currentFilePath;
  }
  return resolve(dirname(currentFilePath), filePart);
}

function formatIssues(issues) {
  return issues.map((issue) => `${issue.path}: ${issue.message}`).join("; ");
}

function normalizeSchemaTypes(value) {
  if (typeof value === "string") {
    return [value];
  }
  if (Array.isArray(value)) {
    return value.filter((entry) => typeof entry === "string");
  }
  return [];
}

function matchesSchemaType(value, type) {
  switch (type) {
    case "array":
      return Array.isArray(value);
    case "boolean":
      return typeof value === "boolean";
    case "integer":
      return typeof value === "number" && Number.isInteger(value);
    case "null":
      return value === null;
    case "number":
      return typeof value === "number" && !Number.isNaN(value);
    case "object":
      return isPlainObject(value);
    case "string":
      return typeof value === "string";
    default:
      return false;
  }
}

function isObjectSchema(schema) {
  return isPlainObject(schema) && schema.type === "object";
}

function isPlainObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isValidTSIdentifier(value) {
  return /^[A-Za-z_$][A-Za-z0-9_$]*$/.test(value);
}

function toPascalCase(value) {
  return value
    .split(/[^A-Za-z0-9]+/)
    .filter(Boolean)
    .map((segment) => segment[0].toUpperCase() + segment.slice(1))
    .join("");
}

function toCamelCase(value) {
  const pascal = toPascalCase(value);
  return pascal[0].toLowerCase() + pascal.slice(1);
}

function toGoTopicConstant(topic) {
  return `Topic${toPascalCase(topic)}`;
}

function toGoDirectionConstant(direction) {
  return direction === "client->server"
    ? "DirectionClientToServer"
    : "DirectionServerToClient";
}

function toGoScopeConstant(scope) {
  switch (scope) {
    case "desktop":
      return "ScopeNameDesktop";
    case "global":
      return "ScopeNameGlobal";
    case "workspace":
      return "ScopeNameWorkspace";
    default:
      throw new Error(`Unsupported scope ${scope}`);
  }
}

function goString(value) {
  return JSON.stringify(value);
}

async function formatTypeScript(source) {
  return await format(source, {
    ...prettierConfig,
    parser: "typescript"
  });
}

function formatGo(source) {
  return execFileSync("gofmt", {
    encoding: "utf8",
    input: source
  });
}
