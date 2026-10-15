// P01 Landing: explain the product and lead to the first upload. The hero shows the product at work,
// a Discord answer beside the page it cites, because every answer cites.
import { useState } from 'react'
import { Link } from 'react-router'
import { Cat } from '../components/Cat'
import { Icon, LanguageSwitch, Mark, Segmented, type IconName } from '../components/ui'
import { useDocumentTitle } from '../hooks'
import { useI18n, type Key } from '../i18n'

const PLANS: { id: 'free' | 'starter' | 'growth'; monthly: number; rows: Key[]; primary?: boolean }[] = [
  { id: 'free', monthly: 0, rows: ['land.plan.free.r1', 'land.plan.free.r2', 'land.plan.free.r3', 'land.plan.free.r4'], primary: true },
  { id: 'starter', monthly: 19, rows: ['land.plan.starter.r1', 'land.plan.starter.r2', 'land.plan.starter.r3'] },
  { id: 'growth', monthly: 49, rows: ['land.plan.growth.r1', 'land.plan.growth.r2', 'land.plan.growth.r3'] },
]
const STEPS: [Key, Key][] = [
  ['land.step1.title', 'land.step1.body'],
  ['land.step2.title', 'land.step2.body'],
  ['land.step3.title', 'land.step3.body'],
  ['land.step4.title', 'land.step4.body'],
]
const ACCURACY: [IconName, Key, Key][] = [
  ['book', 'land.trust.published.title', 'land.trust.published.body'],
  ['quote', 'land.trust.sources.title', 'land.trust.sources.body'],
  ['person', 'land.trust.declines.title', 'land.trust.declines.body'],
]
const PRIVACY: [IconName, Key, Key][] = [
  ['lock', 'land.trust.storage.title', 'land.trust.storage.body'],
  ['link', 'land.trust.links.title', 'land.trust.links.body'],
  ['trash', 'land.trust.delete.title', 'land.trust.delete.body'],
]

export function LandingPage() {
  const { t } = useI18n()
  const [billing, setBilling] = useState<'monthly' | 'annual'>('monthly')
  useDocumentTitle(null)

  return (
    <div className="landing">
      <header className="land-header">
        <div className="wrap">
          <a href="#top" className="brand">
            <Mark size={28} />
            RAGcat
          </a>
          <nav className="landnav" aria-label={t('land.nav.label')}>
            <a href="#product" className="landlink">
              {t('land.nav.product')}
            </a>
            <a href="#how" className="landlink">
              {t('land.nav.how')}
            </a>
            <a href="#trust" className="landlink">
              {t('land.nav.trust')}
            </a>
            <a href="#pricing" className="landlink">
              {t('land.nav.pricing')}
            </a>
          </nav>
          <div className="header-right">
            <LanguageSwitch />
            <Link to="/assistants" className="landlink signin">
              {t('land.signIn')}
            </Link>
            <Link to="/assistants/new" className="btn btn-dark small">
              {t('land.startFree')}
            </Link>
          </div>
        </div>
      </header>

      <main>
        <section id="top" className="hero-section">
          <div className="wrap hero">
            <h1 className="display hero-title">
              {t('land.hero.title1')}
              <br />
              {t('land.hero.title2')}
            </h1>
            <p className="hero-lead">{t('land.hero.lead')}</p>
            <div className="cta-row">
              <Link to="/assistants/new" className="btn btn-dark lg">
                <Icon name="up" size={18} stroke={2} />
                {t('land.hero.upload')}
              </Link>
              <a href="#product" className="btn btn-line lg">
                {t('land.hero.see')}
              </a>
            </div>
            <p className="fine">{t('land.hero.fine')}</p>
          </div>
          <div className="wrap">
            <div className="stage">
              <ProductFrame />
            </div>
          </div>
        </section>

        <section id="how" className="land-section alt">
          <div className="wrap section-stack">
            <div className="section-head">
              <h2 className="display h2">{t('land.how.title')}</h2>
              <p className="lead">{t('land.how.lead')}</p>
            </div>
            <ol className="steps">
              {STEPS.map(([title, body], i) => (
                <li key={title}>
                  <span className="step-num mono" aria-hidden="true">
                    {i + 1}
                  </span>
                  <h3 className="display">{t(title)}</h3>
                  <p>{t(body)}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section id="product" className="land-section">
          <div className="wrap feature">
            <div className="feature-copy">
              <h2 className="display h2">{t('land.review.title')}</h2>
              <p className="lead">{t('land.review.lead')}</p>
              <ul className="checklist">
                {(['land.review.c1', 'land.review.c2', 'land.review.c3'] as Key[]).map((k) => (
                  <li key={k}>
                    <span className="check" aria-hidden="true">
                      <Icon name="check" size={14} stroke={2.4} />
                    </span>
                    <span>{t(k)}</span>
                  </li>
                ))}
              </ul>
            </div>
            <ReviewMock />
          </div>
        </section>

        <section id="trust" className="land-section alt">
          <div className="wrap section-stack">
            <div className="section-head">
              <h2 className="display h2">{t('land.trust.title')}</h2>
            </div>
            <div className="trust">
              {(
                [
                  ['land.trust.accuracy', ACCURACY],
                  ['land.trust.privacy', PRIVACY],
                ] as [Key, [IconName, Key, Key][]][]
              ).map(([heading, items]) => (
                <div key={heading} className="trust-col">
                  <h3 className="display title">{t(heading)}</h3>
                  <ul>
                    {items.map(([icon, title, body]) => (
                      <li key={title} className="trust-item">
                        <span className="tile" aria-hidden="true">
                          <Icon name={icon} size={18} />
                        </span>
                        <div>
                          <h4>{t(title)}</h4>
                          <p>{t(body)}</p>
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section id="pricing" className="land-section">
          <div className="wrap section-stack">
            <div className="pricing-head">
              <div className="section-head">
                <h2 className="display h2">{t('land.pricing.title')}</h2>
              </div>
              <div className="quota">
                <Segmented
                  label={t('land.pricing.period')}
                  value={billing}
                  onChange={setBilling}
                  options={[
                    { value: 'monthly', label: t('land.pricing.monthly') },
                    { value: 'annual', label: t('land.pricing.annual') },
                  ]}
                />
                <span className="hint">{t('land.pricing.annualNote')}</span>
              </div>
            </div>
            <div className="plans">
              {PLANS.map((p) => (
                <article key={p.id} className={`panel plan ${p.primary ? 'primary' : ''}`}>
                  <div className="plan-head">
                    <h3 className="display plan-name">{t(`land.plan.${p.id}.name` as Key)}</h3>
                    <span className="page-lead">{t(`land.plan.${p.id}.blurb` as Key)}</span>
                  </div>
                  <div className="price-row">
                    <span className="display price">${billing === 'annual' ? p.monthly * 10 : p.monthly}</span>
                    {p.monthly > 0 && <span className="hint">{billing === 'annual' ? t('land.pricing.perYear') : t('land.pricing.perMonth')}</span>}
                  </div>
                  <ul>
                    {p.rows.map((r) => (
                      <li key={r}>
                        <Icon name="check" size={16} stroke={2.2} />
                        <span>{t(r)}</span>
                      </li>
                    ))}
                  </ul>
                  <Link to="/assistants/new" className={`btn ${p.primary ? 'btn-dark' : 'btn-line'}`}>
                    {t(`land.plan.${p.id}.cta` as Key)}
                  </Link>
                </article>
              ))}
            </div>
            <p className="fine">{t('land.pricing.note')}</p>
          </div>
        </section>

        <section className="closing-band">
          <div className="wrap closing">
            <Cat pose="cheer" size={132} className="closing-cat" />
            <div className="closing-copy">
              <h2 className="display closing-title">{t('land.closing.title')}</h2>
              <p>{t('land.closing.body')}</p>
            </div>
            <Link to="/assistants/new" className="btn btn-dark lg">
              <Icon name="up" size={18} stroke={2} />
              {t('land.startFree')}
            </Link>
          </div>
        </section>
      </main>

      <footer className="land-footer">
        <div className="wrap">
          <span className="brand small">
            <Mark size={22} />
            RAGcat
          </span>
          <span>© 2026 RAGcat</span>
        </div>
      </footer>
    </div>
  )
}

/** The product at work: a Discord answer beside the page it cites. Hovering or focusing the [1] marker
 *  sweeps the highlight across the cited sentence, the citation motion used across RAGcat. */
function ProductFrame() {
  const { t } = useI18n()
  const [sweep, setSweep] = useState(0)
  const replay = () => setSweep((n) => n + 1)
  return (
    <figure className="frame" aria-label={t('land.scene.label')}>
      <div className="frame-bar">
        <span className="frame-dots" aria-hidden="true">
          <i />
          <i />
          <i />
        </span>
        <span className="frame-title">{t('steps.review')}</span>
        <span className="mono frame-file">{t('land.scene.file')}</span>
      </div>
      <div className="frame-body">
        <div className="frame-src">
          <div className="frame-head">
            <span>{t('review.source')}</span>
            <span className="mono">{t('land.scene.page')}</span>
          </div>
          <div className="frame-sheet">
            <p className="frame-sheet-heading">{t('land.scene.heading')}</p>
            <p>{t('land.scene.p1')}</p>
            <p className="cited">
              {t('land.scene.p2a')}
              <mark className="cite sweep" key={sweep}>
                {t('land.scene.p2b')}
              </mark>
              {t('land.scene.p2c')}
              <span className="fn after" aria-hidden="true">
                1
              </span>
              {/* The cat leans in from the chat side and points back at the sentence it cited. */}
              <Cat pose="point" size={144} eager className="hero-cat" />
            </p>
            <div className="frame-lines" aria-hidden="true">
              <span style={{ width: '94%' }} />
              <span style={{ width: '88%' }} />
              <span style={{ width: '64%' }} />
            </div>
          </div>
        </div>
        <div className="frame-chat">
          <div className="frame-head">
            <span className="mono frame-channel"># help-desk</span>
            <span>Discord</span>
          </div>
          <div className="chat-msg">
            <span className="chat-avatar" aria-hidden="true">
              <Icon name="person" size={16} />
            </span>
            <div className="chat-copy">
              <span className="chat-who">{t('land.scene.customer')}</span>
              <span className="chat-text">{t('land.scene.question')}</span>
            </div>
          </div>
          <div className="chat-msg">
            <span className="chat-avatar bot" aria-hidden="true">
              <Mark size={24} />
            </span>
            <div className="chat-copy">
              <span className="chat-who">RAGcat</span>
              <span className="chat-text">
                {t('land.scene.answer')}
                <button type="button" className="fn after" aria-label={t('land.scene.showSource')} onMouseEnter={replay} onFocus={replay} onClick={replay}>
                  1
                </button>
              </span>
              <div className="cite-row">
                <span className="row tight">
                  <span className="fn">1</span>
                  <span className="mono">{t('land.scene.cite')}</span>
                </span>
                <span className="with-dot">
                  <span className="dot success" aria-hidden="true" />
                  {t('land.scene.grounded')}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </figure>
  )
}

function ReviewMock() {
  const { t } = useI18n()
  return (
    <div className="frame mock" role="img" aria-label={t('land.mock.label')}>
      <div className="frame-bar">
        <span className="frame-dots" aria-hidden="true">
          <i />
          <i />
          <i />
        </span>
        <span className="mock-seg">
          <span>{t('land.mock.passages')}</span>
          <span>{t('review.test')}</span>
        </span>
        <span className="with-dot hint">
          <span className="dot success" aria-hidden="true" />
          {t('land.mock.saved')}
        </span>
      </div>
      <div className="pane2">
        <div className="mock-src">
          <div className="mock-page">
            <span className="mono mock-pg">{t('land.scene.page')}</span>
            <span className="mock-heading">{t('land.scene.heading')}</span>
            <span>{t('land.scene.p1')}</span>
            <span className="picked">{t('land.mock.picked')}</span>
            <span className="mock-line" style={{ width: '90%' }} />
            <span className="mock-line" style={{ width: '74%' }} />
            <span className="mock-line" style={{ width: '84%' }} />
          </div>
        </div>
        <div className="mock-cards">
          <div className="mock-card">
            <div className="row between">
              <span className="id">{t('land.mock.id13')}</span>
              <span className="chip chip-warn">{t('land.mock.headingOnly')}</span>
            </div>
            <span className="mock-strong">{t('land.scene.heading')}</span>
            <span className="mock-chip-line">{t('review.mergeNext')}</span>
          </div>
          <div className="mock-card picked">
            <div className="row between">
              <span className="id">{t('land.mock.id14')}</span>
              <span className="chip chip-info">{t('review.editedChip')}</span>
            </div>
            <span>{t('land.mock.p14')}</span>
          </div>
          <div className="mock-card">
            <div className="row between">
              <span className="id">{t('land.mock.id15')}</span>
              <span className="chip chip-warn">{t('land.mock.multiple')}</span>
            </div>
            <span>
              {t('land.mock.p15a')}
              <span className="mock-split">{t('review.splitHere')}</span>
              {t('land.mock.p15b')}
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
