#!/usr/bin/env node
/**
 * Run manually after the real deployment is ready:
 *   node frontend/scripts/live-smoke.mjs
 *
 * Five logical vision calls, no mocks, and no assertion that memory changes a
 * model decision. Storage state is a credential: it is saved privately for a
 * subsequent server-restart persistence check and never printed.
 *
 * Resume browser checks with zero new vision calls after an interrupted run:
 *   CHIEF_SKILL_RESUME_DIR=/absolute/path/to/the/prior/run node frontend/scripts/live-smoke.mjs
 * Set CHIEF_SKILL_RESUME_PHASE=isolation to check isolation while a UI fix is
 * pending, or mobile to rerun only the viewer/mobile checks after that fix.
 */
import { chromium, expect } from '@playwright/test'
import { chmod, mkdir, readFile, writeFile } from 'node:fs/promises'
import { randomUUID } from 'node:crypto'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const LIVE_TIMEOUT = 240_000
const UI_TIMEOUT = 30_000
const MAX_VISION_CALLS = 5
const resumedFrom = process.env.CHIEF_SKILL_RESUME_DIR ? resolve(process.env.CHIEF_SKILL_RESUME_DIR) : null
const priorPersistence = resumedFrom ? JSON.parse(await readFile(join(resumedFrom, 'persistence.json'), 'utf8')) : null
const priorSummary = resumedFrom ? JSON.parse(await readFile(join(resumedFrom, 'summary.json'), 'utf8')) : null
const resumePhase = process.env.CHIEF_SKILL_RESUME_PHASE || 'all'
if (!['all', 'isolation', 'mobile'].includes(resumePhase)) throw new Error('CHIEF_SKILL_RESUME_PHASE must be all, isolation, or mobile.')
const target = new URL(process.env.CHIEF_SKILL_BASE_URL || priorPersistence?.base_url || 'https://chief-skill.13-236-192-155.sslip.io')
if (!['https:', 'http:'].includes(target.protocol) || target.username || target.password) {
  throw new Error('CHIEF_SKILL_BASE_URL must be an HTTP(S) URL without embedded credentials.')
}
const baseURL = target.origin
const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const runId = `${new Date().toISOString().replace(/[:.]/g, '-')}-${randomUUID().slice(0, 8)}`
const artifactDir = join(projectRoot, 'var', 'checks', `live-smoke-${runId}`)
const summaryPath = join(artifactDir, 'summary.json')
const storageStatePath = join(artifactDir, 'storage-state.private.json')
const persistencePath = join(artifactDir, 'persistence.json')
const scope = priorPersistence?.scope || {
  factory: `Chief Skill live smoke ${runId}`,
  part_family: 'Whole hazelnut',
  spec_text: '',
}
const rule = 'Reject any white printed ink or sharp pale lettering on the hazelnut shell, including faint marks. Natural shell highlights and texture alone are acceptable.'
const reviewer = 'Chief Skill live smoke'
const check = expect.configure({ timeout: UI_TIMEOUT })
const sensitiveValues = new Set()
const summary = {
  format_version: 1,
  base_url: baseURL,
  started_at: new Date().toISOString(),
  status: 'running',
  integration_only: true,
  run_mode: resumedFrom ? `resume-${resumePhase}` : 'full-live',
  ...(resumedFrom ? { resumed_from: resumedFrom, prior_run_status: priorSummary.status, prior_failure_step: priorSummary.failure?.step || null } : {}),
  note: 'Real provider integration smoke check; observed decisions do not establish an accuracy improvement.',
  scope,
  vision_calls: { planned: resumedFrom ? 0 : 5, maximum: resumedFrom ? 0 : MAX_VISION_CALLS, requested_estimate: 0, ...(resumedFrom ? { prior_run_requested_estimate: priorSummary.vision_calls.requested_estimate } : {}) },
  checks: resumedFrom ? priorSummary.checks.filter(item => item.status === 'passed').map(item => ({ ...item, carried_from_prior_run: true })) : [],
  screenshots: [],
  records: {
    inspection_ids: [...(priorPersistence?.inspection_ids || [])],
    correction_ids: [...(priorPersistence?.correction_ids || [])],
    comparison_ids: [...(priorPersistence?.comparison_ids || [])],
  },
}
let browser
let context
let page
let secondContext
let currentStep = 'startup'
let firstInspection
let correction
let transferInspection
let uploadInspection
let comparison
let finalOverview

function shortId(id) {
  return id.replace(/^(insp-|correction-|compare-)/, '').slice(0, 8).toUpperCase()
}

function safeMessage(error) {
  let message = error instanceof Error ? error.message : String(error)
  for (const value of sensitiveValues) message = message.split(value).join('[redacted]')
  return message.replace(/\b[a-f0-9]{64}\b/gi, '[redacted]').slice(0, 2400)
}

async function writePrivateJson(path, value) {
  await writeFile(path, `${JSON.stringify(value, null, 2)}\n`, { mode: 0o600 })
  await chmod(path, 0o600)
}

async function saveCheckpoint() {
  if (context) await writePrivateJson(storageStatePath, await context.storageState())
  await writePrivateJson(persistencePath, {
    format_version: 1,
    base_url: baseURL,
    scope,
    run_id: runId,
    storage_state_path: storageStatePath,
    inspection_ids: [...summary.records.inspection_ids],
    correction_ids: [...summary.records.correction_ids],
    comparison_ids: [...summary.records.comparison_ids],
    image_urls: [firstInspection, transferInspection, uploadInspection, comparison?.baseline, comparison?.with_memory]
      .filter(Boolean).map(item => item.image_url),
    expected_counts: {
      inspections: summary.records.inspection_ids.length,
      corrections: summary.records.correction_ids.length,
      comparisons: summary.records.comparison_ids.length,
    },
    check_status: summary.status,
    updated_at: new Date().toISOString(),
  })
  await writePrivateJson(summaryPath, summary)
}

async function step(name, operation) {
  currentStep = name
  const carriedIndex = summary.checks.findIndex(item => item.name === name && item.carried_from_prior_run)
  if (carriedIndex !== -1) summary.checks.splice(carriedIndex, 1)
  const started = Date.now()
  try {
    const details = await operation()
    summary.checks.push({ name, status: 'passed', duration_ms: Date.now() - started, ...(details ? { details } : {}) })
    await saveCheckpoint()
  } catch (error) {
    summary.checks.push({ name, status: 'failed', duration_ms: Date.now() - started, message: safeMessage(error) })
    throw error
  }
}

async function screenshot(name, screenshotPage = page) {
  await check(screenshotPage.locator('.spin, .is-scanning')).toHaveCount(0)
  await screenshotPage.waitForFunction(() => Array.from(document.images)
    .every(image => image.complete && image.naturalWidth > 0), undefined, { timeout: UI_TIMEOUT })
  await screenshotPage.evaluate(() => window.scrollTo(0, 0))
  const filename = `${name}.png`
  await screenshotPage.screenshot({ path: join(artifactDir, filename), fullPage: true, animations: 'disabled' })
  await chmod(join(artifactDir, filename), 0o600)
  summary.screenshots.push(filename)
}

async function navigate(name, currentPage = page) {
  await currentPage.getByRole('button', { name, exact: true }).click()
  await check(currentPage.getByRole('heading', { name, exact: true })).toBeVisible()
}

async function setMemory(enabled) {
  const toggle = page.getByRole('switch', { name: 'Use quality memory' })
  if ((await toggle.getAttribute('aria-checked')) !== String(enabled)) await toggle.click()
  await check(toggle).toHaveAttribute('aria-checked', String(enabled))
}

async function liveAction(endpoint, action, { status = 200, visionCalls = 0 } = {}) {
  if (summary.vision_calls.requested_estimate + visionCalls > summary.vision_calls.maximum) {
    throw new Error('The live smoke vision-call budget would be exceeded.')
  }
  const responsePending = page.waitForResponse(response =>
    new URL(response.url()).pathname === `/api/workspace/${endpoint}` && response.request().method() === 'POST',
  { timeout: LIVE_TIMEOUT })
  summary.vision_calls.requested_estimate += visionCalls
  const [response] = await Promise.all([responsePending, action()])
  if (response.status() !== status) throw new Error(`Live ${endpoint} returned HTTP ${response.status()} (expected ${status}).`)
  return response.json()
}

function rememberInspection(item) {
  check(typeof item.id).toBe('string')
  check(item.id.startsWith('insp-')).toBe(true)
  check(['good', 'defect', 'uncertain'].includes(item.verdict)).toBe(true)
  check(typeof item.rationale === 'string' && item.rationale.trim().length > 0).toBe(true)
  check(item.model).toBe('muse-spark-1.3')
  check(/^\/files\/workspace\/insp-[a-f0-9]+\.jpg$/.test(item.image_url)).toBe(true)
  if (typeof item.owner_id === 'string' && item.owner_id) sensitiveValues.add(item.owner_id)
  if (!summary.records.inspection_ids.includes(item.id)) summary.records.inspection_ids.push(item.id)
}

async function readDownload(buttonName) {
  const pending = page.waitForEvent('download', { timeout: UI_TIMEOUT })
  await page.getByRole('button', { name: buttonName, exact: true }).click()
  const download = await pending
  const downloadedPath = await download.path()
  if (!downloadedPath) throw new Error('The browser did not provide the JSON download.')
  const record = JSON.parse(await readFile(downloadedPath, 'utf8'))
  // Inspect full records in memory and remove the raw temporary download.
  // Public summaries contain only allowlisted verification fields.
  await download.delete()
  return { filename: download.suggestedFilename(), record }
}

function overviewPath() {
  return `/api/workspace/overview?${new URLSearchParams(scope)}`
}

async function requestJson(requestContext, path, options = {}) {
  const response = await requestContext.get(path, { timeout: LIVE_TIMEOUT, ...options })
  if (!response.ok()) throw new Error(`Live GET ${new URL(path, baseURL).pathname} returned HTTP ${response.status()}.`)
  return response.json()
}

async function checkSettings(currentPage = page) {
  const opener = currentPage.getByRole('button', { name: 'Workspace settings', exact: true }).first()
  await opener.click()
  const dialog = currentPage.getByRole('dialog', { name: 'Workspace settings' })
  const close = dialog.getByRole('button', { name: 'Close settings', exact: true })
  const save = dialog.getByRole('button', { name: 'Save workspace', exact: true })
  await check(close).toBeFocused()
  await currentPage.keyboard.press('Shift+Tab')
  await check(save).toBeFocused()
  await currentPage.keyboard.press('Tab')
  await check(close).toBeFocused()
  await dialog.getByLabel('Factory or workspace').fill('Unsaved live smoke edit')
  await currentPage.keyboard.press('Escape')
  await check(dialog).toHaveCount(0)
  await check(opener).toBeFocused()
  await check(currentPage.locator('.breadcrumb')).toContainText(scope.factory)
  await opener.click()
  await check(dialog.getByLabel('Factory or workspace')).toHaveValue(scope.factory)
  await currentPage.keyboard.press('Escape')
}

async function mobileWidth(label) {
  const geometry = await page.evaluate(() => ({ viewport: window.innerWidth, document: document.documentElement.scrollWidth }))
  check(geometry.document, `${label}: document width at a ${geometry.viewport}px viewport`).toBeLessThanOrEqual(geometry.viewport + 1)
  return { view: label, viewport_px: geometry.viewport, document_px: geometry.document }
}

await mkdir(artifactDir, { recursive: true, mode: 0o700 })
await chmod(artifactDir, 0o700)

try {
  browser = await chromium.launch({ headless: true })
  context = await browser.newContext({
    baseURL,
    viewport: { width: 1440, height: 1000 },
    acceptDownloads: true,
    ...(resumedFrom ? { storageState: join(resumedFrom, 'storage-state.private.json') } : {}),
  })
  await context.addInitScript(value => {
    if (!localStorage.getItem('speclens-scope')) localStorage.setItem('speclens-scope', JSON.stringify(value))
  }, scope)
  page = await context.newPage()
  page.setDefaultTimeout(UI_TIMEOUT)
  page.setDefaultNavigationTimeout(60_000)

  if (resumedFrom) {
    await step('restore saved public session without another vision call', async () => {
      for (const cookie of await context.cookies()) sensitiveValues.add(cookie.value)
      finalOverview = await requestJson(context.request, overviewPath())
      check(finalOverview.inspections.length).toBe(priorPersistence.expected_counts.inspections)
      check(finalOverview.corrections.length).toBe(priorPersistence.expected_counts.corrections)
      check(finalOverview.comparisons.length).toBe(priorPersistence.expected_counts.comparisons)
      firstInspection = finalOverview.inspections.find(item => item.id === priorPersistence.inspection_ids[0])
      transferInspection = finalOverview.inspections.find(item => item.id === priorPersistence.inspection_ids[1])
      uploadInspection = finalOverview.inspections.find(item => item.id === priorPersistence.inspection_ids[2])
      correction = finalOverview.corrections.find(item => item.id === priorPersistence.correction_ids[0])
      comparison = finalOverview.comparisons.find(item => item.id === priorPersistence.comparison_ids[0])
      check(Boolean(firstInspection && transferInspection && uploadInspection && correction && comparison)).toBe(true)
      for (const item of finalOverview.inspections) rememberInspection(item)
      await page.goto('/')
      await check(page.getByRole('button', { name: 'Inspect part', exact: true })).toBeEnabled()
      await check(page.locator('.breadcrumb')).toContainText(scope.factory)
      return { restored_inspections: finalOverview.inspections.length, new_vision_calls: 0 }
    })
  } else {
  await step('public workspace and real provider configuration', async () => {
    const status = await requestJson(context.request, '/api/workspace/status')
    check(status.ok).toBe(true)
    check(status.model_configured).toBe(true)
    check(status.memory_configured).toBe(true)
    const cookie = (await context.cookies()).find(item => item.name === 'chief_skill_workspace')
    check(Boolean(cookie)).toBe(true)
    sensitiveValues.add(cookie.value)
    check(cookie.httpOnly).toBe(true)
    if (target.protocol === 'https:') check(cookie.secure).toBe(true)
    await page.goto('/')
    await check(page.getByRole('heading', { name: 'Inspection desk', exact: true })).toBeVisible()
    await check(page.getByRole('button', { name: 'Inspect part', exact: true })).toBeEnabled()
    await check(page.locator('.breadcrumb')).toContainText(scope.factory)
    const overview = await requestJson(context.request, overviewPath())
    check(overview.stats.inspections).toBe(0)
    check(overview.corrections.length).toBe(0)
    return { model: status.model, public_cookie_http_only: cookie.httpOnly, public_cookie_secure: cookie.secure }
  })

  await step('sample inspection with memory off', async () => {
    await page.getByRole('button', { name: 'White marking', exact: true }).click()
    await setMemory(false)
    firstInspection = await liveAction('inspect', () => page.getByRole('button', { name: 'Inspect part', exact: true }).click(), { visionCalls: 1 })
    rememberInspection(firstInspection)
    check(firstInspection.memory_enabled).toBe(false)
    check(firstInspection.memory_status).toBe('disabled')
    check(firstInspection.sample_id).toBe('white-print')
    await check(page.locator('.decision-result')).toBeVisible()
    await screenshot('01-baseline-memory-off')
    return { inspection_id: firstInspection.id, observed_verdict: firstInspection.verdict, memory_status: firstInspection.memory_status }
  })

  await step('human white-print correction retained in Hindsight', async () => {
    await page.getByRole('button', { name: 'Correct this decision', exact: true }).click()
    await page.getByRole('radio', { name: 'Reject part', exact: true }).check()
    await page.getByLabel('Defect class').selectOption('print')
    await page.getByLabel('What should the inspector learn?').fill(rule)
    await page.getByLabel('Reviewed by').fill(reviewer)
    correction = await liveAction('corrections', () => page.getByRole('button', { name: 'Save correction & remember', exact: true }).click(), { status: 201 })
    check(correction.sync_status).toBe('synced')
    check(correction.inspection_id).toBe(firstInspection.id)
    check(correction.original_verdict).toBe(firstInspection.verdict)
    check(correction.original_rationale).toBe(firstInspection.rationale)
    check(correction.verdict).toBe('defect')
    check(correction.defect_type).toBe('print')
    summary.records.correction_ids.push(correction.id)
    await check(page.locator('.reviewed-note')).toContainText(reviewer)
    return { correction_id: correction.id, sync_status: correction.sync_status, original_model_verdict: firstInspection.verdict, human_verdict: correction.verdict }
  })

  await step('different sample recalls and cites the saved correction', async () => {
    await page.getByRole('button', { name: 'Another marking', exact: true }).click()
    await setMemory(true)
    transferInspection = await liveAction('inspect', () => page.getByRole('button', { name: 'Inspect part', exact: true }).click(), { visionCalls: 1 })
    rememberInspection(transferInspection)
    check(transferInspection.sample_id).toBe('second-print')
    check(transferInspection.image_sha256 === firstInspection.image_sha256).toBe(false)
    check(transferInspection.source_group === firstInspection.source_group).toBe(false)
    check(transferInspection.memory_enabled).toBe(true)
    check(transferInspection.memory_status).toBe('recalled')
    check(transferInspection.memories.some(item => item.source_id === correction.id)).toBe(true)
    const citation = page.locator('.recalled-standard').filter({ hasText: rule })
    await check(citation).toContainText(shortId(correction.id))
    await check(citation).toContainText(reviewer)
    await screenshot('02-memory-correction-citation')
    return { inspection_id: transferInspection.id, observed_verdict: transferInspection.verdict, cited_correction_id: correction.id }
  })

  await step('Hindsight standards summary', async () => {
    await navigate('Quality memory')
    await check(page.locator('.standard-rule')).toHaveText(rule)
    const reflected = await liveAction('reflect', () => page.getByRole('button', { name: 'Summarize standards', exact: true }).click())
    check(typeof reflected.summary === 'string' && reflected.summary.trim().length > 0).toBe(true)
    await check(page.getByRole('heading', { name: 'What your inspector has learned', exact: true })).toBeVisible()
    await screenshot('03-hindsight-standards-summary')
    return { summary_present: true, synced_corrections: 1 }
  })

  await step('valid uploaded photo inspection', async () => {
    await navigate('Inspection desk')
    const filename = 'chief-skill-live-upload.jpg'
    await page.getByLabel('Upload part photo').setInputFiles({
      name: filename,
      mimeType: 'image/jpeg',
      buffer: await readFile(join(projectRoot, 'fixtures', 'parts', 'hazelnut_gen_03.jpg')),
    })
    await check(page.locator('.viewer-label')).toContainText(filename)
    await check(page.locator('.viewer-tag')).toHaveText('Uploaded image')
    await setMemory(false)
    uploadInspection = await liveAction('inspect', () => page.getByRole('button', { name: 'Inspect part', exact: true }).click(), { visionCalls: 1 })
    rememberInspection(uploadInspection)
    check(uploadInspection.filename).toBe(filename)
    check(uploadInspection.source_kind).toBe('upload')
    check(uploadInspection.memory_enabled).toBe(false)
    await screenshot('04-upload-inspection')
    return { inspection_id: uploadInspection.id, source_kind: uploadInspection.source_kind, observed_verdict: uploadInspection.verdict }
  })

  await step('unlabeled comparison and JSON export', async () => {
    await navigate('Memory comparison')
    await page.getByLabel('Choose comparison sample').selectOption('second-print')
    await page.getByLabel('Expected decision').selectOption({ label: 'Not labeled' })
    await check(page.getByLabel('Expected decision')).toHaveValue('')
    comparison = await liveAction('compare', () => page.getByRole('button', { name: 'Run comparison', exact: true }).click(), { visionCalls: 2 })
    rememberInspection(comparison.baseline)
    rememberInspection(comparison.with_memory)
    summary.records.comparison_ids.push(comparison.id)
    check(comparison.expected_verdict).toBeNull()
    check(comparison.baseline.image_sha256).toBe(comparison.with_memory.image_sha256)
    check(comparison.baseline.image_sha256).toBe(transferInspection.image_sha256)
    check(comparison.baseline.memory_enabled).toBe(false)
    check(comparison.with_memory.memory_enabled).toBe(true)
    check(comparison.with_memory.memories.some(item => item.source_id === correction.id)).toBe(true)
    check(comparison.held_out).toBe(true)
    await check(page.locator('.comparison-outcome')).toHaveCount(0)
    await check(page.locator('.comparison-history-row')).toHaveCount(1)
    const exported = await readDownload('Export comparison')
    check(exported.filename).toBe(`chief-skill-${comparison.id}.json`)
    check(exported.record.format_version).toBe(1)
    check(exported.record.id).toBe(comparison.id)
    check(exported.record.expected_verdict).toBeNull()
    check(exported.record.baseline.id).toBe(comparison.baseline.id)
    check(exported.record.with_memory.id).toBe(comparison.with_memory.id)
    await screenshot('05-unlabeled-comparison')
    return {
      comparison_id: comparison.id,
      expected_verdict: null,
      baseline_verdict: comparison.baseline.verdict,
      with_memory_verdict: comparison.with_memory.verdict,
      observed_decisions_differ: comparison.changed,
      held_out_from_correction: comparison.held_out,
      export_verified: true,
    }
  })

  await step('history search, complete export, and reopening after reload', async () => {
    await page.reload()
    await check(page.getByRole('button', { name: 'Inspect part', exact: true })).toBeEnabled()
    await navigate('Inspection history')
    await check(page.locator('tbody tr')).toHaveCount(5)
    const search = page.getByRole('searchbox', { name: 'Search inspection history' })
    await search.fill(reviewer)
    await check(page.locator('tbody tr')).toHaveCount(1)
    await check(page.locator('tbody tr')).toContainText('Reject')
    await search.fill('chief-skill-no-matching-record')
    await check(page.locator('tbody')).toContainText('No matching inspections')
    const exported = await readDownload('Export records')
    check(exported.filename).toBe('chief-skill-inspection-records.json')
    check(exported.record.format_version).toBe(1)
    check(exported.record.scope.factory).toBe(scope.factory)
    check(exported.record.inspections.length).toBe(5)
    check(exported.record.corrections.length).toBe(1)
    check(exported.record.comparisons.length).toBe(1)
    check(exported.record.inspections.map(item => item.id).sort()).toEqual([...summary.records.inspection_ids].sort())
    const savedCorrection = exported.record.corrections.find(item => item.id === correction.id)
    check(Boolean(savedCorrection)).toBe(true)
    check(savedCorrection.original_verdict).toBe(firstInspection.verdict)
    check(savedCorrection.original_rationale).toBe(firstInspection.rationale)
    check(savedCorrection.verdict).toBe('defect')
    await search.clear()
    await page.getByRole('button', { name: `Open inspection ${shortId(firstInspection.id)}`, exact: true }).click()
    await check(page.locator('.viewer-label')).toContainText(firstInspection.filename)
    await check(page.locator('.reviewed-note')).toContainText(reviewer)
    await check(page.getByRole('button', { name: 'Correct this decision', exact: true })).toHaveCount(0)
    await navigate('Memory comparison')
    await page.locator('.comparison-history-row').click()
    await check(page.locator('.compare-input strong')).toHaveText('second-print.jpg')
    await check(page.getByLabel('Expected decision')).toHaveValue('')
    await check(page.getByRole('button', { name: 'Run comparison', exact: true })).toBeDisabled()
    const reopened = await readDownload('Export comparison')
    check(reopened.record.id).toBe(comparison.id)
    check(reopened.record.expected_verdict).toBeNull()
    finalOverview = await requestJson(context.request, overviewPath())
    check(finalOverview.stats.inspections).toBe(5)
    check(finalOverview.stats.synced).toBe(1)
    return { inspections: 5, corrections: 1, comparisons: 1, filtered_export_keeps_all_records: true, saved_records_reopened: true }
  })
  }

  let deferredUiError
  try {
  if (!resumedFrom || resumePhase !== 'isolation') {
  await step('zoom, model outline, and settings focus and Escape', async () => {
    const withBox = finalOverview.inspections.find(item => Array.isArray(item.box_px) && item.box_px.length === 4)
    const selected = withBox || firstInspection
    await navigate('Inspection history')
    await page.getByRole('button', { name: `Open inspection ${shortId(selected.id)}`, exact: true }).click()
    const zoomIn = page.getByRole('button', { name: 'Zoom in', exact: true })
    const zoomOut = page.getByRole('button', { name: 'Zoom out', exact: true })
    await check(zoomOut).toBeDisabled()
    for (let count = 0; count < 4; count++) await zoomIn.click()
    await check(page.locator('.zoom-controls')).toContainText('200%')
    await check(page.locator('.part-image-wrap')).toHaveCSS('transform', 'matrix(2, 0, 0, 2, 0, 0)')
    await check(zoomIn).toBeDisabled()
    await zoomOut.click()
    await check(page.locator('.zoom-controls')).toContainText('175%')
    await page.getByRole('button', { name: 'Reset zoom', exact: true }).click()
    await check(page.locator('.zoom-controls')).toContainText('100%')
    await check(zoomOut).toBeDisabled()
    const outline = page.getByRole('button', { name: 'Defect outline', exact: true })
    if (withBox) {
      await check(page.getByLabel('Model defect location')).toBeVisible()
      await outline.click()
      await check(outline).toHaveAttribute('aria-pressed', 'false')
      await check(page.getByLabel('Model defect location')).toHaveCount(0)
      await outline.click()
      await check(outline).toHaveAttribute('aria-pressed', 'true')
      await check(page.getByLabel('Model defect location')).toBeVisible()
    } else {
      await check(outline).toBeDisabled()
      await check(page.getByLabel('Model defect location')).toHaveCount(0)
    }
    await checkSettings()
    await screenshot('06-viewer-controls')
    return { zoom_bounds_verified: true, outline_toggle_verified: Boolean(withBox), outline_disabled_without_model_box: !withBox, settings_focus_and_escape_verified: true }
  })

  await step('mobile navigation, settings, and horizontal overflow', async () => {
    const widths = []
    await page.setViewportSize({ width: 390, height: 844 })
    await navigate('Inspection desk')
    await page.getByRole('button', { name: 'Small hole', exact: true }).click()
    await check(page.locator('.viewer-label')).toContainText('Small hole')
    widths.push(await mobileWidth('Inspection desk'))
    await screenshot('07-mobile-inspection')
    await navigate('Quality memory')
    await check(page.locator('.standard-rule')).toHaveText(rule)
    await checkSettings()
    widths.push(await mobileWidth('Quality memory'))
    await screenshot('08-mobile-memory')
    await navigate('Inspection history')
    await check(page.locator('tbody tr')).toHaveCount(5)
    widths.push(await mobileWidth('Inspection history'))
    await screenshot('09-mobile-history')
    return { viewport: '390x844', navigation_verified: true, settings_verified: true, horizontal_overflow: false, widths }
  })
  }
  } catch (error) {
    // Keep checking independent browser isolation even if a layout assertion
    // fails; the failed check and original failure artifacts remain honest.
    deferredUiError = error
  }

  if (!resumedFrom || resumePhase !== 'mobile') {
  await step('second browser cannot read records, images, or corrections', async () => {
    secondContext = await browser.newContext({ baseURL, viewport: { width: 1280, height: 900 } })
    await secondContext.addInitScript(value => localStorage.setItem('speclens-scope', JSON.stringify(value)), scope)
    await requestJson(secondContext.request, '/api/workspace/status')
    const firstCookie = (await context.cookies()).find(item => item.name === 'chief_skill_workspace')
    const secondCookie = (await secondContext.cookies()).find(item => item.name === 'chief_skill_workspace')
    check(Boolean(secondCookie)).toBe(true)
    sensitiveValues.add(secondCookie.value)
    check(firstCookie.value === secondCookie.value).toBe(false)
    const isolated = await requestJson(secondContext.request, overviewPath())
    check(isolated.stats.inspections).toBe(0)
    check(isolated.inspections.length).toBe(0)
    check(isolated.corrections.length).toBe(0)
    check(isolated.comparisons.length).toBe(0)
    check(isolated.scope_id === finalOverview.scope_id).toBe(false)
    for (const image of finalOverview.inspections.map(item => item.image_url)) {
      const ownerResponse = await context.request.get(image, { timeout: LIVE_TIMEOUT })
      check(ownerResponse.status()).toBe(200)
      const otherResponse = await secondContext.request.get(image, { timeout: LIVE_TIMEOUT })
      check(otherResponse.status()).toBe(404)
    }
    const deniedCorrection = await secondContext.request.post('/api/workspace/corrections', {
      timeout: LIVE_TIMEOUT,
      data: { inspection_id: firstInspection.id, verdict: 'defect', defect_type: 'print', rule_text: rule, reviewer: 'Isolated browser' },
    })
    check(deniedCorrection.status()).toBe(404)
    const deniedSync = await secondContext.request.post(`/api/workspace/corrections/${encodeURIComponent(correction.id)}/sync`, {
      data: {}, timeout: LIVE_TIMEOUT,
    })
    check(deniedSync.status()).toBe(404)
    const recalledResponse = await secondContext.request.post('/api/workspace/recall', { data: scope, timeout: LIVE_TIMEOUT })
    if (!recalledResponse.ok()) throw new Error(`Isolated browser recall returned HTTP ${recalledResponse.status()}.`)
    check((await recalledResponse.json()).memories.length).toBe(0)
    const otherPage = await secondContext.newPage()
    otherPage.setDefaultTimeout(UI_TIMEOUT)
    await otherPage.goto('/')
    await check(otherPage.getByRole('button', { name: 'Inspect part', exact: true })).toBeEnabled()
    await navigate('Inspection history', otherPage)
    await check(otherPage.getByRole('heading', { name: 'A clear trail for every decision', exact: true })).toBeVisible()
    await check(otherPage.getByRole('button', { name: 'Export records', exact: true })).toBeDisabled()
    await screenshot('10-isolated-second-browser', otherPage)
    return { identical_scope_settings: true, records_visible: 0, private_images_denied: finalOverview.inspections.length, correction_write_status: 404, correction_sync_status: 404, recalled_standards: 0 }
  })
  }

  if (deferredUiError) throw deferredUiError
  check(summary.vision_calls.requested_estimate).toBe(resumedFrom ? 0 : 5)
  summary.status = 'passed'
} catch (error) {
  summary.status = 'failed'
  summary.failure = { step: summary.checks.find(item => item.status === 'failed')?.name || currentStep, message: safeMessage(error) }
  if (page && !page.isClosed()) {
    try { await screenshot('failure') } catch { /* Preserve the original failure. */ }
  }
  process.exitCode = 1
} finally {
  summary.finished_at = new Date().toISOString()
  try {
    await saveCheckpoint()
  } catch (error) {
    summary.status = 'failed'
    summary.artifact_error = safeMessage(error)
    process.exitCode = 1
    await writePrivateJson(summaryPath, summary)
  }
  await secondContext?.close().catch(() => {})
  await context?.close().catch(() => {})
  await browser?.close().catch(() => {})
  console.log(JSON.stringify({
    status: summary.status,
    artifact_dir: artifactDir,
    summary_path: summaryPath,
    persistence_path: persistencePath,
    storage_state_path: storageStatePath,
    vision_calls_requested_estimate: summary.vision_calls.requested_estimate,
  }, null, 2))
}
