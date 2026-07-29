// CodeAware 工程仪表台 - 7 模块 SPA（状态切换视图，无 router）
import { useState } from "react";
import Layout, { type PageId } from "./components/Layout";
import ChatPage from "./pages/Chat";
import CodeReviewPage from "./pages/CodeReview";
import UnitTestPage from "./pages/UnitTest";
import AiReadmePage from "./pages/AiReadme";
import KnowledgePage from "./pages/Knowledge";
import MemoryPage from "./pages/Memory";
import PromptPage from "./pages/Prompt";

export default function App() {
  const [page, setPage] = useState<PageId>("chat");

  return (
    <Layout active={page} onNavigate={setPage}>
      {page === "chat" && <ChatPage />}
      {page === "review" && <CodeReviewPage />}
      {page === "unittest" && <UnitTestPage />}
      {page === "readme" && <AiReadmePage />}
      {page === "knowledge" && <KnowledgePage />}
      {page === "memory" && <MemoryPage />}
      {page === "prompt" && <PromptPage />}
    </Layout>
  );
}
