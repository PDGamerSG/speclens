import { expect, test, type Page } from '@playwright/test'

const inspection = (values: Record<string, unknown>) => ({
  id: 'insp-output0001', scope_id: 'scope', factory: 'Output', part_family: 'Whole hazelnut', spec_text: 'spec',
  verdict: 'good', defect: false, type: 'good', confidence: .82, rationale: 'Natural shell texture.', box_px: null,
  image_url: '/files/fixtures/parts/hazelnut_gen_01.jpg', image_width: 1024, image_height: 1024,
  memory_enabled: false, memory_status: 'disabled', memories: [], source_kind: 'synthetic_sample', source_group: null, sample_id: 'white-print',
  filename: 'white-print.jpg', image_sha256: 'a'.repeat(64), ms: 1400, cost_usd: .002, created_at: '2026-11-07T12:00:00Z', model: 'muse-spark-1.3',
  part_visible: true, prompt_tokens: 1325, cached_tokens: 1265, ...values,
})

async function open(page: Page, purpose: string) {
  await page.addInitScript(factory => {
    if (!localStorage.getItem('speclens-scope')) localStorage.setItem('speclens-scope', JSON.stringify({ factory, part_family: 'Whole hazelnut', spec_text: '' }))
  }, `Output ${purpose} ${Date.now()}`)
  await page.goto('/')
  await expect(page.getByRole('button', { name: 'Inspect part', exact: true })).toBeEnabled()
}

async function inspectWith(page: Page, reply: Record<string, unknown>) {
  await page.route('**/api/workspace/inspect', route => route.fulfill({ json: reply }))
  await page.getByRole('button', { name: 'Inspect part', exact: true }).click()
}

/** Smooth scrolling must finish first: an automated click on the sticky header would otherwise cancel it. */
async function settled(page: Page) {
  let last = -1
  await expect.poll(async () => {
    const now = await page.evaluate(() => window.scrollY)
    const still = now === last
    last = now
    return still
  }, { intervals: [120] }).toBe(true)
}

test('an accepted part shows its decision, reason, confidence and cache use', async ({ page }) => {
  await open(page, 'accept')
  await inspectWith(page, inspection({}))
  await expect(page.getByRole('heading', { name: 'Accept part', exact: true })).toBeVisible()
  await expect(page.locator('.stamp')).toHaveText('Accept')
  await expect(page.locator('.reasoning')).toContainText('Natural shell texture.')
  await expect(page.locator('.confidence-row strong')).toContainText('82')
  await expect(page.locator('.inspection-meta')).toContainText('95% of prompt from cache')
})

test('a rejected part marks the defect on the photo', async ({ page }) => {
  await open(page, 'reject')
  await inspectWith(page, inspection({ verdict: 'defect', defect: true, type: 'print', box_px: [300, 300, 600, 520], rationale: 'White ink characters on the shell.' }))
  await expect(page.getByRole('heading', { name: 'Reject part', exact: true })).toBeVisible()
  await expect(page.locator('.stamp')).toHaveText('Reject')
  await expect(page.getByLabel('Model defect location')).toContainText('print')
  await expect(page.locator('.verdict-line')).toContainText('Print detected')
})

test('a photo without the part asks for human review and explains what to do', async ({ page }) => {
  await open(page, 'review')
  await inspectWith(page, inspection({ verdict: 'uncertain', part_visible: false, confidence: .3, rationale: 'This photo shows a keyboard, not a hazelnut.' }))
  await expect(page.getByRole('heading', { name: 'Review part', exact: true })).toBeVisible()
  await expect(page.locator('.stamp')).toHaveText('Review')
  await expect(page.locator('.verdict-line')).toContainText('not clear in this photo')
  await expect(page.locator('.reasoning')).toContainText('keyboard')
  await expect(page.locator('.ticket-hint')).toContainText('top-down photo')
  await expect(page.getByRole('button', { name: 'Correct this decision' })).toBeEnabled()
})

test('a very long model reason stays inside the ticket on a phone', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await open(page, 'long reason')
  await inspectWith(page, inspection({ rationale: `${'unbrokenreasoning'.repeat(40)} ${'Long explanation of the shell. '.repeat(60)}` }))
  await expect(page.getByRole('heading', { name: 'Accept part', exact: true })).toBeInViewport()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  const reasoning = page.locator('.reasoning p')
  expect(await reasoning.evaluate(item => item.scrollWidth <= item.clientWidth)).toBe(true)
})

test('model, memory and limit failures appear as a message and keep the part ready', async ({ page }) => {
  await open(page, 'failures')
  for (const [status, detail] of [
    [502, 'The vision model could not complete this inspection. Check the model connection and try again.'],
    [503, 'Hindsight could not complete this request. Check the memory connection and retry.'],
    [429, 'This public workspace has reached its hourly request limit. Please try again later.'],
    [402, 'Meta API budget guard: spent $5.00 of $5.00'],
  ] as const) {
    await page.unroute('**/api/workspace/inspect')
    await page.route('**/api/workspace/inspect', route => route.fulfill({ status, json: { detail } }))
    await page.getByRole('button', { name: 'Inspect part', exact: true }).click()
    await expect(page.getByRole('alert')).toContainText(detail)
    await expect(page.locator('.decision-result')).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Inspect part', exact: true })).toBeEnabled()
    await page.getByRole('button', { name: 'Dismiss error', exact: true }).click()
  }
})

test('the page stays one page: every section is reachable from the inspection desk', async ({ page }) => {
  await open(page, 'one page')
  await expect(page.locator('.main-nav .nav-item')).toHaveCount(3)
  for (const [button, section] of [['Quality memory', '#standards'], ['Insights', '#dashboard'], ['Inspection desk', '#inspect']] as const) {
    const link = page.getByRole('button', { name: button, exact: true })
    await link.click()
    await expect(page.locator(section)).toBeInViewport()
    await expect(link).toHaveAttribute('aria-current', 'true')
    await settled(page)
  }
  // Compare and history are one link away from their group, not separate items in the bar.
  for (const [button, section, group] of [['Memory comparison', '#compare', 'Quality memory'], ['Inspection history', '#history', 'Insights']] as const) {
    await page.getByRole('button', { name: button, exact: true }).click()
    await expect(page.locator(section)).toBeInViewport()
    await expect(page.getByRole('button', { name: group, exact: true })).toHaveAttribute('aria-current', 'true')
    await settled(page)
  }
  await expect(page.locator('.scan-canvas')).toHaveCount(1)
})

test('reduced motion skips the point cloud and still shows the result', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await open(page, 'reduced motion')
  await expect(page.locator('.image-stage')).toHaveAttribute('data-phase', 'rest')
  await inspectWith(page, inspection({}))
  await expect(page.getByRole('heading', { name: 'Accept part', exact: true })).toBeVisible()
  await expect(page.locator('.stamp')).toHaveText('Accept')
})

test('on a phone the first screen holds the photo, the part choices, and the inspect button', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await open(page, 'phone first screen')
  await expect(page.locator('.image-stage')).toBeInViewport()
  await expect(page.locator('.part-rail')).toBeInViewport()
  const button = page.getByRole('button', { name: 'Inspect part', exact: true })
  await expect(button).toBeInViewport({ ratio: 1 })
  const clear = await button.evaluate(element => {
    const box = element.getBoundingClientRect()
    return [box.top + 3, box.bottom - 3].every(y => element.contains(document.elementFromPoint(box.left + box.width / 2, y)))
  })
  expect(clear).toBe(true)
})

test('a dropped photo becomes the selected part and shows in the upload tile', async ({ page }) => {
  await open(page, 'drop')
  const photo = (await page.request.get('/files/fixtures/parts/hazelnut_gen_01.jpg')).body()
  const data = Array.from(await photo)
  const transfer = await page.evaluateHandle(bytes => {
    const dropped = new DataTransfer()
    dropped.items.add(new File([new Uint8Array(bytes)], 'bench-photo.jpg', { type: 'image/jpeg' }))
    return dropped
  }, data)
  await page.locator('.image-stage').dispatchEvent('drop', { dataTransfer: transfer })
  await expect(page.locator('.viewer-label')).toContainText('bench-photo.jpg')
  await expect(page.locator('.viewer-tag')).toHaveText('Uploaded image')
  await expect(page.locator('.rail-upload img')).toBeVisible()
})
