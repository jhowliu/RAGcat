import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { Doc } from '../src/api.ts'
import { needsPublish } from '../src/model.ts'

const BASE_DOCUMENT = {
  id: 'doc_ready',
  assistant_id: 'ast_test',
  filename: 'model-migration.pdf',
  size_bytes: 1024,
  page_count: 5,
  status: 'ready',
  progress: null,
  enabled: true,
  edit_version: 1,
  pending_changes: 14,
  warning_count: 0,
  error: null,
  last_embedded_at: '2026-10-14T00:00:00Z',
  created_at: '2026-10-14T00:00:00Z',
  updated_at: '2026-10-14T00:00:00Z',
} satisfies Doc

function document(overrides: Partial<Doc> = {}): Doc {
  return { ...BASE_DOCUMENT, ...overrides }
}

test('ready documents with pending model changes can be published again', () => {
  assert.equal(needsPublish(document()), true)
})

test('review documents with text edits remain publishable', () => {
  assert.equal(needsPublish(document({ status: 'review', pending_changes: 1 })), true)
})

for (const status of ['ready', 'review'] as const) {
  test(`paused ${status} documents are excluded from publishing`, () => {
    assert.equal(needsPublish(document({ status, enabled: false })), false)
  })

  test(`${status} documents without pending changes are excluded`, () => {
    assert.equal(needsPublish(document({ status, pending_changes: 0 })), false)
  })
}

const NON_PUBLISHABLE_STATUSES = [
  'awaiting_upload', 'parsing', 'embedding', 'failed', 'cancelled', 'deleting',
] as const satisfies readonly Doc['status'][]

for (const status of NON_PUBLISHABLE_STATUSES) {
  test(`${status} documents remain excluded even with pending changes`, () => {
    assert.equal(needsPublish(document({ status })), false)
  })
}

test('publish and draft Test selection include model migrations and edits without unsafe documents', () => {
  const documents = [
    document(),
    document({ id: 'doc_review', status: 'review', pending_changes: 1 }),
    document({ id: 'doc_unchanged', pending_changes: 0 }),
    document({ id: 'doc_paused', enabled: false }),
    document({ id: 'doc_processing', status: 'embedding' }),
    document({ id: 'doc_failed', status: 'failed' }),
  ]
  assert.deepEqual(documents.filter(needsPublish).map((d) => d.id), ['doc_ready', 'doc_review'])
})
