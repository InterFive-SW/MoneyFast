import React from 'react'

export class SettingsErrorBoundary extends React.Component<{children: React.ReactNode}, {hasError: boolean, error: Error | null}> {
  constructor(props: {children: React.ReactNode}) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="p-4 bg-red-900 text-white rounded">
          <h2>Something went wrong in Settings.</h2>
          <pre className="text-sm mt-2">{this.state.error?.message}</pre>
          <pre className="text-xs mt-2">{this.state.error?.stack}</pre>
        </div>
      )
    }
    return this.props.children
  }
}
