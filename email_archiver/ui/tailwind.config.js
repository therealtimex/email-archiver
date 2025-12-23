/** @type {import('tailwindcss').Config} */
export default {
    content: [
        "./index.html",
        "./src/**/*.{js,ts,jsx,tsx}",
    ],
    theme: {
        extend: {
            colors: {
                primary: "#6366f1",
                secondary: "#a855f7",
                background: "#0a0a0c",
                card: "rgba(255, 255, 255, 0.05)",
            },
            backdropBlur: {
                xs: '2px',
            }
        },
    },
    plugins: [],
}
