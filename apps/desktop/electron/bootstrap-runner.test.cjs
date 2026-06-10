const assert = require('node:assert/strict')

const test = require('node:test')



const { runBootstrap } = require('./bootstrap-runner.cjs')



test('runBootstrap bails immediately when the signal is already aborted', async () => {

  const controller = new AbortController()

  controller.abort()



  const events = []

  const result = await runBootstrap({

    installStamp: null,

    activeRoot: '/tmp/clawk-runner-test',

    sourceRepoRoot: null,

    clawkHome: '/tmp/clawk-runner-test',

    logRoot: '/tmp/clawk-runner-test',

    onEvent: ev => events.push(ev),

    abortSignal: controller.signal

  })



  // Cancelled before any install script is spawned.

  assert.deepEqual(result, { ok: false, cancelled: true })

  assert.ok(

    events.some(ev => ev.type === 'failed' && /cancelled/i.test(ev.error)),

    'should emit a cancelled failure event'

  )

})

