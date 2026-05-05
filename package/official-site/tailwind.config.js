/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: [
    "./.vitepress/**/*.{js,ts,vue}",
    "./docs/**/*.md",
    "./en/**/*.md",
    "./*.md"
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#4A9DFF',
          dark: '#3A8DFF',
          light: '#70B3FF',
        },
        secondary: '#FFEEDD',
        neutral: {
          light: '#F5F7FA',
          dark: '#1D2124',
          gray: '#333333',
        }
      },
      fontFamily: {
        sans: ['Source Han Sans CN', 'Microsoft YaHei', 'PingFang SC', 'sans-serif'],
      },
      boxShadow: {
        'soft': '0 5px 15px rgba(0,0,0,0.05)',
        'hover': '0 10px 25px rgba(0,0,0,0.1)',
        'float': '0 10px 30px rgba(0,0,0,0.1)',
      }
    },
  },
  plugins: [],
}
