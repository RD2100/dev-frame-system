// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import type { SessionId } from '@deepseek-ai/dsh-session/types'
import { makeTranslate } from '@deepseek-ai/dsh-client-test-runtime'
import { zh as commonZh } from '@deepseek-ai/dsh-client-locale/src/locales/zh.ts'
import { AgentNodeItem } from '../src/client/rows/Rows.tsx'
import type { AgentNode } from '../src/client/tree.ts'
import { zh } from '../src/client/locales.ts'

afterEach(cleanup)

const t = makeTranslate(zh, commonZh) as never
const sid = (id: string) => id as SessionId

function agentNode(id: string, overrides: Partial<AgentNode> = {}): AgentNode {
  return {
    id: sid(id), title: `Title ${id}`, blank: false, running: false,
    runningSubagentCount: 0, completed: false, hasActiveSchedule: false, updatedAt: 0,
    children: [], ...overrides,
  }
}

interface Harness {
  expanded: Set<string>
  onToggle: (id: SessionId) => void
}

/** Render one agent row with a Set-backed expansion predicate. */
function renderAgent(node: AgentNode, harness: Harness, currentId: string | undefined = undefined): void {
  render(
    <AgentNodeItem
      node={node}
      depth={0}
      currentId={currentId}
      now={0}
      expandedOf={candidate => harness.expanded.has(candidate.id)}
      onToggle={harness.onToggle}
      onOpen={vi.fn()}
      onRename={vi.fn()}
      onFork={vi.fn()}
      onArchive={vi.fn()}
      t={t}
    />,
  )
}

describe('AgentNodeItem', () => {
  it('renders name, live status, durable Session ID, worktree, and progress on one row', () => {
    renderAgent(agentNode('lead', {
      title: 'DSH-G1-Lead', running: true, cwd: 'D:\\wt\\r3-g1', updatedAt: 60_000,
    }), { expanded: new Set(), onToggle: vi.fn() })

    expect(screen.getByText('DSH-G1-Lead')).toBeTruthy()
    // The live status dot plus its screen-reader label.
    expect(screen.getByRole('treeitem').querySelector('[data-state="ongoing"]')).toBeTruthy()
    expect(screen.getByText('进行中')).toBeTruthy()
    // Meta line: the full durable id and the bound working directory.
    const meta = document.querySelector('[class*="agentMeta"]') as HTMLElement
    expect(meta.textContent).toContain('lead')
    expect(meta.textContent).toContain('D:\\wt\\r3-g1')
    // Recent progress: the relative activity stamp.
    expect(screen.getByText('刚刚')).toBeTruthy()
  })

  it('renders no expand control and no aria-expanded for a childless agent', () => {
    renderAgent(agentNode('leaf'), { expanded: new Set(), onToggle: vi.fn() })
    const row = screen.getByRole('treeitem')
    expect(row.hasAttribute('aria-expanded')).toBe(false)
    expect(screen.queryByRole('button', { name: zh['agent.toggle.aria'].replace('{name}', 'Title leaf') })).toBeNull()
  })

  it('expands on the chevron only, one direct level, and collapses again', () => {
    const onToggle = vi.fn()
    const grandchild = agentNode('executor')
    const child = agentNode('lead', { children: [grandchild] })
    const root = agentNode('master', { children: [child] })
    const harness: Harness = { expanded: new Set(), onToggle }
    const { rerender } = render(
      <AgentNodeItem
        node={root} depth={0} currentId={undefined} now={0}
        expandedOf={candidate => harness.expanded.has(candidate.id)}
        onToggle={harness.onToggle}
        onOpen={vi.fn()} onRename={vi.fn()} onFork={vi.fn()} onArchive={vi.fn()} t={t}
      />,
    )
    // Collapsed: the child row is absent, the chevron reports closed.
    expect(screen.queryByText('Title lead')).toBeNull()
    const chevron = screen.getByRole('button', { name: '展开或收起“Title master”的直接下级' })
    expect(chevron.getAttribute('aria-expanded')).toBe('false')
    expect(screen.getByRole('treeitem').getAttribute('aria-expanded')).toBe('false')

    // The chevron toggles without navigating.
    fireEvent.click(chevron)
    expect(onToggle).toHaveBeenCalledWith(root.id)
    expect(onToggle).toHaveBeenCalledTimes(1)

    harness.expanded.add(root.id)
    rerender(
      <AgentNodeItem
        node={root} depth={0} currentId={undefined} now={0}
        expandedOf={candidate => harness.expanded.has(candidate.id)}
        onToggle={harness.onToggle}
        onOpen={vi.fn()} onRename={vi.fn()} onFork={vi.fn()} onArchive={vi.fn()} t={t}
      />,
    )
    // Expanded: exactly the direct level — the grandchild stays hidden while
    // its own parent is collapsed.
    expect(screen.getByText('Title lead')).toBeTruthy()
    expect(screen.queryByText('Title executor')).toBeNull()
    expect(screen.getByRole('group', { name: '下级 Agent' })).toBeTruthy()

    harness.expanded.add(child.id)
    rerender(
      <AgentNodeItem
        node={root} depth={0} currentId={undefined} now={0}
        expandedOf={candidate => harness.expanded.has(candidate.id)}
        onToggle={harness.onToggle}
        onOpen={vi.fn()} onRename={vi.fn()} onFork={vi.fn()} onArchive={vi.fn()} t={t}
      />,
    )
    expect(screen.getByText('Title executor')).toBeTruthy()

    // Collapse again: the whole level disappears.
    harness.expanded.delete(root.id)
    rerender(
      <AgentNodeItem
        node={root} depth={0} currentId={undefined} now={0}
        expandedOf={candidate => harness.expanded.has(candidate.id)}
        onToggle={harness.onToggle}
        onOpen={vi.fn()} onRename={vi.fn()} onFork={vi.fn()} onArchive={vi.fn()} t={t}
      />,
    )
    expect(screen.queryByText('Title lead')).toBeNull()
    expect(screen.queryByRole('group')).toBeNull()
  })

  it('row activation opens the Session and toggles children; childless rows only open', () => {
    const onOpen = vi.fn()
    const onToggle = vi.fn()
    const child = agentNode('lead')
    const root = agentNode('master', { children: [child] })
    render(
      <>
        <AgentNodeItem
          node={root} depth={0} currentId={undefined} now={0}
          expandedOf={() => false} onToggle={onToggle} onOpen={onOpen}
          onRename={vi.fn()} onFork={vi.fn()} onArchive={vi.fn()} t={t}
        />
        <AgentNodeItem
          node={child} depth={1} currentId={undefined} now={0}
          expandedOf={() => false} onToggle={onToggle} onOpen={onOpen}
          onRename={vi.fn()} onFork={vi.fn()} onArchive={vi.fn()} t={t}
        />
      </>,
    )
    fireEvent.click(screen.getByText('Title master'))
    expect(onOpen).toHaveBeenCalledWith(root.id)
    expect(onToggle).toHaveBeenCalledWith(root.id)
    fireEvent.click(screen.getByText('Title lead'))
    expect(onOpen).toHaveBeenCalledWith(child.id)
    // A childless activation never toggles.
    expect(onToggle).toHaveBeenCalledTimes(1)
  })

  it('opens the Session-ID dialog from the row menu with the full durable id', () => {
    const id = 'session-agent-0123456789abcdef0123456789abcdef'
    renderAgent(agentNode(id, { title: 'Lead row' }), { expanded: new Set(), onToggle: vi.fn() })
    fireEvent.click(screen.getByRole('button', { name: '会话“Lead row”的操作' }))
    fireEvent.click(screen.getByRole('menuitem', { name: zh['menu.sessionId'] }))
    const dialog = screen.getByRole('dialog')
    expect(dialog.textContent).toContain(id)
  })

  it('keeps the meta line for a title-less session to its worktree only (the id is the title)', () => {
    // title === id: the id is already the row's primary text, so the meta
    // line would only repeat it — it stays off entirely without a worktree.
    renderAgent(agentNode('0189abc', { title: '0189abc' }), { expanded: new Set(), onToggle: vi.fn() })
    expect(document.querySelector('[class*="agentMeta"]')).toBeNull()
    expect(screen.getByText('0189abc')).toBeTruthy()
  })

  it('renders a blank placeholder without meta line, progress, or row verbs', () => {
    renderAgent(agentNode('blank', { title: '', blank: true }), { expanded: new Set(), onToggle: vi.fn() })
    expect(screen.getByText('新会话')).toBeTruthy()
    expect(document.querySelector('[class*="agentMeta"]')).toBeNull()
    expect(screen.queryByRole('button', { name: /会话.*的操作/ })).toBeNull()
    expect(screen.queryByText('刚刚')).toBeNull()
  })

  it('marks the selected row and nests children one indentation level deeper', () => {
    const child = agentNode('lead')
    const root = agentNode('master', { children: [child] })
    render(
      <AgentNodeItem
        node={root} depth={0} currentId={root.id} now={0}
        expandedOf={() => true} onToggle={vi.fn()} onOpen={vi.fn()}
        onRename={vi.fn()} onFork={vi.fn()} onArchive={vi.fn()} t={t}
      />,
    )
    const rootRow = screen.getByRole('treeitem', { selected: true })
    expect(rootRow.className).toMatch(/selected/)
    const childRow = screen.getByRole('treeitem', { selected: false })
    expect(childRow.getAttribute('style')).toContain('14px')
  })
})
