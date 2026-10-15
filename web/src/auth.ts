import { useSyncExternalStore } from 'react'
import { AuthClient } from './auth/client'

const KEY = 'ragcat-dev-user'

export function devUser(): string {
  try {
    return localStorage.getItem(KEY) || 'demo'
  } catch {
    return 'demo'
  }
}

export function setDevUser(name: string): void {
  try {
    localStorage.setItem(KEY, name)
  } catch {
    /* private mode: keep the default */
  }
}

export const auth = new AuthClient({
  development: import.meta.env.DEV,
  storage: {
    getItem: (key) => window.sessionStorage.getItem(key),
    setItem: (key, value) => window.sessionStorage.setItem(key, value),
    removeItem: (key) => window.sessionStorage.removeItem(key),
  },
  fetch: window.fetch.bind(window),
  devUser,
  setDevUser,
})

export const authHeader = () => auth.authHeader()
export const useAuth = () => useSyncExternalStore(auth.subscribe, auth.getState)
