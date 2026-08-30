/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        brandBlue: '#4b7be5',
        primary: {
          50: '#f5f3ff',
          100: '#ede9fe',
          200: '#ddd6fe',
          300: '#c4b5fd',
          400: '#a85cf9',
          500: '#5534a5',
          600: '#3f257a',
          700: '#6d28d9',
          800: '#5b21b6',
          900: '#2b1b54',
          950: '#2e1065',
        },
        accent: {
          50: '#f0fdfa',
          100: '#ccfbf1',
          200: '#99f6e4',
          300: '#5eead4',
          400: '#6fdfdf',
          500: '#14b8a6',
          600: '#0d9488',
          700: '#0f766e',
          800: '#115e59',
          900: '#134e4a',
          950: '#042f2e',
        }
      },
      fontFamily: {
        sans: ['Poppins', 'sans-serif'],
      },
      keyframes: {
        // Şerit, listenin İKİ kopyasını yan yana basıp tam yarısı kadar
        // kaydırıyor: ikinci kopya birincinin bittiği yerde başladığı için
        // döngü başa sardığında bir sıçrama görünmüyor.
        marquee: {
          '0%': { transform: 'translateX(0)' },
          '100%': { transform: 'translateX(-50%)' },
        },
      },
      animation: {
        marquee: 'marquee 40s linear infinite',
      },
    },
  },
  plugins: [],
}
