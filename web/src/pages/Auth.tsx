import { useState, type FormEvent } from 'react'
import { Link, Outlet, useLocation } from 'react-router'
import { auth, useAuth } from '../auth'
import { AuthError } from '../auth/client'
import { Field, LanguageSwitch, Mark } from '../components/ui'
import { useI18n, type Key } from '../i18n'

type Mode = 'signin' | 'signup'

const REFUSALS: Record<string, Key> = {
  INVALID_CREDENTIALS: 'auth.error.credentials',
  EMAIL_EXISTS: 'auth.error.exists',
  INVALID_PASSWORD: 'auth.error.password',
  INVALID_INPUT: 'auth.error.input',
  VALIDATION_ERROR: 'auth.error.input',
  TOO_MANY_ATTEMPTS: 'auth.error.attempts',
}

/** RAGcat's own sign-in page: email and password, or a new account. Signing in re-renders the page
 * the owner asked for, so there is no redirect to come back from. */
function AuthScreen({ expired = false }: { expired?: boolean }) {
  const { t } = useI18n()
  const location = useLocation()
  // "Start free" lands on /assistants/new: a new owner most likely needs an account.
  const [mode, setMode] = useState<Mode>(location.pathname === '/assistants/new' ? 'signup' : 'signin')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Key | null>(null)
  const signup = mode === 'signup'

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await (signup ? auth.signUp(email, password) : auth.signIn(email, password))
    } catch (err) {
      setError(err instanceof AuthError ? REFUSALS[err.code] ?? 'auth.error.unavailable' : 'auth.error.unavailable')
      setBusy(false)
    }
  }

  function switchMode() {
    setMode(signup ? 'signin' : 'signup')
    setError(null)
  }

  return (
    <main className="wrap empty-state auth-screen">
      <div className="auth-lang">
        <LanguageSwitch />
      </div>
      <Mark size={44} />
      <h1 className="display title">{t(signup ? 'auth.signUpTitle' : 'auth.title')}</h1>
      <p role={expired && !signup ? 'status' : undefined}>{t(expired && !signup ? 'auth.expired' : signup ? 'auth.signUpBody' : 'auth.body')}</p>
      <form className="panel auth-form" onSubmit={submit} aria-label={t(signup ? 'auth.signUpTitle' : 'auth.title')}>
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
        <Field id="auth-password" label={t('auth.password')} {...(signup ? { hint: t('auth.passwordRule') } : {})}>
          <input
            id="auth-password"
            className="input"
            type="password"
            autoComplete={signup ? 'new-password' : 'current-password'}
            required
            minLength={signup ? 8 : undefined}
            value={password}
            aria-invalid={error === 'auth.error.credentials' || error === 'auth.error.password' || undefined}
            onChange={(e) => setPassword(e.target.value)}
          />
        </Field>
        {import.meta.env.DEV && <p className="hint">{t('auth.devHint')}</p>}
        {error && (
          <p className="field-error" role="alert">
            {t(error)}
          </p>
        )}
        <button type="submit" className="btn btn-dark" disabled={busy}>
          {t(busy ? (signup ? 'auth.creating' : 'auth.loading') : signup ? 'auth.createAccount' : 'auth.signIn')}
        </button>
      </form>
      <p>
        {t(signup ? 'auth.haveAccount' : 'auth.noAccount')}{' '}
        <button type="button" className="btn-text" onClick={switchMode}>
          {t(signup ? 'auth.toSignIn' : 'auth.toSignUp')}
        </button>
      </p>
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
