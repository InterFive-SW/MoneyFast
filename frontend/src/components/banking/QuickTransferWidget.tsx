import React, { useState } from 'react'
import type { SavedContact } from '../../data/mockBankingData'

interface Props {
  contacts: SavedContact[]
}

export default function QuickTransferWidget({ contacts }: Props) {
  const [selectedContact, setSelectedContact] = useState<string | null>(null)
  const [amount, setAmount] = useState<string>('')

  return (
    <div className="flex flex-col rounded-2xl bg-slate-900/50 backdrop-blur-xl border border-white/10 p-6 shadow-2xl">
      <h3 className="text-sm font-semibold text-white mb-4">Hızlı Transfer</h3>

      {/* Kişiler (Horizontal Scroll) */}
      <div className="flex gap-4 overflow-x-auto pb-4 scrollbar-hide -mx-2 px-2">
        <div 
          onClick={() => setSelectedContact('new')}
          className="flex flex-col items-center gap-2 cursor-pointer shrink-0 group"
        >
          <div className={`w-14 h-14 rounded-full flex items-center justify-center border-2 border-dashed transition-colors ${selectedContact === 'new' ? 'border-brandBlue text-brandBlue bg-brandBlue/10' : 'border-white/20 text-slate-400 group-hover:border-white/40 group-hover:text-slate-300'}`}>
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
          </div>
          <span className="text-[11px] font-medium text-slate-400">Yeni Kişi</span>
        </div>

        {contacts.map(contact => (
          <div 
            key={contact.id} 
            onClick={() => setSelectedContact(contact.id)}
            className="flex flex-col items-center gap-2 cursor-pointer shrink-0 group"
          >
            <div className={`w-14 h-14 rounded-full flex items-center justify-center text-white font-bold text-lg border-2 transition-transform ${selectedContact === contact.id ? 'border-brandBlue scale-110 shadow-lg shadow-brandBlue/20' : 'border-transparent group-hover:scale-105'} ${contact.avatarColor}`}>
              {contact.avatarInitials}
            </div>
            <span className={`text-[11px] font-medium ${selectedContact === contact.id ? 'text-white' : 'text-slate-400'}`}>
              {contact.name}
            </span>
          </div>
        ))}
      </div>

      {/* Tutar ve Gönder Butonu */}
      <div className="mt-2 flex gap-3">
        <div className="relative flex-1">
          <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
            <span className="text-slate-400 sm:text-sm">₺</span>
          </div>
          <input
            type="number"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            className="w-full bg-slate-800/50 border border-white/10 rounded-xl py-3 pl-8 pr-4 text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-brandBlue/50 focus:border-brandBlue transition-colors block sm:text-sm"
            placeholder="0.00"
          />
        </div>
        <button 
          disabled={!selectedContact || !amount}
          className="bg-brandBlue hover:bg-blue-600 disabled:opacity-50 disabled:hover:bg-brandBlue disabled:cursor-not-allowed text-white font-medium px-6 py-3 rounded-xl transition-all shadow-lg shadow-brandBlue/20"
        >
          Gönder
        </button>
      </div>
      
      {!selectedContact && (
        <p className="text-[11px] text-slate-500 mt-3 text-center">Lütfen transfer yapmak için bir kişi seçin.</p>
      )}
    </div>
  )
}
