/**
 * Per-tool-call timeout protection in ToolHandler.execute().
 *
 * Guards against a stalled or runaway tool execution (e.g. codegraph_explore
 * BFS on a huge / broken codebase) from hanging the MCP request indefinitely.
 */
import { describe, it, expect, afterEach, vi } from 'vitest';
import { ToolHandler } from '../src/mcp/tools';

const ENV = 'CODEGRAPH_TOOL_TIMEOUT_MS';

describe('ToolHandler execute timeout', () => {
  const original = process.env[ENV];
  afterEach(() => {
    if (original === undefined) delete process.env[ENV];
    else process.env[ENV] = original;
    vi.restoreAllMocks();
  });

  /**
   * Helper: a ToolHandler (no CodeGraph) that will throw when any handler
   * tries to call getCodeGraph(). We stub that out so we can control
   * exactly what the tool does.
   */
  function makeHandler(): ToolHandler {
    return new ToolHandler(null);
  }

  // ---------------------------------------------------------------
  // Test 1: A slow tool returns timeout error, does NOT hang
  // ---------------------------------------------------------------
  it('returns a timeout error when a tool exceeds the deadline', async () => {
    process.env[ENV] = '500'; // 500 ms timeout

    const handler = makeHandler();

    // Hook into executeCore to simulate a tool that hangs forever.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const originalCore = (handler as any).executeCore.bind(handler);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (handler as any).executeCore = vi.fn().mockImplementation(
      () => new Promise(() => {
        /* never resolves — simulates a hung BFS traversal */
      })
    );

    const start = Date.now();
    const result = await handler.execute('codegraph_explore', { query: 'x' });
    const elapsed = Date.now() - start;

    expect(result.isError).toBe(true);
    expect(result.content[0].text).toMatch(/timed out after \d+ seconds/);
    // Should complete near the 500ms deadline, not hang
    expect(elapsed).toBeGreaterThanOrEqual(400);
    expect(elapsed).toBeLessThan(2000); // generous upper bound for CI
  });

  // ---------------------------------------------------------------
  // Test 2: A fast tool completes normally, not affected
  // ---------------------------------------------------------------
  it('lets a fast (normal) tool complete normally', async () => {
    process.env[ENV] = '60000'; // 60s — way longer than this test

    const handler = makeHandler();

    // Stub executeCore to resolve quickly (simulate a normal fast tool)
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (handler as any).executeCore = vi.fn().mockResolvedValue({
      content: [{ type: 'text', text: 'OK' }],
      isError: false,
    });

    const result = await handler.execute('codegraph_search', { query: 'x' });

    expect(result.isError).toBe(false);
    expect(result.content[0].text).toBe('OK');
  });

  // ---------------------------------------------------------------
  // Test 3: Timeout value is configurable via CODEGRAPH_TOOL_TIMEOUT_MS
  // ---------------------------------------------------------------
  it('uses the timeout value from CODEGRAPH_TOOL_TIMEOUT_MS env var', async () => {
    // 200 ms timeout
    process.env[ENV] = '200';

    const handler = makeHandler();

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (handler as any).executeCore = vi.fn().mockImplementation(
      () => new Promise(() => {
        /* never resolves */
      })
    );

    const start = Date.now();
    const result = await handler.execute('codegraph_explore', { query: 'x' });
    const elapsed = Date.now() - start;

    expect(result.isError).toBe(true);
    expect(result.content[0].text).toMatch(/timed out after 0 seconds/);
    expect(elapsed).toBeGreaterThanOrEqual(150);
    expect(elapsed).toBeLessThan(1000);
  });

  // ---------------------------------------------------------------
  // Test 4: CODEGRAPH_TOOL_TIMEOUT_MS=0 disables the timeout
  // ---------------------------------------------------------------
  it('disables timeout when CODEGRAPH_TOOL_TIMEOUT_MS=0', async () => {
    process.env[ENV] = '0';

    const handler = makeHandler();

    // Should throw the usual "no CodeGraph project" error, not a timeout error
    const result = await handler.execute('codegraph_search', { query: 'x' });

    expect(result.content[0].text).toMatch(/No CodeGraph project is loaded/);
    expect(result.content[0].text).not.toMatch(/timed out/);
  });
});
