
interface Props {
  isOpen: boolean
  onClose: () => void
  featureName: string
}

export default function FeatureNotReadyModal({ isOpen, onClose, featureName }: Props) {
  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm overflow-y-auto">
      <div className="bg-slate-900 border border-white/10 rounded-2xl w-full max-w-sm shadow-2xl overflow-hidden my-auto p-6 text-center">
        <div className="w-16 h-16 bg-brandBlue/10 rounded-full mx-auto flex items-center justify-center mb-4 border border-brandBlue/30">
          <svg className="w-8 h-8 text-brandBlue" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </div>
        
        <h4 className="text-xl font-bold text-white mb-2">{featureName}</h4>
        <p className="text-sm text-slate-400 leading-relaxed mb-6">
          Bu özellik şu anda geliştirme aşamasındadır. Çok yakında "MoneyFast SuperApp" vizyonuyla hizmetinizde olacak!
        </p>

        <button 
          onClick={onClose}
          className="w-full bg-slate-800 hover:bg-slate-700 text-white font-medium py-3 rounded-xl transition-colors border border-white/10"
        >
          Anladım
        </button>
      </div>
    </div>
  )
}
