import createClient, { type Middleware } from 'openapi-fetch'

import type { components, paths } from './schema'

export type Schemas = components['schemas']
export type User = Schemas['UserRead']
export type Run = Schemas['RunRead']
export type RunStep = Schemas['RunStepRead']
export type Remediation = Schemas['RemediationRead']

const TOKEN_KEY = 'copilot.token'

// sessionStorage: survives a reload, but not closing the tab, and isn't shared with other tabs.
export const tokenStore = {
  get: () => sessionStorage.getItem(TOKEN_KEY),
  set: (token: string) => sessionStorage.setItem(TOKEN_KEY, token),
  clear: () => sessionStorage.removeItem(TOKEN_KEY),
}

/** Raised for any non-2xx response; `message` is the API's error message. */
export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: Record<string, unknown> | null

  constructor(status: number, code: string, message: string, details: Record<string, unknown> | null) {
    super(message)
    this.status = status
    this.code = code
    this.details = details
  }
}

let onUnauthorized = () => {}

/** Called when the API rejects the session (expired or revoked token), so the app can return to the login page. */
export function setUnauthorizedHandler(handler: () => void) {
  onUnauthorized = handler
}

const auth: Middleware = {
  onRequest({ request }) {
    const token = tokenStore.get()
    if (token) request.headers.set('Authorization', `Bearer ${token}`)
    return request
  },
  async onResponse({ request, response }) {
    if (response.ok) return response
    // Every API error has the shape {"error": {"code", "message", "details"}}.
    const body = await response
      .clone()
      .json()
      .catch(() => null)
    const error = body?.error ?? { code: 'http_error', message: `Request failed (${response.status})` }
    if (response.status === 401 && !request.url.endsWith('/v1/auth/token')) onUnauthorized()
    throw new ApiError(response.status, error.code, error.message, error.details ?? null)
  },
}

export const api = createClient<paths>({ baseUrl: '' })
api.use(auth)
