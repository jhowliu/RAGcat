import assert from 'node:assert/strict'
import { test } from 'node:test'
import { AuthClient, AuthError } from '../src/auth/client.ts'

const USER = { name: 'mochi', email: 'mochi@example.test' }

function setup({ development = false } = {}) {
  const values = new Map<string, string>()
  const requests: { url: string; body: Record<string, string> }[] = []
  let time = 1_000_000
  let session: Record<string, unknown> = { access_token: 'access1', refresh_token: 'refresh1', expires_in: 3600, token_type: 'Bearer', user: USER }
  let status = 200
  let refusal: { code: string; message: string } | null = null
  let refreshBarrier: { arrived: () => void; released: Promise<void> } | null = null
  const client = new AuthClient({
    development, devUser: () => 'tester', now: () => time,
    storage: { getItem: (key) => values.get(key) ?? null, setItem: (key, value) => { values.set(key, value) }, removeItem: (key) => { values.delete(key) } },
    fetch: async (input, init) => {
      const url = String(input)
      requests.push({ url, body: JSON.parse(String(init?.body ?? '{}')) })
      if (url === '/v1/auth/refresh' && refreshBarrier) {
        refreshBarrier.arrived()
        await refreshBarrier.released
      }
      if (url === '/v1/auth/logout') return new Response(null, { status: 204 })
      if (refusal) return Response.json({ error: { ...refusal, details: {} } }, { status })
      const { refresh_token, user, ...renewed } = session
      return Response.json(url === '/v1/auth/refresh' ? renewed : { ...renewed, refresh_token, user }, { status })
    },
  })
  const holdRefresh = () => {
    let arrived: () => void = () => undefined
    let release: () => void = () => undefined
    const started = new Promise<void>((resolve) => { arrived = resolve })
    const released = new Promise<void>((resolve) => { release = resolve })
    refreshBarrier = { arrived, released }
    return { started, release }
  }
  return {
    client, values, requests, holdRefresh,
    advance: (ms: number) => { time += ms },
    nextSession: (changes: Record<string, unknown>) => { session = { ...session, ...changes } },
    refuse: (code: string, httpStatus: number) => { refusal = { code, message: code }; status = httpStatus },
    setStatus: (value: number) => { status = value },
  }
}

test('local development uses the dev token and never calls the sign-in API', async () => {
  const { client, requests } = setup({ development: true })
  assert.deepEqual(await client.authHeader(), { Authorization: 'Bearer dev:tester' })
  assert.deepEqual(client.getState(), { status: 'signed-in', mode: 'dev', name: 'tester', email: null })
  assert.equal(requests.length, 0)
})

test('development builds sign out, stay signed out on reload, and sign back in as any name', async () => {
  const values = new Map<string, string>()
  const storage = { getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => { values.set(key, value) }, removeItem: (key: string) => { values.delete(key) } }
  let devName = 'tester'
  const make = () => new AuthClient({
    development: true, storage, devUser: () => devName, setDevUser: (name) => { devName = name },
    fetch: async () => { throw new Error('development builds never call the sign-in API') },
  })
  const client = make()
  await client.signOut()
  assert.deepEqual(client.getState(), { status: 'signed-out', reason: 'logout' })
  await assert.rejects(client.authHeader(), /Sign in to continue/)
  const reloaded = make()
  await reloaded.start()
  assert.equal(reloaded.getState().status, 'signed-out')
  await reloaded.signIn('mochi@example.test', 'anything')
  assert.deepEqual(reloaded.getState(), { status: 'signed-in', mode: 'dev', name: 'mochi', email: null })
  assert.deepEqual(await reloaded.authHeader(), { Authorization: 'Bearer dev:mochi' })
})

test('production does not authorize a signed-out user', async () => {
  const { client } = setup()
  await assert.rejects(client.authHeader(), /Sign in to continue/)
  assert.deepEqual(client.getState(), { status: 'signed-out', reason: 'initial' })
})

test('sign-in posts the credentials once and then uses the access token', async () => {
  const env = setup()
  await env.client.signIn('mochi@example.test', 'Secret#123')
  assert.deepEqual(env.requests, [{ url: '/v1/auth/login', body: { email: 'mochi@example.test', password: 'Secret#123' } }])
  assert.deepEqual(await env.client.authHeader(), { Authorization: 'Bearer access1' })
  assert.deepEqual(env.client.getState(), { status: 'signed-in', mode: 'cognito', name: 'mochi', email: 'mochi@example.test' })
  const stored = JSON.parse(env.values.get('ragcat-session')!)
  assert.equal(stored.refreshToken, 'refresh1')
  assert.equal('password' in stored, false)
})

test('sign-up waits for the emailed code: verifying it is a separate call, then sign-in starts the session', async () => {
  const env = setup()
  await env.client.signUp('mochi@example.test', 'Secret#123')
  assert.equal(env.client.getState().status, 'signed-out')
  await env.client.verifyEmail('mochi@example.test', '123456')
  await env.client.resendCode('mochi@example.test')
  assert.equal(env.client.getState().status, 'signed-out')
  assert.equal(env.values.has('ragcat-session'), false)
  await env.client.signIn('mochi@example.test', 'Secret#123')
  assert.deepEqual(env.requests.map((r) => r.url), ['/v1/auth/signup', '/v1/auth/verify-email', '/v1/auth/resend-code', '/v1/auth/login'])
  assert.deepEqual(env.requests[1]?.body, { email: 'mochi@example.test', code: '123456' })
  assert.equal(env.client.getState().status, 'signed-in')
})

test('a password reset posts the code and new password but leaves signing in to the caller', async () => {
  const env = setup()
  await env.client.forgotPassword('mochi@example.test')
  await env.client.resetPassword('mochi@example.test', '654321', 'Newer#456')
  assert.deepEqual(env.requests, [
    { url: '/v1/auth/forgot-password', body: { email: 'mochi@example.test' } },
    { url: '/v1/auth/reset-password', body: { email: 'mochi@example.test', code: '654321', password: 'Newer#456' } },
  ])
  assert.equal(env.values.has('ragcat-session'), false)
})

test('an unverified account and a wrong code surface their reason codes', async () => {
  const env = setup()
  env.refuse('EMAIL_NOT_VERIFIED', 403)
  await assert.rejects(env.client.signIn('mochi@example.test', 'Secret#123'), (error: unknown) => error instanceof AuthError && error.code === 'EMAIL_NOT_VERIFIED')
  env.refuse('INVALID_CODE', 400)
  await assert.rejects(env.client.verifyEmail('mochi@example.test', '000000'), (error: unknown) => error instanceof AuthError && error.code === 'INVALID_CODE')
  assert.equal(env.client.getState().status, 'signed-out')
})

test('development builds have no codes: sign-up signs straight in and code calls stay local', async () => {
  const { client, requests } = setup({ development: true })
  await client.signOut()
  await client.signUp('mochi@example.test', 'anything')
  assert.deepEqual(client.getState(), { status: 'signed-in', mode: 'dev', name: 'mochi', email: null })
  await client.forgotPassword('mochi@example.test')
  await client.resetPassword('mochi@example.test', '000000', 'anything')
  assert.equal(requests.length, 0)
})

test('a refused sign-in keeps the owner signed out and exposes the reason code', async () => {
  const env = setup()
  env.refuse('INVALID_CREDENTIALS', 401)
  await assert.rejects(env.client.signIn('mochi@example.test', 'wrong'), (error: unknown) => error instanceof AuthError && error.code === 'INVALID_CREDENTIALS')
  assert.equal(env.values.has('ragcat-session'), false)
  assert.equal(env.client.getState().status, 'signed-out')
})

test('a session survives a reload of the tab', async () => {
  const first = setup()
  await first.client.signIn('mochi@example.test', 'Secret#123')
  const reloaded = new AuthClient({
    development: false, devUser: () => 'tester', now: () => 1_000_000, fetch: async () => Response.json({}),
    storage: { getItem: (key) => first.values.get(key) ?? null, setItem: () => undefined, removeItem: () => undefined },
  })
  await reloaded.start()
  assert.deepEqual(await reloaded.authHeader(), { Authorization: 'Bearer access1' })
})

test('parallel API requests share one refresh and keep the refresh token', async () => {
  const env = setup()
  await env.client.signIn('mochi@example.test', 'Secret#123')
  env.advance(3590_000)
  env.nextSession({ access_token: 'access2' })
  const headers = await Promise.all([env.client.authHeader(), env.client.authHeader(), env.client.authHeader()])
  assert.ok(headers.every((h) => h.Authorization === 'Bearer access2'))
  const refreshes = env.requests.filter((r) => r.url === '/v1/auth/refresh')
  assert.deepEqual(refreshes.map((r) => r.body), [{ refresh_token: 'refresh1' }])
  assert.equal(JSON.parse(env.values.get('ragcat-session')!).refreshToken, 'refresh1')
  assert.deepEqual(env.client.getState(), { status: 'signed-in', mode: 'cognito', name: 'mochi', email: 'mochi@example.test' })
})

test('an expired refresh clears the session and does not reuse the old token', async () => {
  const env = setup()
  await env.client.signIn('mochi@example.test', 'Secret#123')
  env.advance(3590_000)
  env.refuse('SESSION_EXPIRED', 401)
  await assert.rejects(env.client.authHeader(), /could not be renewed/)
  assert.equal(env.values.has('ragcat-session'), false)
  assert.deepEqual(env.client.getState(), { status: 'signed-out', reason: 'expired' })
})

test('malformed token responses cannot create a session', async () => {
  const env = setup()
  env.nextSession({ access_token: '' })
  await assert.rejects(env.client.signIn('mochi@example.test', 'Secret#123'), /Invalid sign-in response/)
  assert.equal(env.values.has('ragcat-session'), false)
})

test('sign-out forgets the tokens and asks the API to revoke the refresh token', async () => {
  const env = setup()
  await env.client.signIn('mochi@example.test', 'Secret#123')
  await env.client.signOut()
  assert.equal(env.values.has('ragcat-session'), false)
  assert.deepEqual(env.client.getState(), { status: 'signed-out', reason: 'logout' })
  assert.deepEqual(env.requests.at(-1), { url: '/v1/auth/logout', body: { refresh_token: 'refresh1' } })
})

test('a refresh already in progress cannot restore credentials after sign-out', async () => {
  const env = setup()
  await env.client.signIn('mochi@example.test', 'Secret#123')
  env.advance(3590_000)
  const barrier = env.holdRefresh()
  const refreshing = env.client.authHeader()
  const rejected = assert.rejects(refreshing, /Sign in to continue/)
  await barrier.started
  await env.client.signOut()
  barrier.release()
  await rejected
  assert.equal(env.values.has('ragcat-session'), false)
  assert.equal(env.client.getState().status, 'signed-out')
})
