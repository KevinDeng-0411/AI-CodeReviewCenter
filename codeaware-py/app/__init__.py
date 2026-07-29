"""CodeAware Python 应用包。"""

import os

# 禁用库遥测/ tracing 的网络请求：langchain 1.x（langchain_openai 导入）与 unstructured
# （partition 调用）都会发起遥测网络请求，网络不通会 hang。setdefault 不覆盖显式设置。
os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")
os.environ.setdefault("ANONYMIZED_TELEMETRY", "false")
os.environ.setdefault("UNSTRUCTURED_TELEMETRY_DISABLE", "1")
