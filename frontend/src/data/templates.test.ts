import { describe, expect, it } from 'vitest'
import { DASHBOARD_TEMPLATES, DEFAULT_TEMPLATE_ID } from './templates'

describe('DASHBOARD_TEMPLATES', () => {
  it('en az bir şablon tanımlıdır', () => {
    expect(DASHBOARD_TEMPLATES.length).toBeGreaterThan(0)
  })

  it('her şablonun id\'si benzersizdir', () => {
    const ids = DASHBOARD_TEMPLATES.map((t) => t.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('her şablon en az bir widget içerir', () => {
    for (const template of DASHBOARD_TEMPLATES) {
      expect(template.widgets.length).toBeGreaterThan(0)
    }
  })

  it('her widget\'ın grid içindeki id\'si kendi şablonu içinde benzersizdir', () => {
    for (const template of DASHBOARD_TEMPLATES) {
      const widgetIds = template.widgets.map((w) => w.id)
      expect(new Set(widgetIds).size).toBe(widgetIds.length)
    }
  })

  it('DEFAULT_TEMPLATE_ID, tanımlı şablonlardan birine karşılık gelir', () => {
    const ids = DASHBOARD_TEMPLATES.map((t) => t.id)
    expect(ids).toContain(DEFAULT_TEMPLATE_ID)
  })
})
