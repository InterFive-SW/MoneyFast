import { Component } from 'react'
import type { ErrorInfo, ReactNode } from 'react'

interface Props {
  children: ReactNode
  /** Shown in the fallback so a broken tile still says what it was. */
  label?: string
}
interface State { error: Error | null }

/**
 * Contains a render crash to its own subtree.
 *
 * React unmounts the entire root when a render throws and nothing catches it,
 * so a single widget dereferencing an empty array turned the whole dashboard
 * white -- the page flashed once, then went blank with no clue in the network
 * log, because every request had already succeeded.
 *
 * A boundary per widget means the worst case is one dead tile next to
 * seventeen working ones.
 */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(`[${this.props.label ?? 'component'}] render failed`, error, info.componentStack)
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="flex h-full flex-col items-center justify-center gap-1 rounded-xl border border-amber-500/20 bg-amber-500/5 p-4 text-center">
        <span className="text-xs font-semibold text-amber-400">Bu bileşen yüklenemedi</span>
        {this.props.label && (
          <span className="text-[11px] text-slate-500">{this.props.label}</span>
        )}
        <button
          onClick={() => this.setState({ error: null })}
          className="mt-1 rounded-md border border-white/10 px-2 py-1 text-[11px] text-slate-400 hover:text-slate-200"
        >
          Yeniden dene
        </button>
      </div>
    )
  }
}
