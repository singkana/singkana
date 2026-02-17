/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./index.html",
    "./privacy.html",
    "./terms.html",
    "./tokusho.html",
    "./singkana_sheet.html",
    "./en/**/*.html",
    "./romaji/**/*.html",
    "./lp/**/*.html",
    "./guide/**/*.html",
    "./submit_singkana_sanitized/**/*.html",
    "./submit_singkana_v1/**/*.html",
    "./assets/js/**/*.js",
    "./*.js",
  ],
  theme: {
    extend: {
      colors: {
        singkana: {
          50: "#f7f4ff",
          100: "#ede7ff",
          200: "#d9ceff",
          300: "#c0aeff",
          400: "#a184ff",
          500: "#8a5dff",
          600: "#7441f0",
          700: "#5c32c4",
          800: "#472898",
          900: "#362073",
        },
      },
      boxShadow: {
        soft: "0 18px 45px rgba(0,0,0,0.35)",
        glow: "0 0 40px rgba(138,93,255,0.45)",
      },
      backdropBlur: {
        xs: "2px",
      },
    },
  },
  plugins: [],
};
