import { expect, test } from '@playwright/test'

import { seed, signIn } from './seed.ts'

test('wrong password shows an error and stays on the sign-in page', async ({ page }) => {
  await page.goto('/')
  await page.getByLabel('Email').fill(seed().operator)
  await page.getByLabel('Password').fill('not-the-password')
  await page.getByRole('button', { name: 'Sign in' }).click()

  await expect(page.getByRole('alert')).toHaveText('Invalid email or password')
})

test('runs list shows the seeded runs and opens one with its markdown answer and steps', async ({ page }) => {
  const { tag, operator } = seed()
  await signIn(page, operator)

  await page.getByRole('link', { name: 'Runs' }).click()
  await expect(page.getByRole('link', { name: new RegExp(tag) })).toHaveCount(4)
  await page.getByRole('link', { name: `[${tag}] How do I roll back a deployment?` }).click()

  await expect(page.getByText('completed', { exact: true })).toBeVisible()
  // Markdown is rendered, not shown raw.
  const answer = page.getByRole('region', { name: 'Answer' })
  await expect(answer.getByRole('strong')).toHaveText('Rolling back a deployment')
  await expect(answer.getByRole('listitem')).toHaveText([
    'Get superuser approval.',
    'Roll back to the previous revision.',
  ])
  // Each node is listed once, in the order it ran, with its LLM call nested under it.
  const timeline = page.getByRole('region', { name: 'What the copilot did' })
  await expect(timeline.locator('summary > span:first-child')).toHaveText([
    'classify',
    'llm',
    'retrieve_documents',
    'answer_knowledge',
    'llm',
  ])
  const step = page.getByRole('group').filter({ has: page.getByText('answer_knowledge', { exact: true }) })
  await expect(step.getByText('Output')).toBeHidden()
  await step.getByText('answer_knowledge', { exact: true }).click()
  await expect(step.getByText('Output')).toBeVisible()
})

test('a failed run shows why it failed', async ({ page }) => {
  await signIn(page, seed().operator)
  await page.goto(`/runs/${seed().runs.failed}`)

  await expect(page.getByRole('alert')).toHaveText('The run failed: LLM provider failed')
})

test('the asker cannot approve their own high-risk action, but can reject it', async ({ page }) => {
  await signIn(page, seed().operator)
  await page.goto(`/runs/${seed().runs.high_risk}`)
  await expect(page.getByRole('heading', { name: /Proposed action: Roll back payments/ })).toBeVisible()

  await page.getByRole('button', { name: 'Approve and run' }).click()
  await expect(page.getByRole('alert')).toHaveText('Not allowed to approve this high risk action')

  await page.getByLabel('Comment (optional)').fill('Investigating first')
  await page.getByRole('button', { name: 'Reject' }).click()
  await expect(page.getByText(/Rejected .*: “Investigating first”/)).toBeVisible()
  await expect(page.getByText('rejected').first()).toBeVisible()
})

test('a superuser approves a low-risk action from the queue and sees it verified', async ({ page }) => {
  const { tag, superuser, runs } = seed()
  await signIn(page, superuser)

  await page.getByRole('link', { name: /Approvals/ }).click()
  const card = page.locator('section').filter({ hasText: 'Proposed action: Scale payments to 2 replicas' })
  // Other proposals may be waiting in the dev database; act on the seeded one only.
  const seeded = page
    .locator('div')
    .filter({ has: card })
    .filter({ has: page.locator(`a[href="/runs/${runs.low_risk}"]`) })
    .last()
  await seeded.getByRole('button', { name: 'Approve and run' }).click()

  await page.goto(`/runs/${runs.low_risk}`)
  await expect(page.getByRole('heading', { name: `[${tag}] Is payments under-provisioned?` })).toBeVisible()
  // The action runs and its verification polls the real metrics; the page polls the run until it's done.
  await expect(page.getByText(/The service recovered/)).toBeVisible({ timeout: 45_000 })
  await expect(page.getByText('verified', { exact: true })).toBeVisible()
})

test('a superuser adds a user, who can then sign in', async ({ page }) => {
  const { tag, superuser, password } = seed()
  const email = `e2e-new-${tag}@example.com`
  await signIn(page, superuser)

  await page.getByRole('link', { name: 'Users' }).click()
  await page.getByLabel('Email').fill(email)
  await page.getByLabel(/Initial password/).fill(password)
  await page.getByRole('button', { name: 'Add user' }).click()
  await expect(page.getByText(email)).toBeVisible()

  await page.getByRole('button', { name: 'Sign out' }).click()
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill(password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByText(email)).toBeVisible()
  // Not a superuser: no user management.
  await expect(page.getByRole('link', { name: 'Users' })).toHaveCount(0)
})
