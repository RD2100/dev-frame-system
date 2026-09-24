// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { makeTranslate } from '@deepseek-ai/dsh-client-test-runtime'
import type { ScheduleId, ScheduleRecord } from '@deepseek-ai/dsh-schedule/client'
import type { SessionId } from '@deepseek-ai/dsh-session/types'
import { ScheduleTaskCenter, type ScheduleTaskCenterProps } from '../src/client/ScheduleTaskCenter.tsx'
import { en } from '../src/client/locales.ts'

afterEach(cleanup)

const SESSION = 'schedule-task-session' as SessionId

const ACTIVE: ScheduleRecord = {
  id: 'schedule-1' as ScheduleId,
  kind: 'after',
  prompt: 'Send the report',
  scheduledAt: '2099-01-01T00:00:00.000Z',
  afterSeconds: 3_600,
}

function props(
  record: ScheduleRecord = ACTIVE,
  schedule: Partial<ScheduleTaskCenterProps['schedule']> = {},
): ScheduleTaskCenterProps {
  return {
    useSessions: select => select({
      ids: [SESSION],
      byId: {
        [SESSION]: { displayTitle: 'Project session', projectionValues: { schedule: [record], scheduleHistory: [] } },
      },
    } as never),
    schedule: {
      pause: async () => ({ ok: true, value: { id: ACTIVE.id, paused: true } }),
      resume: async () => ({ ok: true, value: { id: ACTIVE.id, resumed: true } }),
      run: async () => ({ ok: true, value: { id: ACTIVE.id, started: true } }),
      delete: async () => ({ ok: true, value: { id: ACTIVE.id, deleted: true } }),
      ...schedule,
    } as ScheduleTaskCenterProps['schedule'],
    t: makeTranslate(en),
  } as ScheduleTaskCenterProps
}

describe('ScheduleTaskCenter', () => {
  it('routes pause, run-now, and delete through the Schedule Remote', async () => {
    const pause = vi.fn<ScheduleTaskCenterProps['schedule']['pause']>().mockResolvedValue({ ok: true, value: { id: ACTIVE.id, paused: true } })
    const run = vi.fn<ScheduleTaskCenterProps['schedule']['run']>().mockResolvedValue({ ok: true, value: { id: ACTIVE.id, started: true } })
    const remove = vi.fn<ScheduleTaskCenterProps['schedule']['delete']>().mockResolvedValue({ ok: true, value: { id: ACTIVE.id, deleted: true } })
    render(<ScheduleTaskCenter {...props(ACTIVE, { pause, run, delete: remove })} />)

    fireEvent.click(screen.getByRole('button', { name: en['center.action.pause'] }))
    await waitFor(() => { expect(pause).toHaveBeenCalledWith({ sessionId: SESSION, id: ACTIVE.id }) })
    fireEvent.click(screen.getByRole('button', { name: en['center.action.run'] }))
    await waitFor(() => { expect(run).toHaveBeenCalledWith({ sessionId: SESSION, id: ACTIVE.id }) })
    fireEvent.click(screen.getByRole('button', { name: en['center.action.delete'] }))
    await waitFor(() => { expect(remove).toHaveBeenCalledWith({ sessionId: SESSION, id: ACTIVE.id }) })
  })

  it('shows resume for paused records and reports Remote failures without leaking details', async () => {
    const resume = vi.fn<ScheduleTaskCenterProps['schedule']['resume']>().mockResolvedValue({
      ok: false,
      error: { code: 'failed', message: 'private transport detail' },
    })
    render(<ScheduleTaskCenter {...props({ ...ACTIVE, paused: true }, { resume })} />)
    fireEvent.click(screen.getByRole('button', { name: en['center.action.resume'] }))
    expect((await screen.findByRole('alert')).textContent).toBe(en['center.actionError'])
    expect(screen.queryByText('private transport detail')).toBeNull()
    expect(resume).toHaveBeenCalledWith({ sessionId: SESSION, id: ACTIVE.id })
  })
})
