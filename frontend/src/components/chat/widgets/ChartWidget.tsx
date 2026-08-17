// src/components/chat/widgets/ChartWidget.tsx
import React from 'react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { ChartWidgetPayload } from '../../../types/chat';

interface ChartWidgetProps {
  payload: ChartWidgetPayload;
}

/**
 * ChartWidget Bileşeni
 * 
 * Recharts kullanarak sohbet içerisindeki mesajlarda grafik 
 * (hisse senedi, portföy dağılımı vb.) render eden interaktif bileşen.
 */
export default function ChartWidget({ payload }: ChartWidgetProps) {
  return (
    <div className="mt-3 w-full bg-white rounded-xl p-4 shadow-sm border border-slate-100 overflow-hidden">
      <h4 className="text-sm font-semibold text-slate-800 mb-4">{payload.title}</h4>
      <div className="h-40 w-full min-w-[200px]">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={payload.data} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
            <XAxis dataKey="name" fontSize={10} tickLine={false} axisLine={false} stroke="#94a3b8" />
            <YAxis fontSize={10} tickLine={false} axisLine={false} stroke="#94a3b8" />
            <Tooltip 
              contentStyle={{ borderRadius: '8px', border: '1px solid #e2e8f0', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }}
              itemStyle={{ color: '#0f172a', fontSize: '12px', fontWeight: 500 }}
              labelStyle={{ color: '#64748b', fontSize: '11px', marginBottom: '4px' }}
            />
            <Line 
              type="monotone" 
              dataKey="value" 
              stroke={payload.color || '#10b981'} 
              strokeWidth={2} 
              dot={{ r: 3, fill: payload.color || '#10b981' }} 
              activeDot={{ r: 5 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
