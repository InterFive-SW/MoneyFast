import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import SuggestedPrompts from './SuggestedPrompts'

describe('SuggestedPrompts', () => {
  it('tüm önerileri render eder, tıklanınca onSelectPrompt\'u metniyle çağırır', () => {
    const onSelectPrompt = vi.fn()
    render(<SuggestedPrompts onSelectPrompt={onSelectPrompt} />)

    const prompt = "SASA'nın son çeyrek bilançosunu basitçe anlat"
    const button = screen.getByText(prompt)
    fireEvent.click(button)
    expect(onSelectPrompt).toHaveBeenCalledWith(prompt)
  })
})
