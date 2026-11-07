// Copies the recorded demo and evaluation results into dist/ for the static hosted build.
import { cpSync, mkdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..')
const dist = resolve(root, 'frontend', 'dist-static', 'files')

mkdirSync(resolve(dist, 'fixtures'), { recursive: true })
for (const item of ['parts', 'demo_run', 'demo_inspect', 'demo_export.zip']) {
  cpSync(resolve(root, 'fixtures', item), resolve(dist, 'fixtures', item), { recursive: true })
}
cpSync(resolve(root, 'docs', 'results', 'eval.json'), resolve(dist, 'eval.json'))
console.log('copied demo fixtures and eval results into dist/files')
