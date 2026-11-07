import { expect, test } from '@playwright/test'
import { readFile } from 'node:fs/promises'

test('a correction is retained, recalled on a new part, and compared against the baseline', async ({ page }) => {
  await page.addInitScript((factory) => localStorage.setItem('speclens-scope', JSON.stringify({ factory, part_family: 'Whole hazelnut', spec_text: '' })), 'UI acceptance ' + Date.now())
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Inspection desk', exact: true })).toBeVisible()
  await page.getByRole('switch', { name: 'Use quality memory' }).click()
  await page.getByRole('button', { name: 'Inspect part', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Accept part', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Correct this decision' }).click()
  await page.getByLabel('What should the inspector learn?').fill('Sharp printed characters are ink and must be rejected, including faint markings.')
  await page.getByLabel('Reviewed by').fill('QA test operator')
  await page.getByRole('button', { name: 'Save correction & remember' }).click()
  await expect(page.getByRole('status')).toContainText('now available in Hindsight')
  await page.getByRole('button', { name: 'Quality memory', exact: true }).click()
  await expect(page.getByText('Sharp printed characters are ink and must be rejected, including faint markings.', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Summarize standards' }).click()
  await expect(page.getByRole('heading', { name: 'What your inspector has learned' })).toBeVisible()
  await page.getByRole('button', { name: 'Inspection desk', exact: true }).click()
  await page.getByRole('button', { name: 'Another marking', exact: true }).click()
  await page.getByRole('switch', { name: 'Use quality memory' }).click()
  await page.getByRole('button', { name: 'Inspect part', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Reject part', exact: true })).toBeVisible()
  await expect(page.locator('.recalled-standard')).toContainText('Sharp printed characters')
  await page.getByRole('button', { name: 'Memory comparison', exact: true }).click()
  await page.getByRole('button', { name: 'Run comparison', exact: true }).click()
  await expect(page.locator('.comparison-arm').first()).toContainText('Accept part')
  await expect(page.locator('.comparison-arm').last()).toContainText('Reject part')
  await expect(page.locator('.comparison-arm').first()).toContainText('Differs from the selected label: reject')
  await expect(page.locator('.comparison-arm').last()).toContainText('Matches the selected label: reject')
  await expect(page.locator('.comparison-disclosure')).toContainText('decisions differ')
  const downloadEvent = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Export comparison', exact: true }).click()
  const download = await downloadEvent
  const artifact = JSON.parse(await readFile((await download.path())!, 'utf8'))
  expect(artifact.format_version).toBe(1)
  expect(artifact.baseline.image_sha256).toBe(artifact.with_memory.image_sha256)
  expect(artifact.with_memory.memories[0].source_id).toContain('correction-')
  await page.getByRole('button', { name: 'Inspection history', exact: true }).click()
  await expect(page.locator('tbody tr')).toHaveCount(4)
  const reviewed = page.locator('tbody tr').filter({ hasText: 'QA test operator' })
  await expect(reviewed.locator('td').nth(1)).toContainText('Accept')
  await expect(reviewed.locator('td').nth(4)).toContainText('Reject · QA test operator')
  await page.getByRole('searchbox', { name: 'Search inspection history' }).fill('QA test operator')
  await expect(page.locator('tbody tr')).toHaveCount(1)
  await page.getByRole('searchbox', { name: 'Search inspection history' }).fill('no such part')
  await expect(page.locator('tbody')).toContainText('No matching inspections')
  await page.getByRole('searchbox', { name: 'Search inspection history' }).clear()
  await expect(page.locator('tbody tr')).toHaveCount(4)
  await page.reload()
  await page.getByRole('button', { name: 'Quality memory', exact: true }).click()
  await expect(page.getByText('Sharp printed characters are ink and must be rejected, including faint markings.', { exact: true })).toBeVisible()
})

test('mobile navigation, part selection and settings work without horizontal overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/')
  await page.getByRole('button', { name: 'Small hole', exact: true }).click()
  await expect(page.locator('.viewer-label')).toContainText('Small hole')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.getByRole('button', { name: 'Quality memory', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Quality memory', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Workspace settings', exact: true }).first().click()
  await page.getByLabel('Factory or workspace').fill('Mobile factory')
  await page.getByRole('button', { name: 'Save workspace' }).click()
  await expect(page.locator('.breadcrumb')).toContainText('Mobile factory')
  await expect(page.locator('.empty-state')).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})

test('a pending correction can be retried after an interrupted sync without an error message', async ({ page }) => {
  await page.route('**/api/workspace/overview?*', route => route.fulfill({ json: {
    scope_id: 'scope', bank_id: 'bank', inspections: [], comparisons: [],
    stats: { inspections: 1, corrections: 1, synced: 0, pending: 1 },
    corrections: [{ id: 'correction-pending', inspection_id: 'insp-source', scope_id: 'scope',
      rule_text: 'Reject sharp ink characters on the shell.', reviewer: 'QA operator',
      original_verdict: 'good', original_type: 'good', original_rationale: 'Natural gloss.',
      image_url: '/files/fixtures/parts/hazelnut_gen_01.jpg', verdict: 'defect', defect_type: 'print',
      created_at: '2026-11-07T12:00:00Z', sync_status: 'pending', sync_error: null }],
  } }))
  await page.goto('/')
  await page.getByRole('button', { name: 'Quality memory', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Retry sync', exact: true })).toBeVisible()
})

test('workspace settings cannot change scopes during an inspection', async ({ page }) => {
  let release!: () => void
  const gate = new Promise<void>(resolve => { release = resolve })
  await page.route('**/api/workspace/inspect', async route => { await gate; await route.continue() })
  await page.goto('/')
  await page.getByRole('switch', { name: 'Use quality memory' }).click()
  await page.getByRole('button', { name: 'Inspect part', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Inspecting part…', exact: true })).toBeDisabled()
  try {
    for (const button of await page.getByRole('button', { name: 'Workspace settings', exact: true }).all()) {
      await expect(button).toBeDisabled()
    }
    await expect(page.locator('.workspace-switch')).toBeDisabled()
  } finally { release() }
  await expect(page.getByRole('heading', { name: 'Accept part', exact: true })).toBeVisible()
})

test('opening a historical comparison restores its own image identity', async ({ page }) => {
  await page.addInitScript(factory => localStorage.setItem('speclens-scope', JSON.stringify({ factory, part_family: 'Whole hazelnut', spec_text: '' })), 'Comparison history ' + Date.now())
  await page.goto('/')
  await page.getByRole('button', { name: 'White marking', exact: true }).click()
  await page.getByRole('button', { name: 'Memory comparison', exact: true }).click()
  await page.getByRole('button', { name: 'Run comparison', exact: true }).click()
  await expect(page.locator('.comparison-history-row')).toHaveCount(1)
  await page.getByLabel('Choose comparison sample').selectOption({ label: 'Small hole' })
  await expect(page.locator('.compare-input strong')).toHaveText('Small hole')
  await page.locator('.comparison-history-row').click()
  await expect(page.locator('.compare-input strong')).toHaveText('white-print.jpg')
  await expect(page.getByRole('button', { name: 'Run comparison', exact: true })).toBeDisabled()
})

test('invalid uploads show a useful error without replacing the selected part', async ({ page }) => {
  await page.goto('/')
  await expect(page.locator('.viewer-label')).toContainText('White marking')
  await page.getByLabel('Upload part photo').setInputFiles({ name: 'report.pdf', mimeType: 'application/pdf', buffer: Buffer.from('not a photo') })
  await expect(page.getByRole('alert')).toContainText('JPG, PNG or WebP')
  await expect(page.locator('.viewer-label')).toContainText('White marking')
  await page.getByLabel('Upload part photo').setInputFiles({ name: 'huge.png', mimeType: 'image/png', buffer: Buffer.alloc(8 * 1024 * 1024 + 1) })
  await expect(page.getByRole('alert')).toContainText('smaller than 8 MB')
})
