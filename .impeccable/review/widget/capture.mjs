// Captures the Website widget prototype and its owner setup screens. Read-only against the backend:
// the setup list is the prototype's browser-local list, and nothing is published.
import { createRequire } from 'node:module'
const require = createRequire('/Users/jhowliu/.npm/_npx/e41f203b7505f1fb/node_modules/')
const { chromium } = require('playwright')

const BASE = 'http://localhost:5173'
const OUT = new URL('.', import.meta.url).pathname
const LIVE = 'ast_01M4D9T2KA0GY0HWCX9ZBB8CZ4'
const DRAFT = 'ast_01M4DAH8WY16QEFRRVN05JTKJV'

const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' })
const shot = (page, name) => page.screenshot({ path: `${OUT}${name}.png` })

async function demo(viewport, query = '') {
  const ctx = await browser.newContext({ viewport, deviceScaleFactor: 2, reducedMotion: 'reduce' })
  const page = await ctx.newPage()
  await page.goto(`${BASE}/widget-demo.html${query}`)
  await page.waitForSelector('[data-ragcat-widget]', { state: 'attached' })
  await page.waitForTimeout(400)
  return { ctx, page }
}
const launcher = (page) => page.locator('[data-ragcat-widget] >> css=.launcher')
const frame = (page) => page.frameLocator('[data-ragcat-widget] >> css=iframe')
async function ask(page, q) {
  const f = frame(page)
  await f.locator('#w-question').fill(q)
  await f.locator('button[type=submit]').click()
}
async function settle(page) {
  await page.waitForTimeout(150)
  await frame(page).locator('button[type=submit]').waitFor()
  for (let i = 0; i < 60; i++) {
    const busy = await frame(page).locator('.cursor, [role=status]:has-text("…")').count()
    if (!busy) break
    await page.waitForTimeout(100)
  }
  await page.waitForTimeout(250)
}

// desktop: closed, empty, answered (with the [1] sweep), no answer, error, rate limited
{
  const { ctx, page } = await demo({ width: 1440, height: 900 })
  await shot(page, 'd1-closed')
  await launcher(page).click()
  await frame(page).locator('.w-empty').waitFor()
  await page.waitForTimeout(500)
  await shot(page, 'd2-empty')
  await ask(page, 'Can I return an opened bag of kibble?')
  await settle(page)
  await frame(page).locator('button.fn').first().hover()
  await page.waitForTimeout(500)
  await shot(page, 'd3-answer')
  await ask(page, 'Do you sell bird seed?')
  await settle(page)
  await shot(page, 'd4-no-answer')
  await ask(page, '/error')
  await settle(page)
  await shot(page, 'd5-error')
  await ask(page, 'How much is shipping?')
  await settle(page)
  await ask(page, 'How long do opened bags stay fresh?')
  await page.waitForTimeout(500)
  await shot(page, 'd6-limited')
  await ctx.close()
}
// desktop: unavailable
{
  const { ctx, page } = await demo({ width: 1440, height: 900 }, '?aid=demo-off')
  await launcher(page).click()
  await frame(page).locator('.w-empty').waitFor()
  await page.waitForTimeout(400)
  await shot(page, 'd7-unavailable')
  await ctx.close()
}
// phone: closed, answered (zh)
{
  const { ctx, page } = await demo({ width: 390, height: 844 }, '?lang=zh')
  await shot(page, 'm1-closed')
  await launcher(page).click()
  await page.waitForTimeout(100)
  await shot(page, 'm2a-opening')
  await frame(page).locator('.w-empty').waitFor()
  await page.waitForTimeout(400)
  await shot(page, 'm2-empty-zh')
  await ask(page, '運費怎麼算？')
  await settle(page)
  await shot(page, 'm3-answer-zh')
  await ctx.close()
}
// owner setup in the app (dev sign-in, read-only)
for (const [viewport, tag] of [[{ width: 1440, height: 900 }, 'd'], [{ width: 390, height: 844 }, 'm']]) {
  const ctx = await browser.newContext({ viewport, deviceScaleFactor: 2, reducedMotion: 'reduce' })
  const page = await ctx.newPage()
  await page.goto(`${BASE}/assistants/${DRAFT}/publish`)
  await page.waitForSelector('text=Add to your website')
  await page.waitForTimeout(500)
  await page.screenshot({ path: `${OUT}${tag}8-publish-locked.png`, fullPage: true })
  await page.goto(`${BASE}/assistants/${LIVE}?tab=channels`)
  await page.waitForSelector('.origin-add')
  await page.waitForTimeout(400)
  await page.screenshot({ path: `${OUT}${tag}9-channels-empty.png`, fullPage: true })
  await page.fill('.origin-add input', 'mochipet.example/shop')
  await page.click('.origin-add button')
  await page.fill('.origin-add input', 'localhost:5173')
  await page.click('.origin-add button')
  await page.fill('.origin-add input', '*.mochipet.example')
  await page.click('.origin-add button')
  await page.waitForTimeout(300)
  await page.screenshot({ path: `${OUT}${tag}10-channels-sites.png`, fullPage: true })
  await ctx.close()
}
await browser.close()
console.log('captured')
