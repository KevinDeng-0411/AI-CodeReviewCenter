# 截图目录

README 的「界面截图」章节使用的截图统一放本目录，GitHub 相对路径引用。

## 待补充清单

| 文件 | 内容 | 建议 |
|---|---|---|
| `chat.png` | Chat 对话界面 | 展示流式回答 + 引用来源（context.references 卡片）+ 思考过程 |
| `knowledge.png` | 知识库管理界面 | 文档列表 + 分块可视化 + 上传/替换/软删操作 |
| `login.png` | 登录页 | JWT 登录（可选） |

## 要求

- PNG 格式，建议宽度 ≥ 1200px（GitHub 单列渲染）
- 引用方式（在 README 中）：

```md
![Chat 对话](./docs/screenshots/chat.png)
```

## 流程

1. 浏览器打开 http://localhost:5173 并登录
2. 上传一篇团队文档到知识库，问一个相关问题（回答会带引用来源）
3. 截图后按上表命名放入本目录
4. 在 README「界面截图」章节替换占位文字
