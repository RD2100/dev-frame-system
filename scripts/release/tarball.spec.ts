import { describe, expect, it, vi } from 'vitest'

const captureMock = vi.hoisted(() => vi.fn())

vi.mock('./process.ts', () => ({ capture: captureMock }))

import { tarballFiles } from './tarball.ts'

describe('tarball file listing', () => {
  it('normalizes Windows tar CRLF output before validating archive members', () => {
    captureMock.mockReturnValue('package/lib/index.js\r\npackage/package.json\r\n')

    expect(tarballFiles('desktop-host.tgz')).toEqual([
      'package/lib/index.js',
      'package/package.json',
    ])
  })
})
