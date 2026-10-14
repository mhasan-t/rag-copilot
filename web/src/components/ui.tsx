import { useId, type ButtonHTMLAttributes, type ReactNode } from 'react'

import { ApiError } from '../api/client'

type Tone = 'ok' | 'warn' | 'danger' | 'info' | 'neutral'

// Full class names (not built from `tone`), so Tailwind can find them when scanning the source.
const TONE_CLASSES: Record<Tone, string> = {
  ok: 'bg-ok-soft text-ok',
  warn: 'bg-warn-soft text-warn',
  danger: 'bg-danger-soft text-danger',
  info: 'bg-info-soft text-info',
  neutral: 'bg-neutral-soft text-neutral',
}

const STATUS_TONES: Record<string, Tone> = {
  // runs
  running: 'info',
  awaiting_approval: 'warn',
  completed: 'ok',
  // remediations
  proposed: 'warn',
  approved: 'info',
  executing: 'info',
  verified: 'ok',
  unverified: 'warn',
  // both
  rejected: 'neutral',
  failed: 'danger',
  // risk levels
  low: 'neutral',
  high: 'danger',
  // explicit tones, for badges that aren't statuses
  info: 'info',
  neutral: 'neutral',
}

/** A coloured label for a status, risk level or tone name; `label` overrides the text shown. */
export function Badge({ value, label }: { value: string; label?: string }) {
  const tone = STATUS_TONES[value] ?? 'neutral'
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${TONE_CLASSES[tone]}`}>
      {label ?? value.replaceAll('_', ' ')}
    </span>
  )
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'danger' }

const BUTTON_CLASSES = {
  primary: 'bg-brand text-white hover:bg-brand-hover',
  secondary: 'border border-border bg-surface hover:bg-canvas',
  danger: 'bg-danger text-white hover:opacity-90',
}

export function Button({ variant = 'primary', className = '', ...props }: ButtonProps) {
  return (
    <button
      className={`rounded-md px-3 py-1.5 text-sm font-medium focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:cursor-not-allowed disabled:opacity-50 ${BUTTON_CLASSES[variant]} ${className}`}
      {...props}
    />
  )
}

export function Card({ title, actions, children }: { title?: ReactNode; actions?: ReactNode; children: ReactNode }) {
  const headingId = useId()
  // Labelled by its heading, a titled card is a named landmark region screen-reader users can jump to.
  return (
    <section
      aria-labelledby={title ? headingId : undefined}
      className="rounded-lg border border-border bg-surface p-4 shadow-sm"
    >
      {(title || actions) && (
        <div className="mb-3 flex items-center justify-between gap-2">
          {title && (
            <h2 id={headingId} className="text-sm font-semibold">
              {title}
            </h2>
          )}
          {actions}
        </div>
      )}
      {children}
    </section>
  )
}

/** Shows an error from a failed request; renders nothing when there is none. */
export function ErrorMessage({ error }: { error: unknown }) {
  if (!error) return null
  const message = error instanceof ApiError || error instanceof Error ? error.message : 'Something went wrong'
  return (
    <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger">
      {message}
    </p>
  )
}

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return (
    <p role="status" className="p-4 text-sm text-muted">
      {label}
    </p>
  )
}

export const inputClasses =
  'w-full rounded-md border border-border bg-surface px-3 py-2 text-sm focus-visible:outline-2 focus-visible:outline-brand'

/** A timestamp in the reader's locale, keeping the exact time machine-readable. */
export function Time({ value }: { value: string }) {
  return <time dateTime={value}>{new Date(value).toLocaleString()}</time>
}
