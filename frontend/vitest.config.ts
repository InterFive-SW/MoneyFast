import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

/**
 * Frontend test gate.
 *
 * Scoped deliberately to the LOGIC that can be wrong in a way a typecheck
 * cannot catch: the live-price hooks and the adapters between the API's shapes
 * and the components'. Presentational components are covered through the hooks
 * that feed them rather than by asserting on markup, which would break on
 * every styling change without catching a single real defect.
 *
 * `coverage.include` names those files explicitly. A blanket `src/**` would
 * fold in pages and mock fixtures and make the 100% gate meaningless — a
 * number reached by counting JSX rather than by testing behaviour.
 */
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    // Saat dilimi testler için UTC'ye SABİT. Ekrandaki her saat
    // `Europe/Istanbul`'a çevriliyor ve bunu doğrulayan testler, kendi
    // makinesi zaten Istanbul olan birinde kırık kodu yeşil gösterirdi.
    env: { TZ: 'UTC' },
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    reporters: ['default', 'junit'],
    outputFile: { junit: './junit.xml' },
    coverage: {
      provider: 'v8',
      include: [
        'src/hooks/**/*.ts',
        'src/lib/**/*.ts',
        'src/api/client.ts',
      ],
      reporter: ['text', 'html', 'cobertura'],
      reportsDirectory: './coverage',
      thresholds: { lines: 100, functions: 100, branches: 100, statements: 100 },
    },
  },
})
