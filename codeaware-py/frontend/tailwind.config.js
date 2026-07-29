/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // 工程仪表台调色板 — 冷调技术纸 + oxblood 权威信号色
        paper: "#ECEEF1", // 纸基
        panel: "#F6F7F9", // 抬升面板
        graph: "#E2E5EA", // 内嵌读数面板（微深）
        ink: "#14161B", // 主文字（冷近黑）
        mute: "#5C6470", // 次文字
        line: "#D4D8DF", // 网格/分隔
        oxblood: "#7E1D2A", // 签名色：品牌/激活/Critical
        "oxblood-soft": "#9A3340",
        amber: "#B8722A", // 磷光琥珀：仅实时（流式/Warning）
        "amber-soft": "#D9943E",
        teal: "#3D6B6B", // Info/正向
      },
      fontFamily: {
        mono: ['"IBM Plex Mono"', "ui-monospace", "monospace"],
        sans: ['"IBM Plex Sans"', "system-ui", "sans-serif"],
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem" }],
      },
      letterSpacing: {
        techy: "0.06em",
      },
      keyframes: {
        // 信号轨迹：琥珀示波随 token 注入而扫动
        trace: {
          "0%": { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(100%)" },
        },
        blink: { "0%,100%": { opacity: "1" }, "50%": { opacity: "0.25" } },
        rise: {
          "0%": { transform: "translateY(4px)", opacity: "0" },
          "100%": { transform: "translateY(0)", opacity: "1" },
        },
      },
      animation: {
        trace: "trace 1.1s ease-in-out infinite",
        blink: "blink 1s steps(2) infinite",
        rise: "rise 0.18s ease-out",
      },
    },
  },
  plugins: [],
};
