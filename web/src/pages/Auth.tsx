import { useState, type FormEvent } from 'react'
import { Link, Outlet, useLocation } from 'react-router'
import { auth, useAuth } from '../auth'
import { AuthError } from '../auth/client'
import { Field, LanguageSwitch, Mark } from '../components/ui'
import { useI18n, type Key } from '../i18n'

/** verify: the emailed code that confirms a new account. forgot → reset: the emailed code that sets a
 * new password. */
type Mode = 'signin' | 'signup' | 'verify' | 'forgot' | 'reset'

const REFUSALS: Record<string, Key> = {
  INVALID_CREDENTIALS: 'auth.error.credentials',
  EMAIL_EXISTS: 'auth.error.exists',
  INVALID_PASSWORD: 'auth.error.password',
  INVALID_INPUT: 'auth.error.input',
  VALIDATION_ERROR: 'auth.error.input',
  TOO_MANY_ATTEMPTS: 'auth.error.attempts',
  RATE_LIMITED: 'auth.error.emails',
  INVALID_CODE: 'auth.error.code',
  CODE_EXPIRED: 'auth.error.codeExpired',
  EMAIL_NOT_SENT: 'auth.error.notSent',
}

const TITLES: Record<Mode, Key> = {
  signin: 'auth.title',
  signup: 'auth.signUpTitle',
  verify: 'auth.verifyTitle',
  forgot: 'auth.forgotTitle',
  reset: 'auth.resetTitle',
}

const SUBMITS: Record<Mode, [idle: Key, busy: Key]> = {
  signin: ['auth.signIn', 'auth.loading'],
  signup: ['auth.createAccount', 'auth.creating'],
  verify: ['auth.verify', 'auth.verifying'],
  forgot: ['auth.sendCode', 'auth.sending'],
  reset: ['auth.resetPassword', 'auth.saving'],
}

/** RAGcat's own sign-in page: email and password, a new account confirmed by an emailed code, or a
 * password reset. Signing in re-renders the page the owner asked for, so there is no redirect to come
 * back from. */
function AuthScreen({ expired = false }: { expired?: boolean }) {
  const { t } = useI18n()
  const location = useLocation()
  // "Start free" lands on /assistants/new: a new owner most likely needs an account.
  const [mode, setMode] = useState<Mode>(location.pathname === '/assistants/new' ? 'signup' : 'signin')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Key | null>(null)
  const [notice, setNotice] = useState<Key | null>(null)
  const signup = mode === 'signup'
  const withCode = mode === 'verify' || mode === 'reset'

  function go(next: Mode, message: Key | null = null) {
    setMode(next)
    setCode('')
    setError(null)
    setNotice(message)
    // A reset asks for a new password; verifying keeps the sign-up password to sign in with.
    if (next === 'reset' || next === 'forgot') setPassword('')
  }

  /** An unverified account: send a fresh code, since the first one may be gone or expired. A refused
   * resend still leaves the code field, for a code that already arrived. */
  async function toVerify() {
    go('verify')
    await auth.resendCode(email)
  }

  async function step() {
    switch (mode) {
      case 'signin':
        try {
          await auth.signIn(email, password)
        } catch (err) {
          if (!(err instanceof AuthError && err.code === 'EMAIL_NOT_VERIFIED')) throw err
          await toVerify()
        }
        return
      case 'signup':
        await auth.signUp(email, password)
        go('verify')
        return
      case 'verify':
        await auth.verifyEmail(email, code.trim())
        if (password) await auth.signIn(email, password)
        else go('signin', 'auth.verified')
        return
      case 'forgot':
        try {
          await auth.forgotPassword(email)
          go('reset')
        } catch (err) {
          if (!(err instanceof AuthError && err.code === 'EMAIL_NOT_VERIFIED')) throw err
          await toVerify()
        }
        return
      case 'reset':
        await auth.resetPassword(email, code.trim(), password)
        await auth.signIn(email, password)
    }
  }

  function refused(err: unknown) {
    if (err instanceof AuthError && err.code === 'ALREADY_VERIFIED') go('signin', 'auth.verified')
    else setError(err instanceof AuthError ? REFUSALS[err.code] ?? 'auth.error.unavailable' : 'auth.error.unavailable')
  }

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      await step()
    } catch (err) {
      refused(err)
    }
    setBusy(false)
  }

  async function resend() {
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      await (mode === 'reset' ? auth.forgotPassword(email) : auth.resendCode(email))
      setNotice('auth.resent')
    } catch (err) {
      refused(err)
    }
    setBusy(false)
  }

  const body = withCode
    ? t(mode === 'verify' ? 'auth.verifyBody' : 'auth.resetBody', { email: email.trim() })
    : t(mode === 'signin' ? (expired ? 'auth.expired' : 'auth.body') : mode === 'signup' ? 'auth.signUpBody' : 'auth.forgotBody')
  const codeRefused = error === 'auth.error.code' || error === 'auth.error.codeExpired'

  return (
    <main className="wrap empty-state auth-screen">
      <div className="auth-lang">
        <LanguageSwitch />
      </div>
      <Mark size={44} />
      <h1 className="display title">{t(TITLES[mode])}</h1>
      <p role={expired && mode === 'signin' ? 'status' : undefined}>{body}</p>
      <form className="panel auth-form" onSubmit={submit} aria-label={t(TITLES[mode])}>
        {!withCode && (
          <Field id="auth-email" label={t('auth.email')}>
            <input
              id="auth-email"
              className="input"
              type="email"
              autoComplete={signup ? 'email' : 'username'}
              required
              value={email}
              aria-invalid={error === 'auth.error.credentials' || error === 'auth.error.exists' || undefined}
              onChange={(e) => setEmail(e.target.value)}
            />
          </Field>
        )}
        {withCode && (
          <Field id="auth-code" label={t('auth.code')}>
            <input
              id="auth-code"
              className="input"
              inputMode="numeric"
              autoComplete="one-time-code"
              required
              value={code}
              aria-invalid={codeRefused || undefined}
              onChange={(e) => setCode(e.target.value)}
            />
          </Field>
        )}
        {(mode === 'signin' || signup || mode === 'reset') && (
          <Field
            id="auth-password"
            label={t(mode === 'reset' ? 'auth.newPassword' : 'auth.password')}
            {...(mode === 'signin' ? {} : { hint: t('auth.passwordRule') })}
          >
            <input
              id="auth-password"
              className="input"
              type="password"
              autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
              required
              minLength={mode === 'signin' ? undefined : 8}
              value={password}
              aria-invalid={error === 'auth.error.credentials' || error === 'auth.error.password' || undefined}
              onChange={(e) => setPassword(e.target.value)}
            />
          </Field>
        )}
        {import.meta.env.DEV && (mode === 'signin' || signup) && <p className="hint">{t('auth.devHint')}</p>}
        {notice && (
          <p className="hint" role="status">
            {t(notice)}
          </p>
        )}
        {error && (
          <p className="field-error" role="alert">
            {t(error)}
          </p>
        )}
        <button type="submit" className="btn btn-dark" disabled={busy}>
          {t(SUBMITS[mode][busy ? 1 : 0])}
        </button>
      </form>
      {withCode && (
        <p>
          {t('auth.noCode')}{' '}
          <button type="button" className="btn-text" disabled={busy} onClick={resend}>
            {t('auth.resend')}
          </button>
        </p>
      )}
      {mode === 'signin' && (
        <p>
          <button type="button" className="btn-text" onClick={() => go('forgot')}>
            {t('auth.forgot')}
          </button>
        </p>
      )}
      {mode === 'signin' || signup ? (
        <p>
          {t(signup ? 'auth.haveAccount' : 'auth.noAccount')}{' '}
          <button type="button" className="btn-text" onClick={() => go(signup ? 'signin' : 'signup')}>
            {t(signup ? 'auth.toSignIn' : 'auth.toSignUp')}
          </button>
        </p>
      ) : (
        <p>
          <button type="button" className="btn-text" onClick={() => go('signin')}>
            {t('auth.backToSignIn')}
          </button>
        </p>
      )}
      <p>
        <Link to="/">{t('auth.home')}</Link>
      </p>
    </main>
  )
}

export function AuthGuard() {
  const state = useAuth()
  if (state.status === 'loading') return null
  if (state.status === 'signed-out') return <AuthScreen expired={state.reason === 'expired'} />
  return <Outlet />
}
