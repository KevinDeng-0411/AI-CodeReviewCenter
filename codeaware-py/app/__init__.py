"""CodeAware Python 应用包。"""

import os

# 禁用 LangSmith tracing / 匿名遥测：langchain 1.x 导入 langchain_openai 时可能
# 发起网络请求，网络不通会 hang（本项不使用 LangSmith）。setdefault 不覆盖显式设置。
os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")
os.environ.setdefault("ANONYMIZED_TELEMETRY", "false")
