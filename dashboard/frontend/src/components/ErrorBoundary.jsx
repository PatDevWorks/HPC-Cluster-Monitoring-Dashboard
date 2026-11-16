import React from 'react';
import { AlertTriangle, RotateCcw } from 'lucide-react';

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, errorMessage: '' };
  }

  static getDerivedStateFromError(error) {
    return {
      hasError: true,
      errorMessage: error?.message ? String(error.message) : 'Unexpected rendering error',
    };
  }

  componentDidCatch(error, errorInfo) {
    if (typeof console !== 'undefined' && console.error) {
      console.error('Page render error:', error, errorInfo);
    }
  }

  componentDidUpdate(prevProps) {
    if (this.state.hasError && prevProps.resetKey !== this.props.resetKey) {
      this.setState({ hasError: false, errorMessage: '' });
    }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="rounded-xl border border-rose-500/40 bg-rose-500/10 p-6 text-slate-100">
          <div className="flex items-start gap-3">
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-rose-400" />
            <div className="space-y-2">
              <h2 className="text-base font-semibold text-rose-200">
                Unable to render {this.props.sectionLabel || 'this view'}
              </h2>
              <p className="text-sm text-slate-300">
                A component rendering error occurred ({this.state.errorMessage}). Other dashboard sections remain available.
              </p>
              <button
                type="button"
                onClick={() => this.setState({ hasError: false, errorMessage: '' })}
                className="inline-flex items-center gap-2 rounded-lg border border-rose-400/40 bg-rose-500/20 px-3 py-1.5 text-xs font-medium text-rose-100 hover:bg-rose-500/30"
              >
                <RotateCcw className="h-3.5 w-3.5" />
                Retry View
              </button>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
