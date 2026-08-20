import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import Banking from './Banking'

describe('Banking', () => {
  it('başlığı render eder', () => {
    render(<Banking />)
    expect(screen.getByText('Banking')).toBeInTheDocument()
  })
})
