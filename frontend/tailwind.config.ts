import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx}",
    "./components/**/*.{js,ts,jsx,tsx}",
    "./lib/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-source-sans)", "ui-sans-serif", "system-ui"],
        display: ["var(--font-source-serif)", "ui-serif", "Georgia"],
      },
      colors: {
        canvas: "#f6f4ef",
        ink: "#1c1917",
        muted: "#57534e",
        line: "#e7e0d4",
        accent: "#1d4ed8",
        accentHover: "#1e40af",
      },
    },
  },
  plugins: [],
};

export default config;
