import { describe, expect, it } from 'vitest'
import { BlockAssembler, ToolCallId, type StreamChunk } from '@deepseek-ai/dsh-llm'

/**
 * C2b streamed tool-call args proof on the real chain3 fragments (session
 * 87444f2d, huoshan-1/glm-5.3-flash): step-2 seq 1081-1115 (two parallel
 * `cordis_inspect_query`, indexes 2/3) and step-3 seq 2412-2438 (index 4,
 * nested-object input). The arrays below are the recorded fragment streams,
 * extracted losslessly from the packed `tool-call-chunks` rows plus the
 * standalone head/tail `assistant/chunk` deltas by
 * `.agents/devframe/v14-llmargs/tools/extract-streamargs.mjs`: the provider
 * shattered tokens (`"list"+"Service"`, `"Built"+"ins"`) and the nested input
 * arrived as a stringified JSON body. 02251fac16 closed the aggregation
 * hazard where a provider multiplexing both calls onto one index spliced the
 * fragments into unparseable JSON under an overwritten id.
 */
const SERVICE_CALL_ID = 'call_66f4702be29f4dcdb3dba636'
const BUILTIN_CALL_ID = 'call_98480ff041f94b02a4cdef1c'
const TOOL_NAME = 'cordis_inspect_query'

const serviceFragments = [
  '{"', 'method', '":"', 'list', 'Service', '"', ',"', 'platform', '":"', 'host', '"', ',"',
  'provider', '":"', 'Service', '"', '}',
]
const builtinFragments = [
  '{"', 'method', '":"', 'list', 'Built', 'ins', '"', ',"', 'platform', '":"', 'host', '"', ',"',
  'provider', '":"', 'Builtin"', '}',
]
const serviceArguments = '{"method":"listService","platform":"host","provider":"Service"}'
const builtinArguments = '{"method":"listBuiltins","platform":"host","provider":"Builtin"}'

function callDelta(index: number, id: string, fragment: string): StreamChunk {
  return { type: 'tool-call-delta', index, id: ToolCallId(id), name: TOOL_NAME, argumentsDelta: fragment }
}

/**
 * The pre-02251fac16 `tool-call-delta` aggregation, replicated from the
 * pre-fix source: unconditional id overwrite and unconditional fragment
 * concatenation, regardless of which call a fragment belongs to.
 */
interface OldPartial {
  id: string | undefined
  name?: string
  arguments: string
}
function oldAggregate(deltas: readonly StreamChunk[]): Map<number, OldPartial> {
  const partials = new Map<number, OldPartial>()
  for (const chunk of deltas) {
    if (chunk.type !== 'tool-call-delta') continue
    const partial = partials.get(chunk.index) ?? { id: undefined, arguments: '' }
    partial.id = chunk.id
    if (chunk.name) partial.name = chunk.name
    partial.arguments += chunk.argumentsDelta
    partials.set(chunk.index, partial)
  }
  return partials
}

/** Both calls' fragments multiplexed onto one index, interleaved in stream order. */
function multiplexedOnOneIndex(): StreamChunk[] {
  return serviceFragments.flatMap((fragment, position) => [
    callDelta(2, SERVICE_CALL_ID, fragment),
    callDelta(2, BUILTIN_CALL_ID, builtinFragments[position] as string),
  ])
}

describe('BlockAssembler chain3 streamargs: pre-fix aggregation reproduces the corruption', () => {
  it('splices index-reused parallel calls into unparseable JSON under an overwritten id', () => {
    const partial = oldAggregate(multiplexedOnOneIndex()).get(2)
    expect(partial?.id).toBe(BUILTIN_CALL_ID)
    // The very first fragments already splice: both calls open their object.
    const spliced = partial?.arguments ?? ''
    expect(spliced.startsWith('{"{"')).toBe(true)
    expect(() => { JSON.parse(spliced) }).toThrow()
  })

  it('also corrupts sequential index reuse: two complete calls concatenated into one argument string', () => {
    const sequential = [
      ...serviceFragments.map(fragment => callDelta(2, SERVICE_CALL_ID, fragment)),
      ...builtinFragments.map(fragment => callDelta(2, BUILTIN_CALL_ID, fragment)),
    ]
    const partial = oldAggregate(sequential).get(2)
    expect(partial?.id).toBe(BUILTIN_CALL_ID)
    const spliced = partial?.arguments ?? ''
    expect(spliced).toBe(serviceArguments + builtinArguments)
    expect(() => { JSON.parse(spliced) }).toThrow()
  })

  it('lets a trailing id-less continuation delta erase the recorded call id', () => {
    // Fragments 0-15 stream the call under its real id; the stream ends with an
    // id-less delta carrying the final fragment — the pre-fix overwrite leaves
    // no id, so assembly falls back to the fabricated `call-{index}` identity.
    const withTrailingIdlessDelta = [
      ...serviceFragments.slice(0, 16).map(fragment => callDelta(2, SERVICE_CALL_ID, fragment)),
      { type: 'tool-call-delta', index: 2, argumentsDelta: serviceFragments[16] as string } as StreamChunk,
    ]
    const partial = oldAggregate(withTrailingIdlessDelta).get(2)
    expect(partial?.id).toBeUndefined()
    expect(partial?.arguments).toBe(serviceArguments)
  })
})

describe('BlockAssembler chain3 streamargs: current assembler resolves the same sample', () => {
  it('keeps the owning call intact and reports the dropped index-reused fragments', () => {
    const assembler = new BlockAssembler()
    for (const chunk of multiplexedOnOneIndex()) assembler.push(chunk)
    expect(assembler.blocks()).toEqual([
      { type: 'tool-call', id: ToolCallId(SERVICE_CALL_ID), name: TOOL_NAME, arguments: serviceArguments },
    ])
    const [call] = assembler.blocks()
    expect(JSON.parse((call as { arguments: string }).arguments)).toEqual({ method: 'listService', platform: 'host', provider: 'Service' })
    expect(assembler.indexConflicts).toEqual(
      builtinFragments.map(() =>
        `index 2: id ${BUILTIN_CALL_ID} fragment dropped; call ${SERVICE_CALL_ID} already owns this index`,
      ),
    )
  })

  it('assembles the recorded stream (distinct indexes) with both calls intact and no conflicts', () => {
    const recorded = [
      ...serviceFragments.map(fragment => callDelta(2, SERVICE_CALL_ID, fragment)),
      ...builtinFragments.map(fragment => callDelta(3, BUILTIN_CALL_ID, fragment)),
    ]
    const assembler = new BlockAssembler()
    for (const chunk of recorded) assembler.push(chunk)
    expect(assembler.blocks()).toEqual([
      { type: 'tool-call', id: ToolCallId(SERVICE_CALL_ID), name: TOOL_NAME, arguments: serviceArguments },
      { type: 'tool-call', id: ToolCallId(BUILTIN_CALL_ID), name: TOOL_NAME, arguments: builtinArguments },
    ])
    expect(assembler.indexConflicts).toEqual([])
  })

  it('keeps the recorded call id across a trailing id-less continuation delta', () => {
    const withTrailingIdlessDelta = [
      ...serviceFragments.slice(0, 16).map(fragment => callDelta(2, SERVICE_CALL_ID, fragment)),
      { type: 'tool-call-delta', index: 2, argumentsDelta: serviceFragments[16] as string } as StreamChunk,
    ]
    const assembler = new BlockAssembler()
    for (const chunk of withTrailingIdlessDelta) assembler.push(chunk)
    expect(assembler.blocks()).toEqual([
      { type: 'tool-call', id: ToolCallId(SERVICE_CALL_ID), name: TOOL_NAME, arguments: serviceArguments },
    ])
    expect(assembler.indexConflicts).toEqual([])
  })

  it('passes the recorded escaped fragments through verbatim', () => {
    // Real turn-1 step-3 index-4 stream (seq 2412-2438): the model emitted the
    // nested input as a stringified JSON string. The assembler must neither
    // strip nor inject escapes; the fail-loud "input must be an object"
    // rejection downstream is the tool's correct behavior against that shape.
    const escapedCallId = 'call_939d19c2f5f64dab8bf6722d'
    const escapedFragments = [
      '{"', 'input', '":"', '{\\"', 'service', '\\":', ' \\"', 'sub', 'agents', '\\"}', '"', ',"',
      'method', '":"', 'list', 'Service', '"', ',"', 'platform', '":"', 'host', '"', ',"',
      'provider', '":"', 'Service"', '}',
    ]
    const assembler = new BlockAssembler()
    for (const fragment of escapedFragments) assembler.push(callDelta(4, escapedCallId, fragment))
    const [call] = assembler.blocks()
    expect(call).toEqual({
      type: 'tool-call',
      id: ToolCallId(escapedCallId),
      name: TOOL_NAME,
      arguments: '{"input":"{\\"service\\": \\"subagents\\"}","method":"listService","platform":"host","provider":"Service"}',
    })
    const parsed = JSON.parse((call as { arguments: string }).arguments) as { input: string }
    expect(parsed.input).toBe('{"service": "subagents"}')
    expect(assembler.indexConflicts).toEqual([])
  })
})
