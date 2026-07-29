import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App.tsx";

// 不用 StrictMode：dev 下双调 effect 会重复触发 SSE 流式，影响 Chat 调试
createRoot(document.getElementById("root")!).render(<App />);
