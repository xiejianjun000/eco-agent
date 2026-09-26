/**
 * Tool bridge: discovers MCP tools, registers them on the harness ToolRuntime
 * under deterministic server-qualified public names, and handles re-sync when
 * the server's tool list changes.
 *
 * Naming contract (see the mcp-client Agent Note "Naming invariants"): every MCP tool
 * has the stable identity `(serverName, rawName)`; the model-facing public name
 * is `mcp__<serverName>__<rawName>`, normalized to the DeepSeek function-name
 * constraints. The raw name is only ever sent on the wire (`tools/call`); the
 * public name is never parsed to recover it.
 *
 * @module
 */

import { createHash } from 'node:crypto'
import { isDeepStrictEqual } from 'node:util'
import { specTypeSchemas, type Client, type ImageContent } from '@modelcontextprotocol/client'
import type { Context } from '@deepseek-ai/cordis'
import { isImageAdmissionError } from '@deepseek-ai/dsh-attachment'
import type { AttachmentStore, ImageAttachmentRef, ImageMediaType, SaveImageAttachment } from '@deepseek-ai/dsh-attachment'
import type { ContentBlock } from '@deepseek-ai/dsh-llm'
import type { ToolDefinition, ToolExecution, ToolExecutionResult } from '@deepseek-ai/dsh-tools'
import { assertSupportedJsonSchema } from '@deepseek-ai/dsh-tools'
import type { JsonSchemaNode } from '@deepseek-ai/dsh-tools'
import type { JsonValue } from '@deepseek-ai/dsh-util-values'

/** Resolved options relevant to tool bridging. */
export interface ToolBridgeOptions {
  /** Whether a registry conflict is contained or rejects this synchronization. */
  registrationFailure: 'contain' | 'throw'
  serverName: string
  toolCallTimeoutMs: number
  /**
   * Invoked when a tool call fails because the server dropped its MCP session
   * (e.g. "Session not found" after a server restart). The connection
   * supervisor uses this to re-establish the session instead of leaving every
   * tool call broken until a manual reload.
   */
  onSessionLost?: () => void
}

/** JSON-RPC error code the SDK surfaces for a server-rejected request, including an expired session. */
const SESSION_NOT_FOUND_CODE = -32600

/** Detect a dropped MCP session ("Session not found") independently of the SDK's error class identity. */
function isSessionNotFound(error: unknown): boolean {
  if (typeof error !== 'object' || error === null) return false
  const candidate = error as { code?: unknown; message?: unknown }
  if (candidate.code !== SESSION_NOT_FOUND_CODE) return false
  return typeof candidate.message === 'string' && /session\s+not\s+found/i.test(candidate.message)
}

/** State for one sync generation: the current set of disposers keyed by public name. */
export type ToolDisposers = Map<string, () => void>

/** Canonical MCP result exposed to PTC mode without discarding protocol blocks. */
export type McpResult<Structured extends JsonValue = JsonValue> = {
  content: JsonValue[]
  structuredContent?: Structured
}

/**
 * DeepSeek function-name contract: at most 64 characters. Wire-protocol
 * constant, not configuration.
 */
const MAX_PUBLIC_NAME_LENGTH = 64

/** DeepSeek function-name contract: only `[A-Za-z0-9_-]` is allowed. */
const INVALID_NAME_CHARS = /[^A-Za-z0-9_-]/g

/** Hex chars of the SHA-256 identity hash appended on lossy normalization. */
const HASH_LENGTH = 12

/** Raster formats supported by the durable attachment vocabulary. */
const IMAGE_MEDIA_TYPES: readonly ImageMediaType[] = [
  'image/png',
  'image/jpeg',
  'image/webp',
  'image/gif',
]

/** Canonical RFC 4648 base64, excluding whitespace and URL-safe aliases. */
const CANONICAL_BASE64 = /^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/

/**
 * Derive the model-facing public name for one MCP tool.
 *
 * Deterministic pure function of `(serverName, rawName)`: the clean case is
 * `mcp__<serverName>__<rawName>` verbatim. When character replacement or
 * truncation to the DeepSeek function-name contract (64 chars,
 * `[A-Za-z0-9_-]`) changes the name, a 12-hex-char SHA-256 hash of the
 * identity is appended so distinct MCP identities never collapse into the
 * same public name.
 *
 * @param serverName - Stable local namespace from plugin config.
 * @param rawName - The MCP server's own tool name.
 * @returns The globally unique, model-facing ToolRuntime name.
 */
export function publicToolName(serverName: string, rawName: string): string {
  const joined = `mcp__${serverName}__${rawName}`
  const normalized = joined.replace(INVALID_NAME_CHARS, '_')
  if (normalized === joined && normalized.length <= MAX_PUBLIC_NAME_LENGTH) return normalized
  const hash = createHash('sha256').update(`${serverName}\0${rawName}`).digest('hex').slice(0, HASH_LENGTH)
  return `${normalized.slice(0, MAX_PUBLIC_NAME_LENGTH - HASH_LENGTH - 1)}_${hash}`
}

/**
 * Sync the MCP server's tool list into the harness ToolRuntime.
 *
 * Two phases keep the swap safe:
 *
 * 1. Fetch: let the SDK aggregate `tools/list` and build the full next
 *    generation of `ToolDefinition`s under public names. Any failure here
 *    (network error or duplicate raw name) rejects
 *    and leaves the previous generation registered untouched.
 * 2. Swap: dispose the previous generation, register the new one. A registry
 *    conflict here can only mean a foreign registration squats on this
 *    server's `mcp__<serverName>__` namespace — the partial generation is
 *    rolled back (zero tools from this server) and logged. Initial strict
 *    synchronization may propagate the conflict so its parent transaction
 *    rejects; ordinary clients and later re-syncs return an empty map.
 *
 * @param client - Connected MCP Client instance used to list and call tools.
 * @param ctx - Cordis context providing the `tools` service for registration.
 * @param opts - Bridge options: server namespace and per-call timeout.
 * @param previous - Disposer map from the prior sync generation; disposed
 *   during the swap phase (only after the fetch phase succeeded).
 * @returns A map of registered public tool names to their unregister
 *   disposers — the exact set of live registrations owned by this server.
 */
export async function syncTools(
  client: Client,
  ctx: Context,
  opts: ToolBridgeOptions,
  previous: ToolDisposers,
): Promise<ToolDisposers> {
  // Phase 1: fetch and build the next generation without touching the registry.
  const definitions = new Map<string, ToolDefinition>()
  const response = client.getServerCapabilities()?.tools === undefined
    ? { tools: [] }
    : await client.listTools(undefined, { cacheMode: 'refresh' })
  for (const tool of response.tools) {
    const publicName = publicToolName(opts.serverName, tool.name)
    const app = appBinding(opts.serverName, tool.name, tool._meta)
    if (definitions.has(publicName)) {
      throw new Error(
        `mcp-client(${opts.serverName}): server listed tool "${tool.name}" more than once — invalid tool list`,
      )
    }
    definitions.set(publicName, createMcpToolDefinition(ctx, {
      name: publicName,
      rawName: tool.name,
      description: tool.description ?? '',
      inputSchema: tool.inputSchema,
      outputSchema: tool.outputSchema,
      taskRequired: tool.execution?.taskSupport === 'required',
      // `_meta.ui.resourceUri` is the MCP App declaration; most tools have none.
      ...app === undefined ? {} : { app },
      listResources: async () => {
        try {
          return await client.listResources() as JsonValue
        } catch (error) {
          if (opts.onSessionLost !== undefined && isSessionNotFound(error)) opts.onSessionLost()
          throw error
        }
      },
      readResource: async (uri, execution) => {
        try {
          const response = await client.readResource(
            { uri },
            { signal: execution.signal, timeout: opts.toolCallTimeoutMs },
          )
          return response as JsonValue
        } catch (error) {
          if (opts.onSessionLost !== undefined && isSessionNotFound(error)) opts.onSessionLost()
          throw error
        }
      },
      call: async (args, execution) => {
        try {
          return await client.callTool(
            { name: tool.name, arguments: args },
            { signal: execution.signal, timeout: opts.toolCallTimeoutMs, toolDefinition: tool },
          )
        } catch (error) {
          if (opts.onSessionLost !== undefined && isSessionNotFound(error)) opts.onSessionLost()
          throw error
        }
      },
    }))
  }

  // Phase 2: swap generations.
  for (const dispose of previous.values()) dispose()
  const disposers: ToolDisposers = new Map()
  try {
    for (const [publicName, definition] of definitions) {
      disposers.set(publicName, ctx.tools.register(definition))
    }
  } catch (error) {
    // A conflict on an `mcp__<serverName>__`-qualified name means a foreign
    // registration occupies this server's namespace. Roll back so the model
    // sees either the full generation or none of it — never a partial set.
    for (const dispose of disposers.values()) dispose()
    ctx.logger.error(`mcp-client(${opts.serverName}): tool registration failed, no tools registered: ${String(error)}`)
    if (opts.registrationFailure === 'throw') throw error
    return new Map()
  }
  return disposers
}

/** Fields read from canonical content, including policy-owned value replacements. */
interface McpContentBlock {
  type: string
  text?: string
  mimeType?: string
  data?: string
  name?: string
  uri?: string
}

/** Async rich projection staged for one exact ToolRuntime execution. */
interface PreparedProjection {
  /** Canonical MCP value returned by execute before registry materialization. */
  value: McpResult
  /** Synchronous output.render projection expected before finalization. */
  fallback: ContentBlock[]
  /** Image-enriched or explicit-refusal projection prepared during execute. */
  content: ContentBlock[]
}

/**
 * The MCP App UI resource a tool declares through `_meta.ui.resourceUri`.
 *
 * A server that ships an interactive result publishes the App's HTML as a
 * `ui://` resource and points the tool at it; the tool call itself still
 * returns the compact textual summary the model reads. Only a tool carrying
 * this binding projects an App descriptor into its result meta, so ordinary
 * MCP tools pay nothing.
 */
export interface McpAppBinding {
  /** Configured server namespace the App's resource is read through. */
  serverName: string
  /** Upstream tool name, replayed when the App calls back into the server. */
  rawName: string
  /** `ui://` URI of the App resource. */
  uri: string
}

/** One App resource read back from the server, before MIME qualification. */
interface McpAppResource {
  uri: string
  mimeType?: string
  text?: string
  _meta?: JsonValue
}

/**
 * Read a tool's declared App resource URI out of its upstream `_meta`.
 *
 * Anything that is not a `ui://` string yields `undefined`: the App
 * vocabulary is opt-in, and a malformed declaration must not change how the
 * tool is registered or called.
 *
 * @param serverName - configured server namespace owning the resource.
 * @param rawName - upstream tool name.
 * @param toolMeta - the tool's advertised `_meta`, if any.
 * @returns the App binding, or `undefined` when the tool declares none.
 */
export function appBinding(serverName: string, rawName: string, toolMeta: unknown): McpAppBinding | undefined {
  if (typeof toolMeta !== 'object' || toolMeta === null) return undefined
  const ui = (toolMeta as { ui?: unknown }).ui
  if (typeof ui !== 'object' || ui === null) return undefined
  const uri = (ui as { resourceUri?: unknown }).resourceUri
  if (typeof uri !== 'string' || !uri.startsWith('ui://')) return undefined
  return { serverName, rawName, uri }
}

/** Normalize a `resources/read` response's first content entry. */
function appResourceFrom(response: JsonValue, uri: string): McpAppResource | undefined {
  if (!isRecord(response)) return undefined
  const contents = response['contents']
  if (!Array.isArray(contents)) return undefined
  const first: unknown = contents[0]
  if (!isRecord(first)) return undefined
  return {
    uri: typeof first['uri'] === 'string' ? first['uri'] : uri,
    ...typeof first['mimeType'] === 'string' ? { mimeType: first['mimeType'] } : {},
    ...typeof first['text'] === 'string' ? { text: first['text'] } : {},
    ...first['_meta'] !== undefined ? { _meta: first['_meta'] as JsonValue } : {},
  }
}

/**
 * Find one resource's declared `_meta` in `resources/list`.
 *
 * The CSP an App needs to run lives on the resource declaration, not on the
 * bytes `resources/read` returns, so a read response alone cannot tell the
 * sandbox what to allow. Best-effort: a server that will not list resources
 * simply contributes no declaration, and the sandbox keeps its secure default.
 *
 * @param list - list reader bound to the live connection.
 * @param uri - App resource URI to look up.
 * @returns the declaration, or `undefined` when the server serves none.
 */
async function declaredResourceMeta(
  list: () => Promise<JsonValue | undefined>,
  uri: string,
): Promise<JsonValue | undefined> {
  let page: JsonValue | undefined
  try {
    page = await list()
  } catch {
    // An unlistable server must not cost the App its already-read body.
    return undefined
  }
  if (!isRecord(page) || !Array.isArray(page['resources'])) return undefined
  for (const entry of page['resources'] as unknown[]) {
    if (isRecord(entry) && entry['uri'] === uri && entry['_meta'] !== undefined) {
      return entry['_meta'] as JsonValue
    }
  }
  return undefined
}

/** Keep a supported advertised schema; unsupported MCP vocabulary falls back to JsonValue. */
function supportedOutputSchema(candidate: unknown): JsonSchemaNode | undefined {
  if (candidate === undefined) return undefined
  try {
    assertSupportedJsonSchema(candidate)
    return candidate
  } catch {
    return undefined
  }
}

/** One upstream MCP tool and the callback that obtains its raw protocol result. */
export interface McpToolDefinitionOptions {
  /** ToolRuntime name presented to the model. */
  name: string
  /** Upstream name used in result diagnostics. */
  rawName: string
  /** Upstream model-facing description. */
  description: string
  /** Upstream JSON input schema. */
  inputSchema: Record<string, unknown>
  /** Advertised structured output schema, when present. */
  outputSchema?: unknown
  /** Whether the upstream tool requires the unsupported task execution extension. */
  taskRequired?: boolean
  /**
   * Declared MCP App resource, when the tool advertises one. It carries the
   * server namespace and raw tool name an App-initiated call replays.
   */
  app?: McpAppBinding
  /**
   * Read one `ui://` resource through the live connection. Best-effort: a
   * failure degrades to an App-less result and never fails the tool call.
   * @param uri - App resource URI.
   * @param execution - exact ToolRuntime invocation, for cancellation.
   * @returns the raw `resources/read` result, or `undefined` when unreadable.
   */
  readResource?: (uri: string, execution: ToolExecution) => Promise<JsonValue | undefined>
  /**
   * List the server's resources, for the App resource's declared `_meta`
   * (CSP and border hints). Best-effort, same as {@link readResource}.
   * @returns the raw `resources/list` result, or `undefined` when unavailable.
   */
  listResources?: () => Promise<JsonValue | undefined>
  /**
   * Obtain one raw MCP result from the provider.
   * @param args - model arguments admitted by the ToolRuntime.
   * @param execution - exact ToolRuntime invocation, including its Agent and cancellation.
   * @returns the external result object, validated before content projection.
   */
  call(args: Record<string, unknown>, execution: ToolExecution): Promise<unknown>
}

/**
 * Adapt an upstream MCP tool to canonical values and durable image content.
 * Registration, provider lifetime, deadlines, and transport belong to the caller.
 * @param ctx - plugin context carrying optional attachment and model services.
 * @param options - upstream tool fields and its raw-result callback.
 * @returns the unregistered ToolRuntime definition.
 */
export function createMcpToolDefinition(
  ctx: Context,
  options: McpToolDefinitionOptions,
): ToolDefinition {
  const { name, rawName, description, inputSchema } = options
  const projections = new WeakMap<ToolExecution, PreparedProjection>()
  return {
    name,
    description,
    parameters: inputSchema,
    output: createOutput(rawName, supportedOutputSchema(options.outputSchema), options.app),
    execute: createExecutor(ctx, options, projections),
    finalizeContent(exec: Readonly<ToolExecution>, result: Readonly<ToolExecutionResult>) {
      const projection = projections.get(exec)
      if (projection === undefined) return undefined
      projections.delete(exec)
      if (result.isError) return undefined
      if (!isDeepStrictEqual(result.value, projection.value)) return undefined
      if (!isDeepStrictEqual(result.content, projection.fallback)) return undefined
      return projection.content
    },
  }
}

/**
 * Build the canonical result schema, the text projection, and — for an App
 * tool — the App descriptor the UI renders.
 *
 * The descriptor is projected from `presentationMeta`, whose only inputs are
 * the arguments and the canonical value, so the resource the App needs is
 * carried inside the value by `createExecutor` under a key this schema
 * declares. The model still sees only the extracted text: nothing about the
 * App widens what the tool returns to the conversation.
 */
function createOutput(
  rawName: string,
  structuredSchema: JsonSchemaNode | undefined,
  app: McpAppBinding | undefined,
): ToolDefinition['output'] {
  return {
    schema: {
      type: 'object',
      properties: {
        content: { type: 'array', items: {} },
        structuredContent: structuredSchema ?? {},
        // Declared only for App tools: the read `ui://` resource, staged here
        // because `presentationMeta` is a pure projection of args and value.
        ...app === undefined ? {} : { appResource: { type: 'object' } },
      },
      required: structuredSchema === undefined ? ['content'] : ['content', 'structuredContent'],
      additionalProperties: false,
    },
    render(_args: unknown, value: JsonValue) {
      const result = value as unknown as McpResult
      return [{ type: 'text', text: extractText(result.content, rawName) }]
    },
    ...app === undefined ? {} : {
      presentationMeta(_args: unknown, value: JsonValue): JsonValue {
        const result = value as unknown as McpResult & { appResource?: McpAppResource }
        const resource = result.appResource
        // Declared but unread (read failed, or the server returned no text):
        // decline instead of projecting a card with nothing to render.
        if (resource === undefined || typeof resource.text !== 'string') return null
        return {
          card: 'mcp-app',
          serverName: app.serverName,
          toolName: app.rawName,
          resource: {
            uri: resource.uri,
            ...resource.mimeType === undefined ? {} : { mimeType: resource.mimeType },
            text: resource.text,
            ...resource._meta === undefined ? {} : { _meta: resource._meta },
          },
          result: {
            content: result.content,
            ...result.structuredContent === undefined
              ? {}
              : { structuredContent: result.structuredContent },
          },
        }
      },
    },
  }
}

/**
 * Read the App resource behind a tool's declared `ui://` URI.
 *
 * Strictly best-effort: the tool call itself already succeeded, and a resource
 * the server will not serve must not turn a working call into a failure. A
 * refusal degrades to an App-less result — the model still sees the tool's
 * own text, and no UI card is projected.
 *
 * @param ctx - plugin context, for the refusal diagnostic.
 * @param options - tool options carrying the App binding and resource reader.
 * @param exec - exact ToolRuntime invocation, for cancellation.
 * @returns the normalized resource, or `undefined` when it cannot be read.
 */
async function stageAppResource(
  ctx: Context,
  options: McpToolDefinitionOptions,
  exec: ToolExecution,
): Promise<McpAppResource | undefined> {
  const { app, readResource, listResources } = options
  if (app === undefined || readResource === undefined) return undefined
  try {
    const response = await readResource(app.uri, exec)
    if (response === undefined) return undefined
    const resource = appResourceFrom(response, app.uri)
    if (resource === undefined || resource._meta !== undefined || listResources === undefined) {
      return resource
    }
    const declared = await declaredResourceMeta(listResources, app.uri)
    return declared === undefined ? resource : { ...resource, _meta: declared }
  } catch (error: unknown) {
    ctx.logger.warn(
      `mcp-client(${app.serverName}): App resource "${app.uri}" is unreadable, rendering without the App: ${String(error)}`,
    )
    return undefined
  }
}

/**
 * Invoke the caller-owned raw-result callback and prepare canonical content.
 * MCP isError results reject before image storage so ToolRuntime records failure.
 */
function createExecutor(
  ctx: Context,
  options: McpToolDefinitionOptions,
  projections: WeakMap<ToolExecution, PreparedProjection>,
): ToolDefinition['execute'] {
  const { rawName, taskRequired } = options
  return async (args: unknown, exec: ToolExecution) => {
    if (taskRequired) {
      throw new Error(`Tool "${rawName}" requires task-based execution, which this bridge does not support`)
    }
    // The agent loop passes `JSON.parse(model_arguments)` which is usually an
    // object, but can be any JSON value if the model misbehaves (outputs a bare
    // string/number/null). Fallback to {} lets the MCP server produce a
    // specific "missing required param" error the model can learn from.
    const argsObj = (typeof args === 'object' && args !== null ? args : {}) as Record<string, unknown>
    const parsed = specTypeSchemas.CallToolResult['~standard'].validate(await options.call(argsObj, exec))
    if (parsed.issues !== undefined) {
      throw new Error(`Tool "${rawName}" returned an invalid MCP result: ${parsed.issues.map(issue => issue.message).join('; ')}`)
    }
    const result = parsed.value

    const content = result.content as unknown as JsonValue[]
    const text = extractText(content, rawName)

    // MCP isError → throw so ToolRuntime produces an isError result for the model.
    if (result.isError === true) {
      throw new Error(text)
    }

    const value: McpResult & { appResource?: McpAppResource } = {
      content,
      ...result.structuredContent !== undefined
        ? { structuredContent: result.structuredContent as JsonValue }
        : {},
    }
    // An App tool's resource is read after the call succeeds and staged on the
    // value, where the pure `presentationMeta` projection can reach it.
    const staged = await stageAppResource(ctx, options, exec)
    if (staged !== undefined) value.appResource = staged
    if (containsImage(content)) {
      const fallback: ContentBlock[] = [{ type: 'text', text: extractText(content, rawName) }]
      const projected = await prepareImageProjection(ctx, exec, content, rawName)
      projections.set(exec, { value, fallback, content: projected })
    }
    return value
  }
}

/** Whether an untrusted MCP content array contains a declared image block. */
function containsImage(content: JsonValue[]): boolean {
  return content.some(value => isRecord(value) && value.type === 'image')
}

/** Narrow an untyped value to a string-keyed object. */
function isRecord(value: unknown): value is { [key: string]: JsonValue } {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** Narrow a declared MIME string to the durable image vocabulary. */
function isImageMediaType(value: string): value is ImageMediaType {
  return IMAGE_MEDIA_TYPES.includes(value as ImageMediaType)
}

/** Decode one projected image without accepting base64 aliases. */
function decodeImage(block: ImageContent): SaveImageAttachment {
  if (!isImageMediaType(block.mimeType)) {
    throw new Error('the declared media type is not PNG, JPEG, WebP, or GIF')
  }
  if (!CANONICAL_BASE64.test(block.data)) {
    throw new Error('the image data is not canonical base64')
  }
  const data = Buffer.from(block.data, 'base64')
  if (data.toString('base64') !== block.data) {
    throw new Error('the image data is not canonical base64')
  }
  return { data, mediaType: block.mimeType }
}

/**
 * Resolve the active model route and durable store for an image-bearing result.
 * @param ctx - plugin context with optional services.
 * @param exec - exact tool execution whose agent supplies the latest route.
 * @returns the attachment store after exact positive image-capability proof.
 */
async function resolveImageAdmission(ctx: Context, exec: ToolExecution): Promise<AttachmentStore> {
  const attachments = ctx.get('attachments')
  if (attachments === undefined) throw new Error('no attachment store is mounted')
  const routed = exec.agent?.session.requestHeader()?.config
  const provider = routed?.provider ?? exec.agent?.options.provider
  const model = routed?.model ?? exec.agent?.options.model
  const llm = ctx.get('llm')
  if (provider === undefined || model === undefined || llm === undefined) {
    throw new Error('the current model route could not be resolved')
  }
  let info: Awaited<ReturnType<typeof llm.resolveModelInfo>>
  try {
    info = await llm.resolveModelInfo(provider, model, exec.signal)
  } catch {
    throw new Error('the current model route could not be verified')
  }
  if (info.inputModalities === undefined || !info.inputModalities.includes('image')) {
    throw new Error(`model "${model}" does not declare image input`)
  }
  if (exec.signal.aborted) throw new Error('the tool call was canceled before image storage')
  return attachments
}

/** Stable diagnostic text for an image block that was not admitted. */
function imageDiagnostic(block: McpContentBlock, reason: string): string {
  const mediaType = block.mimeType ?? 'unknown media type'
  return `[image unavailable: ${mediaType}; ${reason}; raw image data remains available to programmatic callers]`
}

/**
 * Decode, preflight, and durably save one MCP result's ordered image batch.
 * Any refusal projects every image as text while retaining the canonical raw
 * value for programmatic callers.
 */
async function prepareImageProjection(
  ctx: Context,
  exec: ToolExecution,
  content: JsonValue[],
  toolName: string,
): Promise<ContentBlock[]> {
  const decoded: SaveImageAttachment[] = []
  const validationErrors = new Map<number, string>()
  const imageIndexes: number[] = []
  for (const [index, value] of content.entries()) {
    if (!isRecord(value) || value.type !== 'image') continue
    imageIndexes.push(index)
    try {
      decoded.push(decodeImage(value as unknown as ImageContent))
    } catch (error: unknown) {
      // decodeImage owns every throw above and always produces Error.
      validationErrors.set(index, (error as Error).message)
    }
  }
  if (validationErrors.size > 0) {
    return projectContent(content, toolName, (block, index) => ({
      type: 'text',
      text: imageDiagnostic(
        block,
        validationErrors.get(index) ?? 'another image in the same result was invalid',
      ),
    }))
  }

  let attachments: AttachmentStore
  try {
    attachments = await resolveImageAdmission(ctx, exec)
  } catch (error: unknown) {
    // resolveImageAdmission contains provider failures and throws Error only.
    const reason = (error as Error).message
    return projectContent(content, toolName, block => ({ type: 'text', text: imageDiagnostic(block, reason) }))
  }

  try {
    const refs = await attachments.saveImages(decoded)
    const byIndex = new Map(imageIndexes.map((index, offset) => [index, refs[offset] as ImageAttachmentRef] as const))
    return projectContent(content, toolName, (_block, index) => ({
      type: 'image',
      attachment: byIndex.get(index) as ImageAttachmentRef,
    }))
  } catch (error: unknown) {
    const reason = isImageAdmissionError(error)
      ? `image admission rejected the result: ${error.message}`
      : 'durable image storage rejected the result'
    return projectContent(content, toolName, block => ({
      type: 'text',
      text: imageDiagnostic(block, reason),
    }))
  }
}

/**
 * Extract text from an MCP content array into a single string.
 * - text blocks: join with '\n'
 * - image/audio/resource blocks: replaced with a placeholder
 *
 * Policy-owned canonical-value replacements may omit fields required on the MCP wire.
 */
function extractText(mcpContent: JsonValue[], toolName: string): string {
  const content = projectContent(mcpContent, toolName)
  // The default image projector below also returns text, so this local call
  // cannot produce a core image block.
  return content.map(block => (block as Extract<ContentBlock, { type: 'text' }>).text).join('\n')
}

/**
 * Project ordered MCP blocks into the core content vocabulary.
 * Text-like runs are newline-coalesced; admitted images split those runs at
 * their original position.
 */
function projectContent(
  mcpContent: JsonValue[],
  toolName: string,
  image: (block: McpContentBlock, index: number) => ContentBlock = block => ({
    type: 'text',
    text: imageDiagnostic(block, 'this result was not admitted to durable model context'),
  }),
): ContentBlock[] {
  const projected: ContentBlock[] = []
  const text: string[] = []
  const flushText = (): void => {
    if (text.length === 0) return
    projected.push({ type: 'text', text: text.splice(0).join('\n') })
  }

  for (const [index, value] of mcpContent.entries()) {
    if (!isRecord(value)) {
      text.push('[unsupported MCP content block: expected an object]')
      continue
    }
    const block = value as unknown as McpContentBlock
    switch (block.type) {
      case 'text':
        if (block.text !== undefined) text.push(block.text)
        break
      case 'image':
        flushText()
        projected.push(image(block, index))
        break
      case 'resource_link':
        if (block.name === undefined || block.uri === undefined) {
          text.push('[resource link unavailable: the MCP block is missing its name or URI]')
        } else {
          text.push(`Resource link: ${block.name} (${block.uri})`)
        }
        break
      case 'audio':
        text.push(`[audio result unsupported: ${block.mimeType ?? 'unknown media type'}; raw audio data remains available to programmatic callers]`)
        break
      case 'resource':
        text.push('[embedded resource unsupported; raw resource data remains available to programmatic callers]')
        break
      default:
        text.push(`[unsupported MCP content type: ${block.type}]`)
    }
  }
  flushText()
  return projected.length > 0
    ? projected
    : [{ type: 'text', text: `(${toolName} returned no model-visible content)` }]
}
