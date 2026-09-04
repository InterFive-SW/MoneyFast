/**
 * JWT payload reading.
 *
 * The interesting cases are all the malformed ones. Three copies of this
 * logic existed before it moved here, and they disagreed about what a token
 * with no `exp` means — which decides whether the app believes it has a
 * session it cannot prove.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { decodeJwtPayload, isTokenExpired, isTokenExpiringSoon, tokenSubject } from './jwt'

/** An unsigned token whose payload is `claims`. The signature is never read. */
function makeToken(claims: Record<string, unknown>): string {
  const payload = btoa(JSON.stringify(claims)).replace(/\+/g, '-').replace(/\//g, '_')
  return `header.${payload}.signature`
}

const IN_AN_HOUR = Math.floor(Date.now() / 1000) + 3600
const AN_HOUR_AGO = Math.floor(Date.now() / 1000) - 3600

describe('decodeJwtPayload', () => {
  it('reads the claims out of a well-formed token', () => {
    expect(decodeJwtPayload(makeToken({ sub: '12345678901' }))).toEqual({
      sub: '12345678901',
    })
  })

  it('returns null for a null token', () => {
    expect(decodeJwtPayload(null)).toBeNull()
  })

  it('returns null when there is no payload segment', () => {
    expect(decodeJwtPayload('not-a-jwt')).toBeNull()
  })

  it('returns null rather than throwing on undecodable base64', () => {
    expect(decodeJwtPayload('header.!!!not-base64!!!.sig')).toBeNull()
  })

  it('returns null when the payload is not JSON', () => {
    expect(decodeJwtPayload(`header.${btoa('plain text')}.sig`)).toBeNull()
  })

  it('decodes base64url, which is what JWT actually uses', () => {
    // `-` and `_` stand in for `+` and `/`; atob rejects them untranslated.
    const claims = { sub: '???>>>???', extra: 'ÿÿÿ' }
    expect(decodeJwtPayload(makeToken(claims))).toEqual(claims)
  })
})

describe('isTokenExpired', () => {
  it('is false while the token is still good', () => {
    expect(isTokenExpired(makeToken({ exp: IN_AN_HOUR }))).toBe(false)
  })

  it('is true once exp has passed', () => {
    expect(isTokenExpired(makeToken({ exp: AN_HOUR_AGO }))).toBe(true)
  })

  it('treats a token with no exp as expired', () => {
    /* The safe direction: believing an unprovable session means the user
       finds out when a write fails. */
    expect(isTokenExpired(makeToken({ sub: 'x' }))).toBe(true)
  })

  it('treats a non-numeric exp as expired', () => {
    expect(isTokenExpired(makeToken({ exp: 'soon' }))).toBe(true)
  })

  it('treats a missing token as expired', () => {
    expect(isTokenExpired(null)).toBe(true)
  })
})

describe('isTokenExpiringSoon', () => {
  afterEach(() => vi.useRealTimers())

  it('is false for a token with plenty of life left', () => {
    expect(isTokenExpiringSoon(makeToken({ exp: IN_AN_HOUR }))).toBe(false)
  })

  it('is true inside the window, before the token is actually dead', () => {
    /* A request started now could arrive after expiry. Refreshing early
       costs one call; not refreshing costs the turn. */
    const in30s = Math.floor(Date.now() / 1000) + 30
    expect(isTokenExpired(makeToken({ exp: in30s }))).toBe(false)
    expect(isTokenExpiringSoon(makeToken({ exp: in30s }))).toBe(true)
  })

  it('honours a custom window', () => {
    const in120s = Math.floor(Date.now() / 1000) + 120
    expect(isTokenExpiringSoon(makeToken({ exp: in120s }), 60)).toBe(false)
    expect(isTokenExpiringSoon(makeToken({ exp: in120s }), 300)).toBe(true)
  })

  it('is true when there is no readable exp', () => {
    expect(isTokenExpiringSoon(makeToken({}))).toBe(true)
    expect(isTokenExpiringSoon(null)).toBe(true)
  })
})

describe('tokenSubject', () => {
  it('returns the sub claim', () => {
    expect(tokenSubject(makeToken({ sub: '12345678901' }))).toBe('12345678901')
  })

  it('returns an empty string when sub is absent or not a string', () => {
    expect(tokenSubject(makeToken({}))).toBe('')
    expect(tokenSubject(makeToken({ sub: 42 }))).toBe('')
    expect(tokenSubject(null)).toBe('')
  })
})
