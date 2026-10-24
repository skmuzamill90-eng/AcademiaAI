
import type { AuthUser, Envelope, LoginType, Meta } from './types'

/**
 * API configuration:
 * - Production uses the Render backend URL.
 * - Local development uses the Vite proxy.
 * - VITE_API_BASE_URL overrides the default when configured.
 */
const configuredBase = (
  import.meta.env.VITE_API_BASE_URL ?? ''
).trim()

const BASE = (
  configuredBase ||
  (import.meta.env.DEV
    ? ''
    : 'https://academiaai-api-x1ke.onrender.com')
).replace(/\/+$/, '')

const SESSION_KEY = 'academia.session'

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

let token: string | null = null
let unauthorizedHandler: (() => void) | null = null

export const setToken = (value: string | null) => {
  token = value
}

export const onUnauthorized = (fn: (() => void) | null) => {
  unauthorizedHandler = fn
}

/**
 * Used by the import module for multipart uploads and file downloads.
 */
export const getToken = () => token

export const notifyUnauthorized = () => unauthorizedHandler?.()

export const apiUrl = (path: string) => `${BASE}${path}`

export function loadSession(): {
  token: string
  user: AuthUser
} | null {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function saveSession(
  session: { token: string; user: AuthUser } | null
) {
  try {
    if (session) {
      sessionStorage.setItem(SESSION_KEY, JSON.stringify(session))
    } else {
      sessionStorage.removeItem(SESSION_KEY)
    }
  } catch {
    // Storage unavailable: session lasts until reload.
  }
}

type Query = Record<
  string,
  string | number | null | undefined
>

const qs = (params?: Query) => {
  const entries = Object.entries(params ?? {}).filter(
    ([, value]) =>
      value !== undefined &&
      value !== null &&
      value !== ''
  )

  return entries.length
    ? `?${new URLSearchParams(
        entries.map(([key, value]) => [key, String(value)])
      )}`
    : ''
}

async function send(
  path: string,
  init: RequestInit = {},
  authed = true
): Promise<unknown> {
  const headers = new Headers(init.headers)

  if (authed && token) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  let res: Response

  try {
    res = await fetch(`${BASE}${path}`, {
      ...init,
      headers,
    })
  } catch {
    throw new ApiError(
      'Cannot connect to the AcademiaAI API. Check the backend URL, deployment status, and CORS configuration.',
      0
    )
  }

  let body: any = null

  try {
    body = await res.json()
  } catch {
    // Handled below if the response is not valid JSON.
  }

  if (!res.ok || body?.status === 'error') {
    if (res.status === 401 && authed) {
      unauthorizedHandler?.()
    }

    const detail =
      body?.error?.message ??
      (typeof body?.detail === 'string'
        ? body.detail
        : null)

    const fields = Array.isArray(body?.error?.details)
      ? body.error.details
          .map(
            (item: { field: string; message: string }) =>
              `${item.field}: ${item.message}`
          )
          .join('; ')
      : ''

    throw new ApiError(
      [detail, fields].filter(Boolean).join(' — ') ||
        `Request failed (${res.status}).`,
      res.status
    )
  }

  if (body === null) {
    throw new ApiError(
      `The server returned an unreadable response (${res.status}).`,
      res.status
    )
  }

  return body
}

export async function get<T>(
  path: string,
  params?: Query
): Promise<{ data: T; meta: Meta }> {
  const body = (await send(
    `${path}${qs(params)}`
  )) as Envelope<T>

  return {
    data: body.data,
    meta: body.meta ?? {},
  }
}

export async function write<T>(
  method: 'POST' | 'PATCH',
  path: string,
  payload: unknown
): Promise<T> {
  const body = (await send(path, {
    method,
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  })) as Envelope<T>

  return body.data
}

export async function login(
  username: string,
  password: string,
  loginType: LoginType
): Promise<{ token: string; user: AuthUser }> {
  const body = (await send(
    '/api/auth/login',
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: new URLSearchParams({
        username,
        password,
        login_type: loginType,
      }),
    },
    false
  )) as {
    access_token: string
    user: AuthUser
  }

  return {
    token: body.access_token,
    user: body.user,
  }
}

/**
 * Fetches every page of a list endpoint (used for CSV export).
 */
export async function getAll<T>(
  path: string,
  params: Query = {},
  pageSize = 200
): Promise<T[]> {
  const out: T[] = []

  for (let offset = 0; ; offset += pageSize) {
    const { data, meta } = await get<T[]>(path, {
      ...params,
      limit: pageSize,
      offset,
    })

    out.push(...data)

    if (!meta.has_more || data.length === 0) {
      return out
    }
  }
}

export async function setupPassword(
  token: string,
  new_password: string
): Promise<void> {
  await send(
    '/api/auth/setup',
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        token,
        new_password,
      }),
    },
    false
  )
}
