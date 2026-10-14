import { execFileSync } from 'node:child_process'
import { mkdirSync, writeFileSync } from 'node:fs'

import { SEED_FILE } from './seed.ts'

/** Creates users and runs in the dev stack with the API's seeding script (see api/tests/e2e_seed.py). */
export default function globalSetup() {
  const output = execFileSync(
    'docker',
    [
      'compose',
      '--env-file',
      '.env',
      '-f',
      'docker-compose.dev.yaml',
      'exec',
      '-T',
      'api',
      'python',
      '-m',
      'tests.e2e_seed',
    ],
    { cwd: '..', encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] },
  )
  mkdirSync('test-results', { recursive: true })
  writeFileSync(SEED_FILE, output.trim().split('\n').at(-1)!)
}
