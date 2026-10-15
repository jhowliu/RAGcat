/** Email and password sign-in on RAGcat's own page. The API talks to Cognito; the tokens it returns
 * stay in this tab's session storage. Development builds use dev tokens: they start signed in, sign
 * out like production, and sign back in as the email's name with any password. */
export type AuthState =
  | { status: 'loading' }
  | { status: 'signed-out'; reason: 'initial' | 'expired' | 'logout' }
  | { status: 'signed-in'; mode: 'dev' | 'cognito'; name: string; email: string | null }

type Session = { accessToken: string; refreshToken: string | null; expiresAt: number; name: string; email: string | null }
type StoragePort = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>

export interface AuthOptions {
  development: boolean
  storage: StoragePort
  fetch: typeof fetch
  devUser: () => string
  setDevUser?: (name: string) => void
  now?: () => number
}

/** A sign-in or sign-up the API refused. `code` picks the message: INVALID_CREDENTIALS, EMAIL_EXISTS,
 * INVALID_PASSWORD, INVALID_INPUT, TOO_MANY_ATTEMPTS, or anything else for "unavailable". */
export class AuthError extends Error {
  readonly code: string

  constructor(code: string, message: string) {
    super(message)
    this.code = code
  }
}

const SESSION_KEY = 'ragcat-session'
const DEV_SIGNED_OUT = 'ragcat-dev-signed-out'
const EXPIRY_MARGIN = 60_000

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function readJson(storage: StoragePort, key: string): unknown {
  try {
    const raw = storage.getItem(key)
    return raw === null ? null : JSON.parse(raw)
  } catch {
    return null
  }
}

function isSession(value: unknown): value is Session {
  return record(value) && typeof value.accessToken === 'string' && value.accessToken.length > 0
    && (typeof value.refreshToken === 'string' || value.refreshToken === null)
    && typeof value.expiresAt === 'number' && Number.isFinite(value.expiresAt)
    && typeof value.name === 'string' && (typeof value.email === 'string' || value.email === null)
}

function refusal(body: unknown): AuthError {
  const error = record(body) ? body.error : null
  if (record(error) && typeof error.code === 'string') return new AuthError(error.code, typeof error.message === 'string' ? error.message : error.code)
  return new AuthError('UNAVAILABLE', 'Sign-in is unavailable')
}

export class AuthClient {
  private session: Session | null = null
  private state: AuthState = { status: 'loading' }
  private readonly listeners = new Set<() => void>()
  private startup: Promise<void> | null = null
  private refresh: Promise<void> | null = null
  private generation = 0
  private readonly options: AuthOptions

  constructor(options: AuthOptions) {
    this.options = options
  }

  getState = (): AuthState => this.state

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  private now(): number { return this.options.now?.() ?? Date.now() }

  private setState(state: AuthState): void {
    this.state = state
    this.listeners.forEach((listener) => listener())
  }

  start(): Promise<void> {
    this.startup ??= this.initialize()
    return this.startup
  }

  private async initialize(): Promise<void> {
    if (this.options.development) {
      // A dev sign-out lasts until the next dev sign-in, across reloads of this tab.
      if (this.options.storage.getItem(DEV_SIGNED_OUT)) this.setState({ status: 'signed-out', reason: 'initial' })
      else this.setState({ status: 'signed-in', mode: 'dev', name: this.options.devUser(), email: null })
      return
    }
    const stored = readJson(this.options.storage, SESSION_KEY)
    if (isSession(stored) && (stored.expiresAt > this.now() || stored.refreshToken)) {
      this.session = stored
      this.setState({ status: 'signed-in', mode: 'cognito', name: stored.name, email: stored.email })
    } else {
      this.options.storage.removeItem(SESSION_KEY)
      this.setState({ status: 'signed-out', reason: 'initial' })
    }
  }

  signIn(email: string, password: string): Promise<void> {
    return this.passwordAuth('/v1/auth/login', email, password)
  }

  /** Creates the account and signs in; RAGcat sends no verification email. */
  signUp(email: string, password: string): Promise<void> {
    return this.passwordAuth('/v1/auth/signup', email, password)
  }

  private async passwordAuth(path: string, email: string, password: string): Promise<void> {
    await this.start()
    if (this.options.development) {
      const name = email.trim().split('@')[0] || 'demo'
      this.options.setDevUser?.(name)
      this.options.storage.removeItem(DEV_SIGNED_OUT)
      this.setState({ status: 'signed-in', mode: 'dev', name, email: null })
      return
    }
    const response = await this.post(path, { email, password })
    const body: unknown = await response.json().catch(() => null)
    if (!response.ok) throw refusal(body)
    this.saveTokens(body)
  }

  private post(path: string, body: unknown): Promise<Response> {
    return this.options.fetch(path, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal: AbortSignal.timeout(15_000),
    })
  }

  private saveTokens(body: unknown): void {
    if (!record(body) || typeof body.access_token !== 'string' || !body.access_token
      || typeof body.expires_in !== 'number' || !Number.isFinite(body.expires_in) || body.expires_in <= 0
      || body.token_type !== 'Bearer') throw new AuthError('UNAVAILABLE', 'Invalid sign-in response')
    const user = record(body.user) && typeof body.user.name === 'string'
      ? { name: body.user.name, email: typeof body.user.email === 'string' ? body.user.email : null }
      : this.session ?? { name: 'Account', email: null }
    const session: Session = {
      accessToken: body.access_token,
      refreshToken: typeof body.refresh_token === 'string' ? body.refresh_token : this.session?.refreshToken ?? null,
      expiresAt: this.now() + body.expires_in * 1000, name: user.name, email: user.email,
    }
    this.options.storage.setItem(SESSION_KEY, JSON.stringify(session))
    this.session = session
    this.setState({ status: 'signed-in', mode: 'cognito', name: session.name, email: session.email })
  }

  async authHeader(): Promise<Record<string, string>> {
    await this.start()
    if (this.options.development) {
      if (this.state.status !== 'signed-in') throw new Error('Sign in to continue')
      return { Authorization: `Bearer dev:${this.options.devUser()}` }
    }
    if (!this.session) throw new Error('Sign in to continue')
    if (this.session.expiresAt <= this.now() + EXPIRY_MARGIN) {
      this.refresh ??= this.refreshSession().finally(() => { this.refresh = null })
      await this.refresh
    }
    if (!this.session || this.session.expiresAt <= this.now()) throw new Error('Sign in to continue')
    return { Authorization: `Bearer ${this.session.accessToken}` }
  }

  private clearSession(reason: 'expired' | 'logout'): void {
    this.generation++
    this.session = null
    this.options.storage.removeItem(SESSION_KEY)
    this.setState({ status: 'signed-out', reason })
  }

  private async refreshSession(): Promise<void> {
    const generation = this.generation
    const refreshToken = this.session?.refreshToken
    if (!refreshToken) {
      this.clearSession('expired')
      throw new Error('Your session expired. Sign in again.')
    }
    const response = await this.post('/v1/auth/refresh', { refresh_token: refreshToken })
    if (generation !== this.generation) throw new Error('Sign in to continue')
    if (!response.ok) {
      if (response.status === 400 || response.status === 401) this.clearSession('expired')
      throw new Error('Your session could not be renewed. Please retry or sign in again.')
    }
    const tokens: unknown = await response.json()
    if (generation !== this.generation) throw new Error('Sign in to continue')
    this.saveTokens(tokens)
  }

  /** Forgets the tokens at once, then asks the API to revoke the refresh token. */
  async signOut(): Promise<void> {
    const refreshToken = this.session?.refreshToken
    if (this.options.development) this.options.storage.setItem(DEV_SIGNED_OUT, '1')
    this.clearSession('logout')
    if (refreshToken) await this.post('/v1/auth/logout', { refresh_token: refreshToken }).catch(() => undefined)
  }
}
