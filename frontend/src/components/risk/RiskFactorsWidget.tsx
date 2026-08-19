import type { RiskFactor } from '../../data/mockRiskData'

interface RiskFactorsWidgetProps {
  factors: RiskFactor[]
}

// Inline SVGs for positive/negative impacts
const IconCheck = () => (
  <svg className="h-5 w-5 text-emerald-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
  </svg>
)

const IconX = () => (
  <svg className="h-5 w-5 text-rose-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
  </svg>
)

const IconInfo = () => (
  <svg className="h-5 w-5 text-blue-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
  </svg>
)

export default function RiskFactorsWidget({ factors }: RiskFactorsWidgetProps) {
  return (
    <div className="flex flex-col rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <h3 className="mb-4 text-base font-semibold text-slate-800">Öne Çıkan Risk Faktörleri</h3>
      
      <div className="flex flex-col gap-3">
        {factors.map((factor) => {
          let icon = <IconInfo />
          let bg = 'bg-blue-50'
          if (factor.impact === 'positive') {
            icon = <IconCheck />
            bg = 'bg-emerald-50'
          } else if (factor.impact === 'negative') {
            icon = <IconX />
            bg = 'bg-rose-50'
          }

          return (
            <div key={factor.id} className="flex items-start gap-4 rounded-xl border border-slate-100 p-4 transition-colors hover:bg-slate-50">
              <div className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${bg}`}>
                {icon}
              </div>
              <div className="flex-1">
                <h4 className="text-sm font-semibold text-slate-800">{factor.title}</h4>
                <p className="mt-1 text-sm text-slate-500">{factor.description}</p>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
