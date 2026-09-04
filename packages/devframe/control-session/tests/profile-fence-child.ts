import { acquireProfileHostFence } from '../src/profile-fence.ts'

const home = process.argv[2]
if (home === undefined) throw new Error('missing profile-host fence home')

const fence = await acquireProfileHostFence(home)
process.send?.({ type: 'ready', pid: process.pid })

process.on('message', (message: unknown) => {
  if (message !== 'release') return
  void fence.release().then(
    () => {
      process.send?.({ type: 'released' })
      process.exit(0)
    },
    (failure: unknown) => {
      process.stderr.write(`${failure instanceof Error ? failure.stack ?? failure.message : String(failure)}\n`)
      process.exit(1)
    },
  )
})

setInterval(() => {}, 60_000)
