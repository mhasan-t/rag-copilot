import { readFileSync } from 'node:fs'
import type { Page } from '@playwright/test'

export const SEED_FILE = 'test-results/e2e-seed.json'

export interface Seed {
  tag: string
  password: string
  superuser: string
  operator: string
  runs: { high_risk: string; low_risk: string; answered: string; failed: string }
}

export function seed(): Seed {
  return JSON.parse(readFileSync(SEED_FILE, 'utf8'))
}

export async function signIn(page: Page, email: string) {
  await page.goto('/')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill(seed().password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await page.getByRole('link', { name: 'Ask' }).waitFor()
}
