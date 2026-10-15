import assert from 'node:assert/strict'
import { test } from 'node:test'
import { MAX_ORIGINS, addOrigin, embedSnippet, parseOrigin } from '../src/widget/origins.ts'

test('keeps only the origin of whatever the owner pastes', () => {
  assert.deepEqual(parseOrigin('mochipet.example'), { ok: true, origin: 'https://mochipet.example' })
  assert.deepEqual(parseOrigin('  HTTPS://Shop.Mochipet.example/returns?x=1  '), { ok: true, origin: 'https://shop.mochipet.example' })
  assert.deepEqual(parseOrigin('https://mochipet.example:8443/'), { ok: true, origin: 'https://mochipet.example:8443' })
})

test('allows http only on this machine', () => {
  assert.deepEqual(parseOrigin('http://localhost:5173/widget-demo.html'), { ok: true, origin: 'http://localhost:5173' })
  assert.deepEqual(parseOrigin('localhost:5173'), { ok: true, origin: 'http://localhost:5173' })
  assert.deepEqual(parseOrigin('http://mochipet.example'), { ok: false, error: 'insecure' })
})

test('rejects what is not one website', () => {
  assert.deepEqual(parseOrigin(''), { ok: false, error: 'empty' })
  assert.deepEqual(parseOrigin('*.mochipet.example'), { ok: false, error: 'wildcard' })
  assert.deepEqual(parseOrigin('mochipet'), { ok: false, error: 'invalid' })
  assert.deepEqual(parseOrigin('ftp://mochipet.example'), { ok: false, error: 'invalid' })
  assert.deepEqual(parseOrigin('not a site'), { ok: false, error: 'invalid' })
})

test('adds without duplicates, up to the limit', () => {
  assert.deepEqual(addOrigin(['https://mochipet.example'], 'mochipet.example/shop'), { ok: false, error: 'duplicate' })
  const full = Array.from({ length: MAX_ORIGINS }, (_, i) => `https://s${i}.example`)
  assert.deepEqual(addOrigin(full, 'new.example'), { ok: false, error: 'limit' })
  assert.deepEqual(addOrigin([], 'new.example'), { ok: true, origins: ['https://new.example'], origin: 'https://new.example' })
})

test('the embed line names the loader and the Assistant', () => {
  assert.equal(embedSnippet('https://ragcat.example', 'ast_1'), '<script src="https://ragcat.example/widget.js" data-assistant="ast_1" async></script>')
})
