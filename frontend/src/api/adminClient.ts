/**
 * The administrator's API client.
 *
 * Separate from `apiClient` because the two identities are separate, and the
 * separation has to reach the browser: `apiClient` attaches whatever is in
 * `access_token` to every request. If an admin session reused that key, an
 * administrator logging in would silently replace the customer's session, and
 * every customer request would then carry a token the backend refuses.
 *
 * So the admin token lives under its own key and is only ever attached here.
 */

import { isTokenExpired } from '../lib/jwt'

const ADMIN_TOKEN_KEY = 'moneyfast_admin_token'

export function adminToken(): string | null {
  return localStorage.getItem(ADMIN_TOKEN_KEY)
}

export function setAdminToken(token: string): void {
  localStorage.setItem(ADMIN_TOKEN_KEY, token)
}

export function clearAdminToken(): void {
  localStorage.removeItem(ADMIN_TOKEN_KEY)
}

export function adminSessionValid(): boolean {
  const token = adminToken()
  return Boolean(token) && !isTokenExpired(token)
}

export interface AdminUserRow {
  id: string
  tc_no: string
  email: string
  full_name: string
  is_active: boolean
  cash_balance: number
  currency_code: string
  portfolio_value: number
  position_count: number
  created_at: string
}

export interface AdminAccount {
  id: string
  account_number: string
  iban?: string | null
  account_type: string
  currency_code: string
  balance: number
  is_investment: boolean
}

export interface AdminSubscription {
  id: string
  user_id: string
  full_name?: string | null
  label: string
  institution: string
  subscriber_no: string
}

export interface AdminBill {
  id: string
  /** Printed on the bill, as a real one carries. */
  holder_name?: string | null
  /** Who the subscriber number is assigned to. A bill belongs to nobody until
   *  it is paid; this is who it was meant for. */
  assigned_to?: string | null
  paid_by_name?: string | null
  institution: string
  bill_type: string
  subscriber_no: string
  amount: number
  due_day: number
  status: string
  paid_by?: string | null
  paid_at?: string | null
  created_at: string
}

/** Reads `detail` so the backend's Turkish reason reaches the operator. */
async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = adminToken()
  const response = await fetch(`/api/admin${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init.headers ?? {}),
    },
  })
  if (!response.ok) {
    let detail = `İşlem başarısız (${response.status})`
    try {
      const body = await response.json()
      if (typeof body?.detail === 'string') detail = body.detail
    } catch {
      // No JSON body — the status line is all we have.
    }
    throw new Error(detail)
  }
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T)
}

export const adminApi = {
  login(username: string, password: string) {
    return request<{ access_token: string; full_name?: string }>('/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    })
  },
  users() {
    return request<AdminUserRow[]>('/users')
  },
  /** Every account of the customer, so the operator can choose which one. */
  accounts(userId: string) {
    return request<AdminAccount[]>(`/users/${encodeURIComponent(userId)}/accounts`)
  },
  /**
   * `accountId` decides WHERE the money lands. Without it this always took the
   * deposit account, which is why crediting a customer never reached their
   * investment cash -- that lives in another table entirely.
   */
  adjustCash(userId: string, amount: number, accountId?: string, description?: string) {
    return request<{ message: string; balance_after?: number }>(
      `/users/${encodeURIComponent(userId)}/cash`,
      { method: 'POST', body: JSON.stringify({ amount, description, account_id: accountId }) },
    )
  },
  subscriptions(userId?: string) {
    const q = userId ? `?user_id=${encodeURIComponent(userId)}` : ''
    return request<AdminSubscription[]>(`/subscriptions${q}`)
  },
  assignSubscription(body: {
    user_id: string; institution: string; subscriber_no: string; label?: string
  }) {
    return request<AdminSubscription>('/subscriptions', {
      method: 'POST', body: JSON.stringify(body),
    })
  },
  adjustPosition(userId: string, symbol: string, quantity: number) {
    return request<{ message: string; quantity_after?: number }>(
      `/users/${encodeURIComponent(userId)}/positions`,
      { method: 'POST', body: JSON.stringify({ symbol, quantity }) },
    )
  },
  bills() {
    return request<{ bills: AdminBill[] }>('/bills')
  },
  issueBill(bill: {
    institution: string; bill_type: string; subscriber_no: string
    amount: number; due_day: number; holder_name?: string
  }) {
    return request<AdminBill>('/bills', { method: 'POST', body: JSON.stringify(bill) })
  },
  withdrawBill(billId: string) {
    return request<void>(`/bills/${encodeURIComponent(billId)}`, { method: 'DELETE' })
  },
}
