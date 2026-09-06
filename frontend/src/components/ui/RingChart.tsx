import { useState, useEffect } from 'react';

const COLORS = [
  '#10B981', // zümrüt yeşili/teal (dış halka)
  '#A855F7', // parlak mor (orta halka)
  '#0EA5E9', // açık mavi/cyan (iç halka)
  '#EC4899', // pembe
  '#EF4444', // kırmızı
  '#EAB308', // sarı
];

interface DataItem {
  name: string;
  value: number;
}

interface RingChartProps {
  data: DataItem[];
  totalLabel?: string;
  totalValue?: string;
  size?: number;
  strokeWidth?: number;
}

export function RingChart({
  data,
  totalLabel = 'Total',
  totalValue = '0',
  size = 220,
  strokeWidth = 14,
}: RingChartProps) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const [animatedProgress, setAnimatedProgress] = useState(0);

  useEffect(() => {
    // Trigger animation slightly after mount for smooth effect
    const timer = setTimeout(() => {
      setAnimatedProgress(1);
    }, 100);
    return () => clearTimeout(timer);
  }, []);

  const total = data.reduce((sum, item) => sum + item.value, 0);
  const center = size / 2;
  const gap = strokeWidth + 10; // Halkalar arası boşluğu (gap) artırdık

  return (
    <div className="flex flex-col gap-8 w-full mt-4">
      {/* Chart Section */}
      <div className="flex justify-center">
        <div className="relative" style={{ width: size, height: size }}>
          <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
            {data.map((item, i) => {
              const radius = center - strokeWidth / 2 - i * gap;
              const circumference = 2 * Math.PI * radius;
              const percentage = total > 0 ? item.value / total : 0;
              const strokeDashoffset = circumference - percentage * circumference * animatedProgress;
              
              const isHovered = hoveredIndex === i;
              const isAnyHovered = hoveredIndex !== null;
              const opacity = isAnyHovered ? (isHovered ? 1 : 0.3) : 1;
              const color = COLORS[i % COLORS.length];

              return (
                <g key={item.name} style={{ transition: 'opacity 0.3s ease', opacity }}>
                  {/* Background Track */}
                  <circle
                    cx={center}
                    cy={center}
                    r={radius}
                    fill="none"
                    stroke="#1e293b" // slate-800
                    strokeWidth={strokeWidth}
                  />
                  {/* Animated Progress */}
                  <circle
                    cx={center}
                    cy={center}
                    r={radius}
                    fill="none"
                    stroke={color}
                    strokeWidth={strokeWidth}
                    strokeDasharray={circumference}
                    strokeDashoffset={strokeDashoffset}
                    strokeLinecap="round"
                    style={{
                      transition: 'stroke-dashoffset 1s cubic-bezier(0.4, 0, 0.2, 1)',
                      transformOrigin: '50% 50%',
                      transform: 'rotate(-90deg)' // start from top
                    }}
                  />
                </g>
              );
            })}
          </svg>
          
          {/* Center Content */}
          <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
            <div className="text-xl font-bold text-white tracking-tight">{totalValue}</div>
            <div className="text-xs text-slate-400 font-medium mt-1">{totalLabel}</div>
          </div>
        </div>
      </div>

      {/* Legend Section */}
      <div className="flex flex-col gap-4">
        {data.map((item, i) => {
          const color = COLORS[i % COLORS.length];
          const isHovered = hoveredIndex === i;
          const isAnyHovered = hoveredIndex !== null;
          const opacity = isAnyHovered ? (isHovered ? 1 : 0.4) : 1;
          const percentage = total > 0 ? (item.value / total) * 100 : 0;

          return (
            <div
              key={item.name}
              className="flex flex-col gap-2 cursor-pointer"
              onMouseEnter={() => setHoveredIndex(i)}
              onMouseLeave={() => setHoveredIndex(null)}
              style={{ transition: 'opacity 0.3s ease', opacity }}
            >
              <div className="flex items-center justify-between text-sm">
                <div className="flex items-center gap-2.5">
                  <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: color }} />
                  <span className="font-medium text-slate-300">{item.name}</span>
                </div>
                <div className="flex items-center gap-4">
                  {/* Currency Format */}
                  <span className="text-slate-300 tabular-nums">
                    ₺{item.value.toLocaleString('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </span>
                  <span className="text-slate-500 tabular-nums w-12 text-right">
                    {percentage.toFixed(1)}%
                  </span>
                </div>
              </div>
              <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${animatedProgress * percentage}%`,
                    backgroundColor: color,
                    transition: 'width 1s cubic-bezier(0.4, 0, 0.2, 1)'
                  }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
