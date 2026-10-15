// Entry for the Website widget's frame page (docs/api-design.md §7). public/widget.js opens it in an
// iframe with ?lang=…; the api serves this page at /v1/widget/{aid}/frame with the Assistant's id,
// name and contact on #root and a frame-ancestors header listing the owner's sites. The dev demo
// opens widget.html directly with ?aid=demo…
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { I18nProvider } from '../i18n'
import { widgetConfig } from './ask'
import { WidgetApp } from './WidgetApp'
import '../styles.css'
import './widget.css'

const root = document.getElementById('root')!
const params = new URLSearchParams(location.search)
const aid = root.dataset.aid ?? params.get('aid') ?? ''

createRoot(root).render(
  <StrictMode>
    <I18nProvider initialLang={params.get('lang') === 'zh' ? 'zh' : 'en'}>
      <WidgetApp aid={aid} config={widgetConfig(aid, root)} />
    </I18nProvider>
  </StrictMode>,
)
