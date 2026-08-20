import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: false,
    setupFiles: ['./src/test/setup.ts'],
    css: true,
    // Dosya sayısı arttıkça forked worker'lar bu makinede zaman zaman kaynak sıkıntısı
    // çekip varsayılan 5s'yi aşabiliyor (gerçek bir test yavaşlığı değil) — pay bırakıyoruz.
    testTimeout: 15_000,
    // Testler (81 dosya) çok fazla eşzamanlı fork açınca bu makinede ara sıra
    // "Worker forks emitted error" ile çöküyordu — gerçek test hatası değildi, sadece
    // kaynak sıkışması. Paralellik sınırlanınca (tamamen sıralı değil, ama sınırsız da
    // değil) çökme durdu, toplam süre kabul edilebilir kaldı.
    maxWorkers: 4,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html', 'lcov', 'cobertura'],
      reportsDirectory: './coverage',
      include: ['src/**/*.{ts,tsx}'],
      exclude: [
        'src/main.tsx',
        'src/vite-env.d.ts',
        'src/api/generated/**',
        'src/test/**',
        '**/*.d.ts',
        // Kullanılmayan eski Sidebar bileşeni (yerini components/layout/Sidebar.tsx aldı,
        // hiçbir yerden import edilmiyor) — silinmesi ekiple konuşulmalı, o yüzden şimdilik
        // coverage zorunluluğu dışında tutuldu.
        'src/components/Sidebar.tsx',
      ],
      thresholds: {
        lines: 100,
        functions: 100,
        branches: 100,
        statements: 100,
      },
    },
  },
})
