import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: {
          base: "#08090d",
          panel: "#0f1117",
          card: "#14171f",
          hover: "#1a1e28",
        },
        border: {
          DEFAULT: "#1f2430",
          bright: "#2a3140",
        },
        accent: {
          green: "#00e08f",
          red: "#ff3d5c",
          blue: "#3d9cff",
          yellow: "#ffc107",
          purple: "#b366ff",
        },
        text: {
          primary: "#e8ecf3",
          secondary: "#8b94a8",
          muted: "#4a5262",
        },
      },
      fontFamily: {
        mono: ["var(--font-jetbrains)", "monospace"],
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
      },
      animation: {
        "pulse-dot": "pulse-dot 2s ease-in-out infinite",
        "fade-in": "fade-in 0.3s ease-out",
      },
      keyframes: {
        "pulse-dot": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.35" },
        },
        "fade-in": {
          "0%": { opacity: "0", transform: "translateY(4px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
    },
  },
  plugins: [],
};
export default config;