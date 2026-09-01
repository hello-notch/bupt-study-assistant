# 自定义与数据位置

下列路径均相对于 `new_bot/`。编辑配置或 SQLite 数据前，建议先停止机器人并备份对应文件，避免与运行中的写入事务冲突。

## AI 模型与生成参数

- 路由文件：`config/ai_routes.toml`
- API key：`secrets/apikey.txt`
- 路由文件的每个 `[tasks.<任务>]` 可设置 `primary`、`fallbacks`、`temperature`、`max_tokens`。
- `chat` 是普通对话；`proactive_gate` 是主动接话判断；`summary` 和 `stats_analysis` 分别用于群总结和水群分析；`memory_extraction` 用于记忆候选；`vision` 用于图片理解；`complex_reasoning` 留给复杂任务。
- 修改 TOML 后需要重启机器人。

当前代码尚未把 `top_p`、是否联网搜索、是否思考和思考强度接入路由配置。直接在 TOML 中自行添加这些字段不会生效；这些能力还取决于对应供应商是否支持兼容参数。不要在不了解供应商协议时把它们伪装成通用参数。

角色设定分别位于：

- `src/amadeus_bot/persona/canon.md`：身份、经历和人物关系。
- `src/amadeus_bot/persona/style.md`：措辞与语气。
- `src/amadeus_bot/persona/runtime.md`：运行时边界和工具使用约束。

## 帮助信息

每个命令的说明、用法、别名、权限、示例和注意事项位于对应 `src/amadeus_bot/plugins/*.py` 的 `CommandSpec`。`src/amadeus_bot/plugins/help.py` 负责功能分组、权限过滤和图片布局。修改后重启会重新按内容生成 `data/cache/render/*.png`；通常不必手动清缓存。

## 推荐池

`data/core.sqlite3` 的 `recommendations` 表保存三个独立推荐池：

- `activity`：干什么。
- `food`：吃什么。
- `music`：听什么/推歌。

推荐内容可以优先用 `/recommend list|add|del` 维护。也可以在机器人停止时使用 DB Browser for SQLite 编辑；常用字段是 `pool`、`path`、`content`、`weight`、`tags`、`enabled`，不要修改主键或表结构。

普通推荐回复与空池提示目前位于 `src/amadeus_bot/plugins/recommendations.py` 的 `_friendly_recommendation()` 和 `_finish_random()`。这类可变文案尚未集中成独立配置文件。

## 其他常用数据与文本

- QQ 表情 ID 与别名：`data/shared/emoji_ids.json`。只有 `status` 为 `verified` 的条目才用于名称解析；`/stick list [起始ID]` 每次直接展示 20 个 ID 与对应 QQ 表情，方便人工确认映射。
- 用户 DDL、课程、记忆和偏好：`data/users/<QQ号>/user.sqlite3`。
- 群内 wife 配对与语录：`data/groups/<群号>/group.sqlite3`。
- AI 当前对话上下文：`data/core.sqlite3` 的 `conversation_messages` 表，也可由 `/history [1-30]` 只读查看当前作用域。
- 校园通知与活动缓存：`data/core.sqlite3` 的 `source_items` 表。
- 功能开关、权限成员、推荐池、订阅和 AI 用量：`data/core.sqlite3`。
- 人类可读活动日志：`logs/activity/YYYY-MM-DD.log`；结构化版本为同名 `.jsonl`。
- 原始统计消息：群聊在 `logs/messages/<群号>/`，私聊在 `logs/private/<QQ号>/`。
- 控制台/框架运行日志：`logs/runtime/runtime.log`。

目前没有统一的 `texts.toml`；没有列入配置的提示语仍在对应插件源码中。定位时可在项目根目录使用 `rg -n "要查找的原文" src`。后续若经常调整运营文案，适合再把非参数错误类文本集中到 `config/texts.toml`，但权限、安全提示和参数校验信息应继续跟代码一起维护。
