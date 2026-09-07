/**
 * AT4-05 请求预算记账 — the project-level cumulative model-request budget.
 *
 * 断言面：预算内 charge 通过并返回收据；恰好装满最后一个预算位的 charge 被
 * 准入；超限 charge 以稳定错误码拒绝且记账不变；配置值改变可准入次数
 * （含 schemastery 默认与 fail-loud 校验）。竞速：并发 charge 在满预算下恰
 * 好一个成功；重启：已计费用量跨进程恢复、不重置（P06 记账面）。
 *
 * @module tests/at4-05-request-budget
 */

import { expect, describe, it, vi } from 'vitest'
import { harness } from './helpers.ts'

describe('AT4-05 request budget accounting', () => {
  it('keeps charging closed after an uncertain write and restores persisted usage on reload', async () => {
    const first = await harness({ requestBudget: 3 })
    const root = first.root
    try {
      first.ctx.projectController.startProject()
      const domain = first.ctx.storageDomain.get('project_tasks')!
      const originalSet = domain.global.set.bind(domain.global)
      const write = vi.spyOn(domain.global, 'set').mockImplementationOnce(async (value) => {
        await originalSet(value)
        throw new Error('acknowledgement lost after durable write')
      })
      try {
        const results = await Promise.allSettled([
          first.ctx.projectController.chargeModelRequest(),
          first.ctx.projectController.chargeModelRequest(),
        ])
        for (const result of results) {
          expect(result.status).toBe('rejected')
          if (result.status === 'rejected') {
            expect(result.reason).toMatchObject({ code: 'PROJECT_CONTROLLER_PERSISTENCE' })
          }
        }
        expect(write).toHaveBeenCalledTimes(1)
      } finally {
        write.mockRestore()
      }
    } finally {
      await first.dispose({ keepRoot: true })
    }
    const second = await harness({ requestBudget: 3 }, root)
    try {
      second.ctx.projectController.startProject()
      expect(second.ctx.projectController.requestBudgetUsage().chargedRequests).toBe(1)
      await expect(second.ctx.projectController.chargeModelRequest()).resolves.toMatchObject({ chargedRequests: 2 })
    } finally {
      await second.dispose()
    }
  })

  it('rejects an expired host authority guard before charging without latching storage failure', async () => {
    const h = await harness({ requestBudget: 2 })
    try {
      h.ctx.projectController.startProject()
      await expect(h.ctx.projectController.chargeModelRequest({
        beforePersist() { throw new Error('authority revoked') },
      })).rejects.toThrow('authority revoked')
      expect(h.ctx.projectController.requestBudgetUsage().chargedRequests).toBe(0)
      await expect(h.ctx.projectController.chargeModelRequest()).resolves.toMatchObject({ chargedRequests: 1 })
    } finally {
      await h.dispose()
    }
  })

  it('admits charges within the budget and returns cumulative receipts', async () => {
    const h = await harness({ requestBudget: 3 })
    try {
      const controller = h.ctx.projectController
      expect(controller.startProject()).toBe('admission_open')

      await expect(controller.chargeModelRequest()).resolves.toEqual({
        chargedRequests: 1,
        requestBudget: 3,
        remainingRequests: 2,
      })
      await expect(controller.chargeModelRequest()).resolves.toEqual({
        chargedRequests: 2,
        requestBudget: 3,
        remainingRequests: 1,
      })
      expect(controller.requestBudgetUsage()).toEqual({
        requestBudget: 3,
        chargedRequests: 2,
        remainingRequests: 1,
      })
    } finally {
      await h.dispose()
    }
  })

  it('admits the charge that fills the last budget slot and rejects every further charge', async () => {
    const h = await harness({ requestBudget: 1 })
    try {
      const controller = h.ctx.projectController
      expect(controller.startProject()).toBe('admission_open')

      // Reaching the cap is admitted: the budget bounds further charging.
      await expect(controller.chargeModelRequest()).resolves.toEqual({
        chargedRequests: 1,
        requestBudget: 1,
        remainingRequests: 0,
      })

      await expect(controller.chargeModelRequest()).rejects.toMatchObject({
        code: 'PROJECT_CONTROLLER_REQUEST_BUDGET_EXHAUSTED',
        message: 'the request budget of 1 is exhausted (1 charged)',
      })
      expect(controller.requestBudgetUsage()).toEqual({
        requestBudget: 1,
        chargedRequests: 1,
        remainingRequests: 0,
      })
    } finally {
      await h.dispose()
    }
  })

  it('admits exactly one of two racing charges at a full budget', async () => {
    const h = await harness({ requestBudget: 1 })
    try {
      const controller = h.ctx.projectController
      expect(controller.startProject()).toBe('admission_open')

      const settled = await Promise.allSettled([
        controller.chargeModelRequest(),
        controller.chargeModelRequest(),
      ])
      const fulfilled = settled.filter(result => result.status === 'fulfilled')
      const rejected = settled.filter(
        result => result.status === 'rejected'
          && (result.reason as { code?: string }).code === 'PROJECT_CONTROLLER_REQUEST_BUDGET_EXHAUSTED',
      )
      expect(fulfilled).toHaveLength(1)
      expect(rejected).toHaveLength(1)
      if (fulfilled[0]?.status !== 'fulfilled') throw new Error('racing charges: expected one fulfilled receipt')
      expect(fulfilled[0].value).toEqual({
        chargedRequests: 1,
        requestBudget: 1,
        remainingRequests: 0,
      })
      expect(controller.requestBudgetUsage()).toMatchObject({ chargedRequests: 1 })
    } finally {
      await h.dispose()
    }
  })

  it('rejects a charge while project admission is closed', async () => {
    const h = await harness({ requestBudget: 3 })
    try {
      // A fresh process starts stopped: charging model work is dispatch-path.
      await expect(h.ctx.projectController.chargeModelRequest()).rejects.toMatchObject({
        code: 'PROJECT_CONTROLLER_ADMISSION_CLOSED',
      })
      expect(h.ctx.projectController.requestBudgetUsage()).toMatchObject({ chargedRequests: 0 })
    } finally {
      await h.dispose()
    }
  })

  it('applies the configured budget: default 1 and an explicit higher budget', async () => {
    const hDefault = await harness()
    try {
      const controller = hDefault.ctx.projectController
      expect(controller.startProject()).toBe('admission_open')
      await expect(controller.chargeModelRequest()).resolves.toMatchObject({
        requestBudget: 1,
        chargedRequests: 1,
      })
      await expect(controller.chargeModelRequest()).rejects.toMatchObject({
        code: 'PROJECT_CONTROLLER_REQUEST_BUDGET_EXHAUSTED',
      })
    } finally {
      await hDefault.dispose()
    }

    const hRaised = await harness({ requestBudget: 3 })
    try {
      const controller = hRaised.ctx.projectController
      expect(controller.startProject()).toBe('admission_open')
      for (const chargedRequests of [1, 2, 3]) {
        await expect(controller.chargeModelRequest()).resolves.toMatchObject({ chargedRequests })
      }
      await expect(controller.chargeModelRequest()).rejects.toMatchObject({
        code: 'PROJECT_CONTROLLER_REQUEST_BUDGET_EXHAUSTED',
      })
    } finally {
      await hRaised.dispose()
    }
  })

  it('fails loud on a budget outside its serviceable range', async () => {
    for (const requestBudget of [0, -1, 1.5]) {
      await expect(harness({ requestBudget })).rejects.toMatchObject({
        code: 'PROJECT_CONTROLLER_INVALID_CONFIG',
      })
    }
  })

  it('keeps charged usage across a process restart instead of resetting it', async () => {
    const first = await harness({ requestBudget: 2 })
    const root = first.root
    try {
      first.ctx.projectController.startProject()
      await expect(first.ctx.projectController.chargeModelRequest()).resolves.toMatchObject({ chargedRequests: 1 })
    } finally {
      await first.dispose({ keepRoot: true })
    }

    const second = await harness({ requestBudget: 2 }, root)
    try {
      const controller = second.ctx.projectController
      // Usage is restored before the host re-opens admission.
      expect(controller.requestBudgetUsage()).toEqual({
        requestBudget: 2,
        chargedRequests: 1,
        remainingRequests: 1,
      })
      expect(controller.startProject()).toBe('admission_open')
      await expect(controller.chargeModelRequest()).resolves.toMatchObject({ chargedRequests: 2 })
      await expect(controller.chargeModelRequest()).rejects.toMatchObject({
        code: 'PROJECT_CONTROLLER_REQUEST_BUDGET_EXHAUSTED',
      })
    } finally {
      await second.dispose({ keepRoot: true })
    }
  })
})
