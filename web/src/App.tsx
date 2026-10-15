import { useEffect } from 'react'
import { Route, Routes } from 'react-router'
import { auth } from './auth'
import { AppLayout } from './components/AppShell'
import { useI18n } from './i18n'
import { AssistantPage } from './pages/Assistant'
import { AssistantsPage } from './pages/Assistants'
import { LandingPage } from './pages/Landing'
import { PublishPage } from './pages/Publish'
import { ReviewPage } from './pages/Review'
import { SetupPage, UploadPage } from './pages/Setup'
import { AuthGuard } from './pages/Auth'

export default function App() {
  useEffect(() => { void auth.start().catch(() => undefined) }, [])
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route element={<AuthGuard />}>
        <Route element={<AppLayout />}>
          <Route path="/assistants" element={<AssistantsPage />} />
          <Route path="/assistants/new" element={<UploadPage />} />
          <Route path="/assistants/:aid" element={<AssistantPage />} />
          <Route path="/assistants/:aid/add" element={<UploadPage />} />
          <Route path="/assistants/:aid/setup" element={<SetupPage />} />
          <Route path="/assistants/:aid/review" element={<ReviewPage />} />
          <Route path="/assistants/:aid/publish" element={<PublishPage />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Route>
    </Routes>
  )
}

function NotFound() {
  const { t } = useI18n()
  return <p className="wrap empty">{t('common.notFound')}</p>
}
