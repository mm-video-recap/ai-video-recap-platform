import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "var(--font-inter)",
          "Inter",
          "Myanmar Text",
          "Noto Sans Myanmar",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "sans-serif",
        ],
      },
      colors: {
        ink: {
          950: "#07060d",
          900: "#0b0a14",
          850: "#100e1c",
          800: "#151224",
          700: "#1d1830",
          600: "#2a2344",
        },
        brand: {
          300: "#93b4fd",
          400: "#6b8afd",
          500: "#4f6df5",
          600: "#3f56e0",
        },
      },
      boxShadow: {
        glow: "0 0 24px rgba(99, 102, 241, 0.35)",
        "glow-lg": "0 0 48px rgba(99, 102, 241, 0.45)",
        card: "0 8px 32px rgba(0, 0, 0, 0.35)",
      },
      keyframes: {
        float: {
          "0%, 100%": { transform: "translateY(0px)" },
          "50%": { transform: "translateY(-12px)" },
        },
        "pulse-ring": {
          "0%": { transform: "scale(0.9)", opacity: "0.7" },
          "100%": { transform: "scale(1.6)", opacity: "0" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
        dash: {
          to: { strokeDashoffset: "-24" },
        },
        "gradient-x": {
          "0%, 100%": { backgroundPosition: "0% 50%" },
          "50%": { backgroundPosition: "100% 50%" },
        },
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(16px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        float: "float 6s ease-in-out infinite",
        "pulse-ring": "pulse-ring 1.8s cubic-bezier(0.2, 0.6, 0.4, 1) infinite",
        shimmer: "shimmer 2.2s linear infinite",
        dash: "dash 1.2s linear infinite",
        "gradient-x": "gradient-x 8s ease infinite",
        "fade-up": "fade-up 0.5s ease-out both",
        "spin-slow": "spin 2.5s linear infinite",
      },
      backgroundSize: {
        "gradient-lg": "200% 200%",
      },
    },
  },
  plugins: [],
};
export default config;
