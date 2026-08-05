# ADR-0013: 文档管理——软删除 + 列表 + replace 更新

**状态**: 已实施
**日期**: 2026-08-05
**决策者**: Kevin

## 背景

知识库此前只有上传、搜索、物理删除，没有文档列表页面。团队上传多文档后无法查看目录，误删不可恢复。需要文档级管理能力。

## 决策

**1. 软删除**：删除文档 = 标 `documents.status=DELETED` + 物理删该文档所有 chunks。

- `documents` 行保留（列表可审计/追溯），`chunks` 物理删（释放向量存储）
- 符合参考策略"删除文档 = 删除该文档所有分块"
- 幂等：已 DELETED 文档再次删除返回 404

**2. 列表**：`GET /api/knowledge/documents`，status 过滤（ACTIVE/DELETED/ALL）+ 分页 + chunk_count。

**3. 更新（replace）**：`POST /api/knowledge/{doc_id}/replace` = 软删旧文档 + 上传新文档（新 doc_id，ACTIVE）。

- 复用 `upload_document`（分块/向量/jieba 分词不变）
- 旧文档元数据保留（status=DELETED 可审计），新文档独立 id

**4. 详情**：`GET /api/knowledge/{doc_id}` 返回元数据 + 全文 + 分块列表。

- 已软删文档也可查看（审计/追溯），chunks 已物理删则 chunk_count=0
- 分块可视化：RAG 调试（C5 分块效果可查）与面试 demo 的价值点

## 表变更

`documents` 加列（迁移 0011）：
```text
status      VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'   -- ACTIVE/DELETED
deleted_at  TIMESTAMP NULL
updated_at  TIMESTAMP NOT NULL DEFAULT now()
```

## 为什么

- **软删而非物理删行**：误删可审计/可追溯；chunks 物理删释放向量存储
- **列表而非仅搜索**：团队需要文档目录管理（有多少文档、状态如何）
- **replace 而非原地覆盖**：保留更新历史（新旧两个 doc_id），避免原地改 chunks 的复杂事务

## 不做

- 不做"彻底删除"（物理删 documents 行）——避免误删不可恢复
- 不做文档搜索/筛选（只按 status 过滤）
- 不做多版本历史（replace 只留新旧两个 doc_id）
