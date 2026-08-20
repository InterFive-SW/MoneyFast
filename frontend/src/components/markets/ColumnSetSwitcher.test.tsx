import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ColumnSetSwitcher from './ColumnSetSwitcher'

describe('ColumnSetSwitcher', () => {
  it('seçili kolon setini vurgular ve tıklanınca onChange çağırır', () => {
    const onChange = vi.fn()
    render(<ColumnSetSwitcher value="getiri" onChange={onChange} />)

    const active = screen.getByText('Getiri')
    expect(active.className).toContain('bg-emerald-500')

    const inactive = screen.getByText('Değerleme')
    expect(inactive.className).not.toContain('bg-emerald-500')

    fireEvent.click(inactive)
    expect(onChange).toHaveBeenCalledWith('degerleme')
  })
})
