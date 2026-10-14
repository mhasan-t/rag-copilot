/** Approving the seeded scale proposal really scales the demo service; put it back. */
export default async function globalTeardown() {
  await fetch('http://localhost:8001/admin/deployments/payments/scale', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ replicas: 1 }),
  })
}
