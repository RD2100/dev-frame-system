import { describe, expect, it } from 'vitest'
import { classifyGitFailure } from '../src/git-failures.ts'

/** stderr texts captured from real git 2.53 refusals on Windows. */
const REAL_STDERR = {
  pathExists: "fatal: 'C:/repo/occupied' already exists",
  branchConflict: "fatal: a branch named 'wt1' already exists",
  dirtyTree:
    "fatal: 'C:\\repo\\wt1' contains modified or untracked files, use --force to delete it",
  pathLengthLong: "fatal: could not create leading directories of 'C:/repo/deep/.git': Filename too long",
  pathLengthGitDir: "fatal: '$GIT_DIR' too big",
} as const

describe('classifyGitFailure', () => {
  it('classifies the four observed refusal dialects', () => {
    expect(classifyGitFailure(REAL_STDERR.pathExists)).toBe('path-exists')
    expect(classifyGitFailure(REAL_STDERR.branchConflict)).toBe('branch-conflict')
    expect(classifyGitFailure(REAL_STDERR.dirtyTree)).toBe('dirty-tree')
    expect(classifyGitFailure(REAL_STDERR.pathLengthLong)).toBe('path-length')
    expect(classifyGitFailure(REAL_STDERR.pathLengthGitDir)).toBe('path-length')
  })

  it('classifies the branch conflict before the generic already-exists refusal', () => {
    // Both dialects contain "already exists"; the specific one wins.
    expect(classifyGitFailure(`x ${REAL_STDERR.branchConflict} y`)).toBe('branch-conflict')
  })

  it('classifies case-insensitively across git dialect drift', () => {
    expect(classifyGitFailure(REAL_STDERR.dirtyTree.toUpperCase())).toBe('dirty-tree')
    expect(classifyGitFailure('FATAL: a branch named \'X\' ALREADY EXISTS')).toBe('branch-conflict')
  })

  it('leaves unknown refusals unclassified', () => {
    expect(classifyGitFailure('fatal: not a git repository (or any of the parent directories): .git')).toBeUndefined()
    expect(classifyGitFailure('')).toBeUndefined()
  })
})
