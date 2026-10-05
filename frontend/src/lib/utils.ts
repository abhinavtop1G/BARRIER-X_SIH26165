import { clsx, type ClassValue } from 'clsx'

export function cn(...inputs: ClassValue[]) {
  return clsx(inputs)
}

export function decodeGoogleJwt(token: string): Record<string, unknown> {
  const base64 = token.split('.')[1]
  const decoded = atob(base64.replace(/-/g, '+').replace(/_/g, '/'))
  return JSON.parse(decoded) as Record<string, unknown>
}
