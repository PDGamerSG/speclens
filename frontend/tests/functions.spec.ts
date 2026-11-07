import { expect, test, type Page } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import type { Comparison, Overview, ScopeSettings } from '../src/workspace/types'

async function openWorkspace(page: Page, purpose: string) {
  const scope: ScopeSettings = {
    factory: `Functions ${purpose} ${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    part_family: 'Whole hazelnut',
    spec_text: '',
  }
  await page.addInitScript(value => {
    if (!localStorage.getItem('speclens-scope')) localStorage.setItem('speclens-scope', JSON.stringify(value))
  }, scope)
  await page.goto('/')
  await expect(page.getByRole('button', { name: 'Inspect part', exact: true })).toBeEnabled()
  return scope
}

async function readDownload<T>(page: Page, button: string) {
  const pending = page.waitForEvent('download')
  await page.getByRole('button', { name: button, exact: true }).click()
  const download = await pending
  return {
    filename: download.suggestedFilename(),
    record: JSON.parse(await readFile((await download.path())!, 'utf8')) as T,
  }
}

test('an uploaded photo keeps its original decision and human correction in the full history export', async ({ page }) => {
  const scope = await openWorkspace(page, 'upload')
  await page.getByLabel('Upload part photo').setInputFiles({
    name: 'operator-part.jpg', mimeType: 'image/jpeg',
    buffer: await readFile(new URL('../../fixtures/parts/hazelnut_gen_03.jpg', import.meta.url)),
  })
  await expect(page.locator('.viewer-label')).toContainText('operator-part.jpg')
  await expect(page.locator('.viewer-tag')).toHaveText('Uploaded image')
  await expect(page.locator('.part-image')).toBeVisible()
  await page.getByRole('switch', { name: 'Use quality memory' }).click()
  await page.getByRole('button', { name: 'Inspect part', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Accept part', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Correct this decision' }).click()
  await page.getByLabel('Defect class').selectOption('crack')
  await page.getByLabel('What should the inspector learn?').fill('Reject a split shell; a natural smooth highlight alone is acceptable.')
  await page.getByLabel('Reviewed by').fill('Upload acceptance reviewer')
  await page.getByRole('button', { name: 'Save correction & remember' }).click()
  await expect(page.locator('.reviewed-note')).toContainText('reject by Upload acceptance reviewer')

  await page.reload()
  await page.getByRole('button', { name: 'Inspection history', exact: true }).click()
  await expect(page.locator('tbody tr')).toHaveCount(1)
  const row = page.locator('tbody tr').filter({ hasText: 'operator-part.jpg' })
  await expect(row.locator('td').nth(1)).toHaveText('Accept')
  await expect(row.locator('td').nth(4)).toContainText('Reject by Upload acceptance reviewer')
  await row.getByRole('button', { name: /^Open inspection / }).click()
  await expect(page.locator('.viewer-label')).toContainText('operator-part.jpg')
  await expect(page.getByRole('heading', { name: 'Accept part', exact: true })).toBeVisible()
  await expect(page.locator('.reviewed-note')).toContainText('Upload acceptance reviewer')
  await expect(page.getByRole('button', { name: 'Correct this decision' })).toHaveCount(0)

  await page.getByRole('button', { name: 'Inspection history', exact: true }).click()
  await page.getByRole('searchbox', { name: 'Search inspection history' }).fill('no matching upload')
  await expect(page.locator('tbody')).toContainText('No matching inspections')
  const { filename, record } = await readDownload<Overview & { format_version: number; scope: ScopeSettings }>(page, 'Export records')
  expect(filename).toBe('speclens-inspection-records.json')
  expect(record.format_version).toBe(1)
  expect(record.scope.factory).toBe(scope.factory)
  expect(record.inspections).toHaveLength(1)
  expect(record.corrections).toHaveLength(1)
  const original = record.inspections[0]
  expect(original).toMatchObject({ filename: 'operator-part.jpg', source_kind: 'upload', verdict: 'good', memory_enabled: false })
  expect(original.image_sha256).toMatch(/^[a-f0-9]{64}$/)
  expect(record.corrections[0]).toMatchObject({
    inspection_id: original.id, original_verdict: 'good', original_rationale: original.rationale,
    verdict: 'defect', defect_type: 'crack', reviewer: 'Upload acceptance reviewer', sync_status: 'synced',
    rule_text: 'Reject a split shell; a natural smooth highlight alone is acceptable.',
  })
  const savedPhoto = await page.request.get(original.image_url)
  expect(savedPhoto.ok()).toBe(true)
  expect(savedPhoto.headers()['content-type']).toContain('image/jpeg')
})

test('defect outlines can be hidden and restored while zoom stays within its usable bounds', async ({ page }) => {
  const scope = await openWorkspace(page, 'viewer')
  const inspected = await page.request.post('/api/workspace/inspect', {
    multipart: { ...scope, sample_id: 'white-print', memory_enabled: 'false' },
  })
  expect(inspected.ok()).toBe(true)
  const source = await inspected.json()
  const corrected = await page.request.post('/api/workspace/corrections', {
    data: { inspection_id: source.id, verdict: 'defect', defect_type: 'print',
      rule_text: 'Reject sharp printed ink on the shell, including faint characters.', reviewer: 'Viewer setup reviewer' },
  })
  expect(corrected.status()).toBe(201)
  const outline = page.getByRole('button', { name: 'Defect outline', exact: true })
  await expect(outline).toBeDisabled()
  await page.getByRole('button', { name: 'Another marking', exact: true }).click()
  await page.getByRole('button', { name: 'Inspect part', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Reject part', exact: true })).toBeVisible()
  await expect(page.getByLabel('Model defect location')).toBeVisible()
  await expect(outline).toHaveAttribute('aria-pressed', 'true')
  await outline.click()
  await expect(page.getByLabel('Model defect location')).toHaveCount(0)
  await expect(outline).toHaveAttribute('aria-pressed', 'false')
  await outline.click()
  await expect(page.getByLabel('Model defect location')).toBeVisible()

  const zoomIn = page.getByRole('button', { name: 'Zoom in', exact: true })
  const zoomOut = page.getByRole('button', { name: 'Zoom out', exact: true })
  await expect(zoomOut).toBeDisabled()
  for (let step = 0; step < 4; step++) await zoomIn.click()
  await expect(page.locator('.zoom-controls')).toContainText('200%')
  await expect(page.locator('.part-image-wrap')).toHaveCSS('transform', 'matrix(2, 0, 0, 2, 0, 0)')
  await expect(zoomIn).toBeDisabled()
  await zoomOut.click()
  await expect(page.locator('.zoom-controls')).toContainText('175%')
  await page.getByRole('button', { name: 'Reset zoom', exact: true }).click()
  await expect(page.locator('.zoom-controls')).toContainText('100%')
  await expect(page.locator('.part-image-wrap')).toHaveCSS('transform', 'matrix(1, 0, 0, 1, 0, 0)')
  await expect(zoomOut).toBeDisabled()
  await expect(page.getByLabel('Model defect location')).toBeVisible()
})

test('workspace settings trap focus, discard Escape edits, and retain saved settings after reload', async ({ page }) => {
  const scope = await openWorkspace(page, 'settings')
  const opener = page.getByRole('button', { name: 'Workspace settings', exact: true }).first()
  await opener.click()
  const dialog = page.getByRole('dialog', { name: 'Workspace settings' })
  const close = dialog.getByRole('button', { name: 'Close settings', exact: true })
  const save = dialog.getByRole('button', { name: 'Save workspace', exact: true })
  await expect(close).toBeFocused()
  await page.keyboard.press('Shift+Tab')
  await expect(save).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(close).toBeFocused()
  await dialog.getByLabel('Factory or workspace').fill('Unsaved factory')
  await page.keyboard.press('Escape')
  await expect(dialog).toHaveCount(0)
  await expect(opener).toBeFocused()
  await expect(page.locator('.workspace-switch')).toContainText(scope.factory)

  await opener.click()
  await expect(dialog.getByLabel('Factory or workspace')).toHaveValue(scope.factory)
  const savedFactory = `${scope.factory} saved`
  const specification = 'Accept intact shells. Reject printed ink, cracks, cuts, and holes.'
  await dialog.getByLabel('Factory or workspace').fill(savedFactory)
  await dialog.getByLabel('Part family', { exact: true }).fill('Sorted hazelnuts')
  await dialog.getByLabel('Base quality specification').fill(specification)
  await save.click()
  await expect(dialog).toHaveCount(0)
  await expect(page.locator('.workspace-switch')).toContainText(savedFactory)
  await page.reload()
  await expect(page.locator('.workspace-switch')).toContainText(savedFactory)
  await opener.click()
  await expect(dialog.getByLabel('Factory or workspace')).toHaveValue(savedFactory)
  await expect(dialog.getByLabel('Part family', { exact: true })).toHaveValue('Sorted hazelnuts')
  await expect(dialog.getByLabel('Base quality specification')).toHaveValue(specification)
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: 'Inspection history', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'A clear trail for every decision' })).toBeVisible()
})

test('empty memory remains usable and a rejected image creates no phantom inspection', async ({ page }) => {
  await openWorkspace(page, 'empty')
  await page.getByRole('button', { name: 'Quality memory', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Your standards start with a correction' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Summarize standards', exact: true })).toBeDisabled()
  await page.getByRole('button', { name: 'Inspection history', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Export records', exact: true })).toBeDisabled()
  await page.getByRole('button', { name: 'Inspect your first part', exact: true }).click()
  await expect(page.getByRole('switch', { name: 'Use quality memory' })).toHaveAttribute('aria-checked', 'true')
  const emptyInspection = page.waitForResponse(response => response.url().endsWith('/api/workspace/inspect') && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Inspect part', exact: true }).click()
  expect((await (await emptyInspection).json()).memory_status).toBe('empty')
  await expect(page.getByRole('heading', { name: 'Accept part', exact: true })).toBeVisible()
  await expect(page.locator('.inspection-meta')).toContainText('0 recalled standards')
  await expect(page.getByRole('alert')).toHaveCount(0)

  await page.getByLabel('Upload part photo').setInputFiles({ name: 'damaged.png', mimeType: 'image/png', buffer: Buffer.from('not decoded image data') })
  const rejected = page.waitForResponse(response => response.url().endsWith('/api/workspace/inspect') && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Inspect part', exact: true }).click()
  expect((await rejected).status()).toBe(400)
  await expect(page.getByRole('alert')).toContainText('not a readable image')
  await expect(page.locator('.decision-result')).toHaveCount(0)
  await page.getByRole('button', { name: 'Dismiss error', exact: true }).click()
  await expect(page.getByRole('alert')).toHaveCount(0)
  await page.getByRole('button', { name: 'Natural shell', exact: true }).click()
  await page.getByRole('button', { name: 'Inspect part', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Accept part', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Inspection history', exact: true }).click()
  await expect(page.locator('tbody tr')).toHaveCount(2)
  await expect(page.locator('tbody')).not.toContainText('damaged.png')
})

test('saved comparisons reopen and export their own image and optional expected decision', async ({ page }) => {
  await openWorkspace(page, 'saved comparisons')
  await page.getByRole('button', { name: 'White marking', exact: true }).click()
  await page.getByRole('button', { name: 'Memory comparison', exact: true }).click()
  await expect(page.getByLabel('Expected decision')).toHaveValue('defect')
  await page.getByRole('button', { name: 'Run comparison', exact: true }).click()
  await expect(page.locator('.comparison-history-row')).toHaveCount(1)
  await page.getByLabel('Choose comparison sample').selectOption({ label: 'Small hole' })
  await page.getByLabel('Expected decision').selectOption({ label: 'Not labeled' })
  await expect(page.getByLabel('Expected decision')).toHaveValue('')
  await page.getByRole('button', { name: 'Run comparison', exact: true }).click()
  await expect(page.locator('.comparison-history-row')).toHaveCount(2)
  await expect(page.locator('.comparison-outcome')).toHaveCount(0)
  const current = await readDownload<Comparison & { format_version: number }>(page, 'Export comparison')
  expect(current.record.expected_verdict).toBeNull()
  expect(current.record.baseline.filename).toBe('small-hole.jpg')
  expect(current.record.baseline.image_sha256).toBe(current.record.with_memory.image_sha256)

  await page.reload()
  await page.getByRole('button', { name: 'Memory comparison', exact: true }).click()
  await expect(page.locator('.comparison-history-row')).toHaveCount(2)
  await page.locator('.comparison-history-row').filter({ hasText: 'small-hole.jpg' }).click()
  await expect(page.locator('.compare-input strong')).toHaveText('small-hole.jpg')
  await expect(page.getByLabel('Expected decision')).toHaveValue('')
  await expect(page.locator('.comparison-outcome')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Run comparison', exact: true })).toBeDisabled()
  const reopened = await readDownload<Comparison & { format_version: number }>(page, 'Export comparison')
  expect(reopened.filename).toBe(`speclens-${current.record.id}.json`)
  expect(reopened.record.format_version).toBe(1)
  expect(reopened.record.id).toBe(current.record.id)
  expect(reopened.record.expected_verdict).toBeNull()
  expect(reopened.record.baseline.id).toBe(current.record.baseline.id)
  expect(reopened.record.with_memory.id).toBe(current.record.with_memory.id)
  await page.locator('.comparison-history-row').filter({ hasText: 'white-print.jpg' }).click()
  await expect(page.locator('.compare-input strong')).toHaveText('white-print.jpg')
  await expect(page.getByLabel('Expected decision')).toHaveValue('defect')
  await expect(page.locator('.comparison-outcome')).toHaveCount(2)
  const labeled = await readDownload<Comparison>(page, 'Export comparison')
  expect(labeled.record.expected_verdict).toBe('defect')
  expect(labeled.record.baseline.filename).toBe('white-print.jpg')
})
