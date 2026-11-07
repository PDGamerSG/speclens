import { expect, test } from '@playwright/test'

test.beforeEach(async ({ page }, info) => {
  await page.addInitScript(factory => localStorage.setItem('speclens-scope', JSON.stringify({ factory, part_family: 'Whole hazelnut', spec_text: '' })), `UI regression ${info.title.slice(0, 40)} ${Date.now()}`)
})

test('the automatically selected sample initializes the expected comparison decision', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('button', { name: 'Inspect part', exact: true })).toBeEnabled()
  await page.getByRole('button', { name: 'Memory comparison', exact: true }).click()
  await expect(page.getByLabel('Choose comparison sample')).toHaveValue('white-print')
  await expect(page.getByLabel('Expected decision')).toHaveValue('defect')
  const response = page.waitForResponse(result => result.url().endsWith('/api/workspace/compare') && result.request().method() === 'POST')
  await page.getByRole('button', { name: 'Run comparison', exact: true }).click()
  expect((await (await response).json()).expected_verdict).toBe('defect')
})

test('retrying a failed startup request restores samples and permits an inspection', async ({ page }) => {
  let unavailable = true
  await page.route('**/api/workspace/samples', route => unavailable
    ? route.fulfill({ status: 503, json: { detail: 'The connection was interrupted.' } })
    : route.continue())
  await page.goto('/')
  await expect(page.getByRole('alert')).toContainText('The connection was interrupted.')
  await expect(page.getByRole('button', { name: 'Inspect part', exact: true })).toBeDisabled()
  unavailable = false
  await page.getByRole('button', { name: 'Retry connection', exact: true }).click()
  await expect(page.getByRole('alert')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'White marking', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Inspect part', exact: true })).toBeEnabled()
  await page.getByRole('button', { name: 'Inspect part', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Accept part', exact: true })).toBeVisible()
})
