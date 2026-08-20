export interface RiskFactor {
  id: string
  title: string
  description: string
  impact: 'positive' | 'negative' | 'neutral'
}

export interface RiskRecommendation {
  id: string
  title: string
  description: string
  actionLabel: string
  priority: 'high' | 'medium' | 'low'
}

export interface RiskData {
  overallScore: number
  riskLevel: 'Düşük' | 'Orta' | 'Yüksek'
  lastCalculated: string
  factors: RiskFactor[]
  recommendations: RiskRecommendation[]
  financialBalance: {
    monthlyIncome: number
    monthlyExpense: number
    totalDebt: number
    debtToIncomeRatio: number
  }
}

export const MOCK_RISK_DATA: RiskData = {
  overallScore: 68,
  riskLevel: 'Orta',
  lastCalculated: new Date().toISOString(),
  factors: [
    {
      id: 'f1',
      title: 'İyi Portföy Çeşitliliği',
      description: 'Yatırımlarınız birden fazla sektöre yayılmış durumda, bu da riski azaltıyor.',
      impact: 'positive'
    },
    {
      id: 'f2',
      title: 'Düzenli Gelir Akışı',
      description: 'Aylık geliriniz son 6 aydır istikrarlı.',
      impact: 'positive'
    },
    {
      id: 'f3',
      title: 'Yüksek Borçluluk Oranı',
      description: 'Aylık borç ödemeleriniz gelirinizin %40\'ını aşıyor.',
      impact: 'negative'
    },
    {
      id: 'f4',
      title: 'Yetersiz Acil Durum Fonu',
      description: 'Nakit varlıklarınız 3 aylık zorunlu giderlerinizi karşılamıyor.',
      impact: 'negative'
    }
  ],
  recommendations: [
    {
      id: 'r1',
      title: 'Acil Durum Fonu Oluşturun',
      description: 'Beklenmedik harcamalar için likit varlıklarınızı (nakit, vadesiz mevduat) artırmanız önerilir.',
      actionLabel: 'Birikim Hesabı Aç',
      priority: 'high'
    },
    {
      id: 'r2',
      title: 'Kredi Kartı Borcunu Azaltın',
      description: 'Kredi kartı borcunuz ideal oranın üzerinde. Ekstra ödemelerle faiz yükünden kurtulun.',
      actionLabel: 'Borç Öde',
      priority: 'medium'
    },
    {
      id: 'r3',
      title: 'Düşük Riskli Varlıklara Yönelin',
      description: 'Portföyünüzdeki teknoloji hisselerinin oranını düşürerek devlet tahvili veya altın gibi araçlara geçiş yapabilirsiniz.',
      actionLabel: 'Portföyü İncele',
      priority: 'low'
    }
  ],
  financialBalance: {
    monthlyIncome: 45000,
    monthlyExpense: 22000,
    totalDebt: 65000,
    debtToIncomeRatio: 42 // percentage
  }
}
