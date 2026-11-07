#!/usr/bin/env node
/**
 * Actual, narrated SpecLens recording; never starts the mocked test server.
 *
 * Prepare locally without contacting the app:
 *   node frontend/scripts/record-demo.mjs --prepare-only
 * Record after the live deployment is confirmed ready:
 *   SPECLENS_DEMO_READY=1 node frontend/scripts/record-demo.mjs
 * Repeat an interrupted render without another model call:
 *   node frontend/scripts/record-demo.mjs --render-only --dir var/submission/<run>
 *
 * Uses four logical vision calls: baseline, different part, and two comparison
 * arms. macOS `say`, ffmpeg, ffprobe, and Playwright Chromium are required.
 */
import { chromium, expect } from '@playwright/test'
import { spawn } from 'node:child_process'
import { randomUUID } from 'node:crypto'
import { chmod, mkdir, readFile, writeFile } from 'node:fs/promises'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const args = process.argv.slice(2)
const prepareOnly = args.includes('--prepare-only')
const renderOnly = args.includes('--render-only')
const directoryIndex = args.indexOf('--dir')
if (directoryIndex !== -1 && !args[directoryIndex + 1]) throw new Error('--dir needs an output directory.')
const runId = `${new Date().toISOString().replace(/[:.]/g, '-')}-${randomUUID().slice(0, 6)}`
const output = directoryIndex === -1 ? join(projectRoot, 'var', 'submission', `speclens-demo-${runId}`) : resolve(args[directoryIndex + 1])
const voice = process.env.SPECLENS_DEMO_VOICE || 'Karen'
const target = new URL(process.env.SPECLENS_BASE_URL || 'https://speclens.pallabdas.me')
if (!['http:', 'https:'].includes(target.protocol) || target.username || target.password) throw new Error('Use an HTTP(S) product URL without embedded credentials.')
const baseURL = target.origin
const check = expect.configure({ timeout: 30_000 })
const scope = { factory: `SpecLens recording ${new Date().toISOString().slice(0, 16).replace('T', ' ')}`, part_family: 'Whole hazelnut', spec_text: '' }
const rule = 'Sharp white printed characters on the shell are ink. Reject them as print defects. Broad, smooth natural highlights alone remain acceptable.'
const reviewer = 'SpecLens demo reviewer'
const segments = []
const secretValues = new Set()
let visionCalls = 0
let browser
let context
let page
let epoch = 0
let lastSceneEnd = 0
let baseline
let correction
let transfer
let comparison
let recordedVideo
let rawVideo

const chapters = [
  { id: '01-introduction', title: 'A correction the next inspection can recall', caption: 'SpecLens · real Meta vision + Hindsight memory', seconds: 18,
    text: 'A visual inspector can read a specification and still need a quality engineer’s judgment. SpecLens turns that review into a standard the next inspection can recall. This is the live application, using real Meta vision and Hindsight memory. The sample photos are generated, with controlled ink overlays.' },
  { id: '02-baseline', title: 'Establish the model’s own decision', caption: 'White marking · quality memory OFF · unchanged base specification', seconds: 16,
    text: 'First, I choose the white marking sample and turn quality memory off. The vision model sees the photo and the base specification, without a learned correction. We keep its actual verdict and explanation rather than forcing a particular answer.' },
  { id: '03-observed-baseline', title: 'Read the observed result', caption: 'The original decision and reasoning remain on record', seconds: 12, dynamic: true },
  { id: '04-teach', title: 'Teach a precise visual standard', caption: 'Human review · reject print · retain the source correction in Hindsight', seconds: 25,
    text: 'The quality engineer records the human standard: sharp white printed characters are ink, while broad natural highlights alone remain acceptable. I explicitly choose reject and the print class, then save the correction. SpecLens keeps the original model reasoning beside this human decision and sends the correction to Hindsight.' },
  { id: '05-different-part', title: 'Inspect a different source photo', caption: 'Another marking · quality memory ON · no reuse of the teaching image', seconds: 16,
    text: 'Now I select another marking, from a different source photo, and enable quality memory. The base specification stays the same. Hindsight retrieves relevant standards before the model inspects this new part.' },
  { id: '06-citation', title: 'Follow the recalled correction', caption: 'A source correction ID connects the standard to the later inspection', seconds: 17, dynamic: true },
  { id: '07-compare', title: 'One part, two real inspections', caption: 'Same image, model, and specification · only recalled memory changes', seconds: 16,
    text: 'The comparison runs this second part twice, once without memory and once with it. Both arms use the same image, model, and base specification. I leave the expected decision unlabeled so the screen does not imply a measured score.' },
  { id: '08-observed-comparison', title: 'Report both outcomes honestly', caption: 'One paired observation · no general accuracy claim', seconds: 16, dynamic: true },
  { id: '09-memory', title: 'Review what the team has taught', caption: 'Hindsight reflect summarizes standards with their supporting correction', seconds: 18,
    text: 'Quality memory shows the saved rule, reviewer, original inspection reasoning, and confirmed sync state. Summarize standards asks Hindsight to reflect over this workspace’s corrections. The summary supports review; the source correction remains the traceable record.' },
  { id: '10-history', title: 'Keep an audit trail across reloads', caption: 'Original model call + human decision + recalled standards · exportable JSON', seconds: 19,
    text: 'History keeps all four inspection records, including the two comparison arms. I can search by reviewer and export the complete workspace as JSON. After a reload, the original decision, human correction, and saved comparison are still here.' },
  { id: '11-scope', title: 'Keep each standard in its context', caption: 'Factory + part family + specification revision define the memory scope', seconds: 13,
    text: 'Workspace settings make the context explicit. The factory, part family, and exact specification revision define a separate memory bank. Changing the specification starts a new scope. Credentials stay on the server; people remain responsible for disposition.' },
  { id: '12-close', title: 'From human review to cited memory', caption: 'Try speclens.pallabdas.me · source: github.com/PDGamerSG/speclens', seconds: 13,
    text: 'The useful part is the traceable correction: what the model said, what the engineer recorded, and which later inspection used that standard. Explore SpecLens at the public app, or review the source and verification material on GitHub.' },
]

function run(command, commandArgs, options = {}) {
  return new Promise((resolveRun, rejectRun) => {
    const child = spawn(command, commandArgs, { cwd: projectRoot, stdio: ['ignore', 'pipe', 'pipe'], ...options })
    let stdout = ''
    let stderr = ''
    child.stdout?.on('data', data => { stdout += data })
    child.stderr?.on('data', data => { stderr = (stderr + data).slice(-6000) })
    child.on('error', rejectRun)
    child.on('close', code => code === 0 ? resolveRun(stdout) : rejectRun(new Error(`${command} exited ${code}: ${stderr.slice(-1800)}`)))
  })
}

async function privateJson(path, value) {
  await writeFile(path, `${JSON.stringify(value, null, 2)}\n`, { mode: 0o600 })
  await chmod(path, 0o600)
}

function safeError(error) {
  let text = error instanceof Error ? error.message : String(error)
  for (const secret of secretValues) text = text.split(secret).join('[redacted]')
  return text.replace(/\b[a-f0-9]{64}\b/gi, '[redacted]').slice(0, 2400)
}

async function probe(path) {
  return JSON.parse(await run('ffprobe', ['-v', 'error', '-show_entries', 'format=duration:stream=codec_type,codec_name,width,height,sample_rate', '-of', 'json', path]))
}

async function speech(chapter) {
  const textPath = join(output, `${chapter.id}.txt`)
  const audio = join(output, `${chapter.id}.aiff`)
  await writeFile(textPath, chapter.text, { mode: 0o600 })
  await run('say', ['-v', voice, '-r', '158', '-f', textPath, '-o', audio])
  await chmod(audio, 0o600)
  return { audio, audioSeconds: Number((await probe(audio)).format.duration) }
}

async function captionImage(chapter, index) {
  const canvas = await browser.newPage({ viewport: { width: 1920, height: 160 } })
  await canvas.setContent('<!doctype html><html><head><style>*{box-sizing:border-box}body{margin:0;width:1920px;height:160px;background:#102d33;color:#f5f4ed;font-family:Arial,sans-serif;display:flex;align-items:center;padding:25px 58px;gap:32px}.number{color:#9cdbcb;font-size:29px;border-right:2px solid #42656a;padding-right:29px;font-weight:700;letter-spacing:1px}.text{display:grid;gap:12px}h1{margin:0;font-size:36px;letter-spacing:-.5px;font-weight:700}p{margin:0;font-size:25px;color:#c4ded8;line-height:1.3}</style></head><body><div class="number"></div><div class="text"><h1></h1><p></p></div></body></html>')
  await canvas.evaluate(({ number, title, caption }) => {
    document.querySelector('.number').textContent = number
    document.querySelector('h1').textContent = title
    document.querySelector('p').textContent = caption
  }, { number: `${String(index + 1).padStart(2, '0')} / 12`, title: chapter.title, caption: chapter.caption })
  const path = join(output, `${chapter.id}-caption.png`)
  await canvas.screenshot({ path })
  await chmod(path, 0o600)
  await canvas.close()
  return path
}

async function stage(chapter, index, action = async () => {}) {
  const narration = await speech(chapter)
  const caption = await captionImage(chapter, index)
  const start = (Date.now() - epoch) / 1000
  await action()
  const desired = Math.max(chapter.seconds, narration.audioSeconds + 0.9)
  const remaining = desired * 1000 - (Date.now() - epoch - start * 1000)
  if (remaining > 0) await new Promise(resolvePause => setTimeout(resolvePause, remaining))
  const end = (Date.now() - epoch) / 1000
  lastSceneEnd = end
  segments.push({ ...chapter, ...narration, captionImage: caption, start, duration: end - start })
  await checkpoint()
  console.log(JSON.stringify({ chapter: index + 1, recorded: chapter.title, vision_calls: visionCalls }))
}

async function live(endpoint, click, calls = 0, expectedStatus = 200) {
  if (visionCalls + calls > 5) throw new Error('The five-call vision budget would be exceeded.')
  visionCalls += calls
  const waiting = page.waitForResponse(response => new URL(response.url()).pathname === `/api/workspace/${endpoint}` && response.request().method() === 'POST', { timeout: 240_000 })
  const [response] = await Promise.all([waiting, click()])
  if (response.status() !== expectedStatus) throw new Error(`Live ${endpoint} returned HTTP ${response.status()}.`)
  const value = await response.json()
  if (value.owner_id) secretValues.add(value.owner_id)
  return value
}

async function go(name, id) {
  await page.getByRole('button', { name, exact: true }).click()
  const section = page.locator(`#${id}`)
  if (await section.count()) await section.evaluate(element => element.scrollIntoView({ block: 'start', behavior: 'instant' }))
  else await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }))
}

async function memory(enabled) {
  const toggle = page.getByRole('switch', { name: 'Use quality memory' })
  if ((await toggle.getAttribute('aria-checked')) !== String(enabled)) await toggle.click()
  await check(toggle).toHaveAttribute('aria-checked', String(enabled))
}

async function settleResult() {
  await check(page.locator('.decision-result')).toBeVisible()
  await page.getByRole('button', { name: 'Inspect again', exact: true }).waitFor({ state: 'visible' })
  const stage = page.locator('.image-stage')
  if (await stage.getAttribute('data-phase')) await check(stage).toHaveAttribute('data-phase', 'rest')
}

const verdict = value => value === 'good' ? 'accepted the part' : value === 'defect' ? 'rejected the part' : 'requested human review'

async function checkpoint(extra = {}) {
  if (context) await privateJson(join(output, 'storage-state.private.json'), await context.storageState())
  await privateJson(join(output, 'recording.private.json'), {
    format_version: 1, base_url: baseURL, scope, voice, vision_calls: visionCalls,
    raw_video: rawVideo, raw_epoch: epoch, capture_end: lastSceneEnd, segments,
    observed: {
      baseline: baseline ? { id: baseline.id, verdict: baseline.verdict, rationale: baseline.rationale } : null,
      correction: correction ? { id: correction.id, inspection_id: correction.inspection_id, sync_status: correction.sync_status } : null,
      transfer: transfer ? { id: transfer.id, verdict: transfer.verdict, cites_correction: transfer.memories.some(item => item.source_id === correction?.id) } : null,
      comparison: comparison ? { id: comparison.id, baseline_verdict: comparison.baseline.verdict, memory_verdict: comparison.with_memory.verdict, expected_verdict: comparison.expected_verdict, held_out: comparison.held_out } : null,
    }, ...extra,
  })
}

function timecode(seconds, milliseconds = false) {
  const whole = Math.floor(seconds)
  const value = `${String(Math.floor(whole / 3600)).padStart(2, '0')}:${String(Math.floor(whole / 60) % 60).padStart(2, '0')}:${String(whole % 60).padStart(2, '0')}`
  return milliseconds ? `${value},${String(Math.floor(seconds % 1 * 1000)).padStart(3, '0')}` : value
}

async function render(manifest) {
  if (!manifest.raw_video || !manifest.segments?.length) throw new Error('No completed recording is available to render.')
  let timeline = 0
  let cue = 0
  const subtitles = []
  const transcript = ['# SpecLens — a correction the next inspection can recall', '', `Recorded from ${manifest.base_url}. Real Meta vision and Hindsight retain, recall, and reflect.`, '', 'The sample photos are generated; white markings are controlled overlays. This recording reports observed outcomes and makes no general accuracy claim.', '']
  const clips = []
  for (const [index, segment] of manifest.segments.entries()) {
    const clip = join(output, `${segment.id}.mp4`)
    await run('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', '-ss', segment.start.toFixed(3), '-i', manifest.raw_video,
      '-loop', '1', '-i', segment.captionImage, '-i', segment.audio,
      '-filter_complex', '[0:v]scale=1920:920:flags=lanczos,pad=1920:1080:0:0:color=0x102d33[base];[base][1:v]overlay=0:920:shortest=1[v]',
      '-map', '[v]', '-map', '2:a:0', '-af', 'apad', '-t', segment.duration.toFixed(3),
      '-c:v', 'libx264', '-preset', 'fast', '-crf', '20', '-pix_fmt', 'yuv420p', '-r', '30',
      '-c:a', 'aac', '-b:a', '160k', '-ar', '48000', '-movflags', '+faststart', clip])
    clips.push(clip)
    transcript.push(`## ${timecode(timeline)} — ${segment.title}`, '', segment.text, '')
    const words = segment.text.split(/\s+/)
    for (let offset = 0; offset < words.length; offset += 12) {
      const chunk = words.slice(offset, offset + 12)
      const start = timeline + offset / words.length * segment.audioSeconds
      const end = timeline + Math.min(offset + chunk.length, words.length) / words.length * segment.audioSeconds
      subtitles.push(`${++cue}\n${timecode(start, true)} --> ${timecode(end, true)}\n${chunk.join(' ')}\n`)
    }
    timeline += segment.duration
    console.log(JSON.stringify({ rendered_chapter: index + 1, seconds: Number(timeline.toFixed(1)) }))
  }
  if (timeline < 120 || timeline > 300) throw new Error(`Recorded timeline ${timeline.toFixed(1)}s is outside the requested two-to-five-minute range.`)
  const concatPath = join(output, 'scenes.txt')
  const subtitlePath = join(output, 'SpecLens-demo-English.srt')
  const transcriptPath = join(output, 'SpecLens-demo-transcript.md')
  await writeFile(concatPath, clips.map(path => `file '${path.replaceAll("'", "'\\''")}'`).join('\n'), { mode: 0o600 })
  await writeFile(subtitlePath, subtitles.join('\n'), { mode: 0o600 })
  await writeFile(transcriptPath, transcript.join('\n'), { mode: 0o600 })
  const joined = join(output, 'SpecLens-demo-joined.mp4')
  const finalVideo = join(output, 'SpecLens-demo-1080p.mp4')
  await run('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', concatPath, '-c', 'copy', joined])
  await run('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', '-i', joined, '-i', subtitlePath, '-map', '0:v', '-map', '0:a', '-map', '1:0', '-c', 'copy', '-c:s', 'mov_text', '-metadata:s:s:0', 'language=eng', '-movflags', '+faststart', finalVideo])
  const metadata = await probe(finalVideo)
  const videoStream = metadata.streams.find(stream => stream.codec_type === 'video')
  const audioStream = metadata.streams.find(stream => stream.codec_type === 'audio')
  check(videoStream.width).toBe(1920)
  check(videoStream.height).toBe(1080)
  check(Boolean(audioStream)).toBe(true)
  check(Number(metadata.format.duration)).toBeGreaterThanOrEqual(120)
  check(Number(metadata.format.duration)).toBeLessThanOrEqual(300)
  for (const [index, second] of [8, timeline * 0.35, timeline * 0.6, timeline - 7].entries()) {
    await run('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', '-ss', second.toFixed(2), '-i', finalVideo, '-frames:v', '1', join(output, `review-frame-${index + 1}.png`)])
  }
  await privateJson(join(output, 'video-verification.json'), { status: 'passed', base_url: manifest.base_url, vision_calls: manifest.vision_calls, duration_seconds: Number(metadata.format.duration), width: videoStream.width, height: videoStream.height, audio: audioStream.codec_name, chapters: manifest.segments.length, observed: manifest.observed, note: 'Observed live results; no forced miss or general accuracy claim.' })
  await chmod(finalVideo, 0o600)
  console.log(JSON.stringify({ status: 'ready', video: finalVideo, transcript: transcriptPath, subtitles: subtitlePath, verification: join(output, 'video-verification.json'), duration_seconds: Number(metadata.format.duration), resolution: '1920x1080' }, null, 2))
}

await mkdir(output, { recursive: true, mode: 0o700 })
await chmod(output, 0o700)

if (renderOnly) {
  await render(JSON.parse(await readFile(join(output, 'recording.private.json'), 'utf8')))
} else if (prepareOnly) {
  browser = await chromium.launch({ headless: true })
  try {
    for (const [index, chapter] of chapters.entries()) {
      if (!chapter.dynamic) await speech(chapter)
      await captionImage(chapter, index)
    }
    await writeFile(join(output, 'storyboard-draft.md'), chapters.map(chapter => `## ${chapter.title}\n\n${chapter.text || 'Narration will state the actual observed live outcome.'}\n`).join('\n'), { mode: 0o600 })
    console.log(JSON.stringify({ status: 'prepared-offline', output, planned_vision_calls: 4, note: 'No app or provider requests made.' }, null, 2))
  } finally { await browser.close() }
} else {
  if (process.env.SPECLENS_DEMO_READY !== '1') throw new Error('Wait for the live deployment to be confirmed ready, then set SPECLENS_DEMO_READY=1.')
  try {
    browser = await chromium.launch({ headless: true })
    context = await browser.newContext({ baseURL, viewport: { width: 1920, height: 920 }, recordVideo: { dir: output, size: { width: 1920, height: 920 } }, acceptDownloads: true })
    await context.addInitScript(value => localStorage.setItem('speclens-scope', JSON.stringify(value)), scope)
    const status = await context.request.get('/api/workspace/status', { timeout: 30_000 })
    check(status.ok()).toBe(true)
    const connections = await status.json()
    check(connections.model_configured).toBe(true)
    check(connections.memory_configured).toBe(true)
    for (const cookie of await context.cookies()) secretValues.add(cookie.value)
    page = await context.newPage()
    epoch = Date.now()
    recordedVideo = page.video()
    rawVideo = await recordedVideo.path()
    page.setDefaultTimeout(30_000)
    await page.goto('/')
    await check(page.getByRole('button', { name: 'Inspect part', exact: true })).toBeEnabled()
    await page.evaluate(() => document.fonts.ready)
    await stage(chapters[0], 0)
    await stage(chapters[1], 1, async () => {
      await page.getByRole('button', { name: 'White marking', exact: true }).click()
      await memory(false)
      baseline = await live('inspect', () => page.getByRole('button', { name: 'Inspect part', exact: true }).click(), 1)
      check(baseline.memory_enabled).toBe(false)
      await settleResult()
    })
    chapters[2].text = `The live model ${verdict(baseline.verdict)}. ${baseline.verdict === 'defect' ? 'It already identified a defect, so this is not a manufactured failure.' : 'The quality engineer can now make the print standard explicit.'} Its original explanation remains on this ticket and in the audit record.`
    await stage(chapters[2], 2)
    await stage(chapters[3], 3, async () => {
      await page.getByRole('button', { name: 'Correct this decision', exact: true }).click()
      await page.getByRole('radio', { name: 'Reject part', exact: true }).check()
      await page.getByLabel('Defect class').selectOption('print')
      await page.getByLabel('What should the inspector learn?').pressSequentially(rule, { delay: 24 })
      await page.getByLabel('Reviewed by').fill(reviewer)
      correction = await live('corrections', () => page.getByRole('button', { name: 'Save correction & remember', exact: true }).click(), 0, 201)
      check(correction.sync_status).toBe('synced')
      check(correction.original_verdict).toBe(baseline.verdict)
      await check(page.locator('.reviewed-note')).toContainText(reviewer)
    })
    await stage(chapters[4], 4, async () => {
      await page.getByRole('button', { name: 'Another marking', exact: true }).click()
      await memory(true)
      transfer = await live('inspect', () => page.getByRole('button', { name: 'Inspect part', exact: true }).click(), 1)
      check(transfer.image_sha256 === baseline.image_sha256).toBe(false)
      check(transfer.source_group === baseline.source_group).toBe(false)
      check(transfer.memories.some(item => item.source_id === correction.id)).toBe(true)
      await settleResult()
    })
    chapters[5].text = `On the second photo, the live model ${verdict(transfer.verdict)}. This inspection cites the exact human correction saved a moment ago. Hindsight supplied the standard, and the base specification stayed fixed. A cited memory is an observed retrieval step even when the model reaches the same verdict.`
    await stage(chapters[5], 5, async () => {
      await page.locator('.recalled-standard').filter({ hasText: rule }).scrollIntoViewIfNeeded()
      await check(page.locator('.recalled-standard').filter({ hasText: rule })).toBeVisible()
    })
    await stage(chapters[6], 6, async () => {
      await go('Memory comparison', 'compare')
      await page.getByLabel('Choose comparison sample').selectOption('second-print')
      await page.getByLabel('Expected decision').selectOption({ label: 'Not labeled' })
      comparison = await live('compare', () => page.getByRole('button', { name: 'Run comparison', exact: true }).click(), 2)
      check(comparison.expected_verdict).toBeNull()
      check(comparison.baseline.image_sha256).toBe(comparison.with_memory.image_sha256)
      check(comparison.with_memory.memories.some(item => item.source_id === correction.id)).toBe(true)
      await check(page.locator('.comparison-arm')).toHaveCount(2)
    })
    chapters[7].text = `Without memory, the model ${verdict(comparison.baseline.verdict)}. With memory, it ${verdict(comparison.with_memory.verdict)}. ${comparison.changed ? 'Those are the observed decisions for this pair.' : 'Both arms reached the same verdict in this run.'} This is one paired observation, not a general accuracy claim. The memory-enabled arm records the correction it used.`
    await stage(chapters[7], 7, async () => { await page.locator('.comparison-arm').first().scrollIntoViewIfNeeded() })
    await stage(chapters[8], 8, async () => {
      await go('Quality memory', 'standards')
      const reflected = await live('reflect', () => page.getByRole('button', { name: 'Summarize standards', exact: true }).click())
      check(typeof reflected.summary === 'string' && reflected.summary.length > 0).toBe(true)
      await check(page.getByRole('heading', { name: 'What your inspector has learned', exact: true })).toBeVisible()
    })
    await stage(chapters[9], 9, async () => {
      await go('Inspection history', 'history')
      await check(page.locator('tbody tr')).toHaveCount(4)
      const search = page.getByRole('searchbox', { name: 'Search inspection history' })
      await search.fill(reviewer)
      await check(page.locator('tbody tr')).toHaveCount(1)
      await search.clear()
      const downloadPending = page.waitForEvent('download')
      await page.getByRole('button', { name: 'Export records', exact: true }).click()
      const download = await downloadPending
      const exported = JSON.parse(await readFile(await download.path(), 'utf8'))
      check(exported.inspections.length).toBe(4)
      check(exported.corrections[0].id).toBe(correction.id)
      await download.delete()
      await page.reload()
      await check(page.getByRole('button', { name: 'Inspect part', exact: true })).toBeEnabled()
      await go('Inspection history', 'history')
      await check(page.locator('tbody tr')).toHaveCount(4)
    })
    await stage(chapters[10], 10, async () => {
      await page.getByRole('button', { name: 'Workspace settings', exact: true }).first().click()
      await check(page.getByRole('dialog', { name: 'Workspace settings' })).toBeVisible()
    })
    await page.keyboard.press('Escape')
    await stage(chapters[11], 11, async () => {
      const short = transfer.id.replace(/^insp-/, '').slice(0, 8).toUpperCase()
      await page.getByRole('button', { name: `Open inspection ${short}`, exact: true }).click()
      const section = page.locator('#inspect')
      if (await section.count()) await section.evaluate(element => element.scrollIntoView({ block: 'start', behavior: 'instant' }))
      else await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }))
    })
    check(visionCalls).toBe(4)
    await checkpoint({ status: 'recorded' })
    await context.close()
    context = null
    await browser.close()
    browser = null
    await chmod(rawVideo, 0o600)
    await render(JSON.parse(await readFile(join(output, 'recording.private.json'), 'utf8')))
  } catch (error) {
    if (page && !page.isClosed()) await page.screenshot({ path: join(output, 'recording-failure.png') }).catch(() => {})
    await checkpoint({ status: 'failed', error: safeError(error) }).catch(() => {})
    await context?.close().catch(() => {})
    await browser?.close().catch(() => {})
    console.error(JSON.stringify({ status: 'failed', output, vision_calls: visionCalls, error: safeError(error) }, null, 2))
    process.exitCode = 1
  }
}
