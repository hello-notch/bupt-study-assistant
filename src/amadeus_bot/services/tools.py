from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from amadeus_bot.domain.commands import command_registry
from amadeus_bot.repositories.core import CoreRepository
from amadeus_bot.repositories.group_data import GroupDataRepository
from amadeus_bot.repositories.user_data import UserDataRepository
from amadeus_bot.services.activity_log import ActivityLogService
from amadeus_bot.services.analytics import AnalyticsService, format_deterministic
from amadeus_bot.services.calculator import calculate, format_result
from amadeus_bot.services.courses import CourseService, parse_sections, parse_weekday
from amadeus_bot.services.ddl import DDLService, format_ddl
from amadeus_bot.services.feature_flags import FeatureFlagService


@dataclass(frozen=True, slots=True)
class ToolExecutionContext:
    requested_by: str
    subject_user_id: str
    group_id: str | None
    bot: Any | None = None
    replied_message_id: str | None = None

    @classmethod
    def for_requester(
        cls,
        user_id: str,
        group_id: str | None,
        *,
        bot: Any | None = None,
        replied_message_id: str | None = None,
    ) -> ToolExecutionContext:
        normalized = str(user_id)
        return cls(
            requested_by=normalized,
            subject_user_id=normalized,
            group_id=group_id,
            bot=bot,
            replied_message_id=replied_message_id,
        )


class AIToolService:
    """Whitelist only. SUPERUSER tools must never be added here."""

    def __init__(
        self,
        ddl: DDLService,
        repository: CoreRepository,
        features: FeatureFlagService,
        user_repository: UserDataRepository | None = None,
        group_repository: GroupDataRepository | None = None,
        courses: CourseService | None = None,
        log_root: Path | None = None,
        activity_log: ActivityLogService | None = None,
    ) -> None:
        self.ddl = ddl
        self.repository = repository
        self.features = features
        self.user_repository = user_repository or ddl.repository
        root = self.user_repository.users_root.parent
        self.group_repository = group_repository or GroupDataRepository(root / "groups")
        self.courses = courses or CourseService(self.user_repository)
        self.log_root = log_root or root / "logs"
        self.activity_log = activity_log

    def schemas(self) -> list[dict[str, Any]]:
        return [
            _function(
                "help_lookup",
                "查询机器人命令帮助",
                {"command": {"type": "string"}},
                [],
            ),
            _function(
                "calculate",
                "计算安全数学表达式",
                {"expression": {"type": "string"}},
                ["expression"],
            ),
            _function(
                "ddl_show",
                "查看当前请求者的一条 DDL",
                {"ddl_id": {"type": "integer", "minimum": 1}},
                ["ddl_id"],
            ),
            _function(
                "ddl_edit",
                "编辑当前请求者的一条 DDL",
                {
                    "ddl_id": {"type": "integer", "minimum": 1},
                    "deadline": {"type": "string"},
                    "content": {"type": "string"},
                },
                ["ddl_id"],
            ),
            _function(
                "ddl_remind",
                "设置当前请求者 DDL 的提前提醒",
                {"ddl_id": {"type": "integer"}, "advance": {"type": "string"}},
                ["ddl_id", "advance"],
            ),
            _function(
                "ddl_add",
                (
                    "为当前请求者添加 DDL。deadline 支持“2分钟后”“明天下午三点”"
                    "“23:59”或 ISO 时间。用户说“提醒我两分钟后”时 reminder 必须传 at；"
                    "只有用户明确不要提醒时才传 off"
                ),
                {
                    "deadline": {
                        "type": "string",
                        "description": "北京时间，例如 2分钟后、明天15:30、2026-09-02 15:00",
                    },
                    "content": {"type": "string"},
                    "reminder": {
                        "type": "string",
                        "description": (
                            "at=到截止时间提醒；30m/1小时=提前提醒；off=明确不提醒；省略则默认提前1小时"
                        ),
                    },
                },
                ["deadline", "content"],
            ),
            _function(
                "ddl_list",
                "列出当前请求者自己的 DDL",
                {"status": {"type": "string", "enum": ["todo", "done", "all"]}},
                [],
            ),
            _function(
                "ddl_done",
                "把当前请求者自己的 DDL 标记完成",
                {"ddl_id": {"type": "integer", "minimum": 1}},
                ["ddl_id"],
            ),
            _function(
                "recommend_random",
                "从干什么、吃什么或推歌的独立池中推荐",
                {
                    "pool": {"type": "string", "enum": ["activity", "food", "music"]},
                    "path": {"type": "string"},
                },
                ["pool"],
            ),
            _function(
                "recommend_add",
                "以受限 AI_MEMBER_DELEGATE 为当前请求者添加共享推荐项",
                {
                    "pool": {"type": "string", "enum": ["activity", "food", "music"]},
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                    "weight": {"type": "number", "exclusiveMinimum": 0},
                },
                ["pool", "content"],
            ),
            _function(
                "course_list",
                "列出当前请求者课程表",
                {"weekday": {"type": "integer", "minimum": 1, "maximum": 7}},
                [],
            ),
            _function(
                "course_add",
                "为当前请求者添加课程",
                {
                    "name": {"type": "string"},
                    "weekday": {"type": "integer"},
                    "sections": {"type": "string"},
                    "weeks": {"type": "string"},
                    "location": {"type": "string"},
                    "teacher": {"type": "string"},
                },
                ["name", "weekday", "sections", "weeks"],
            ),
            _function(
                "course_remind",
                "设置当前请求者课程私聊提醒",
                {"course_id": {"type": "integer"}, "minutes": {"type": ["integer", "null"]}},
                ["course_id", "minutes"],
            ),
            _function(
                "campus_query",
                "查询信息门户通知或第二课堂活动缓存",
                {
                    "source": {"type": "string", "enum": ["portal", "activity"]},
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                },
                ["source"],
            ),
            _function(
                "campus_subscribe",
                "开关当前请求者的信息门户或第二课堂私聊订阅",
                {
                    "source": {"type": "string", "enum": ["portal", "activity"]},
                    "enabled": {"type": "boolean"},
                },
                ["source", "enabled"],
            ),
            _function(
                "stats_context",
                "取得当前群最近 N 小时的确定性统计和受限群聊文本，供本轮分析或总结",
                {"hours": {"type": "integer", "minimum": 1, "maximum": 24}},
                ["hours"],
            ),
            _function(
                "wife_show",
                "查看当前请求者在当前群的今日 wife",
                {},
                [],
            ),
            _function(
                "wife_random",
                "为当前请求者抽取当前群今日 wife",
                {},
                [],
            ),
            _function(
                "poke_once",
                "以受限 AI_MEMBER_DELEGATE 在当前群戳指定群友一次",
                {"target_user_id": {"type": "string", "pattern": "^[0-9]+$"}},
                ["target_user_id"],
            ),
            _function(
                "stick_once",
                "给当前被回复消息贴一次已知数字 emoji_id",
                {"emoji_id": {"type": "integer", "minimum": 1}},
                ["emoji_id"],
            ),
        ]

    async def execute(self, name: str, arguments: dict[str, Any], context: ToolExecutionContext) -> str:
        if self.activity_log is not None:
            await self.activity_log.record(
                "tool",
                f"AI 调用工具 {name}，参数：{json.dumps(arguments, ensure_ascii=False, default=str)[:1200]}",
                status="started",
                user_id=context.requested_by,
                group_id=context.group_id,
                details={"tool": name, "arguments": arguments},
            )
        try:
            result = await self._execute(name, arguments, context)
        except Exception as exc:
            if self.activity_log is not None:
                await self.activity_log.record(
                    "tool",
                    f"AI 工具 {name} 执行异常：{type(exc).__name__}: {exc}",
                    status="failed",
                    user_id=context.requested_by,
                    group_id=context.group_id,
                    details={"tool": name, "error_type": type(exc).__name__},
                )
            raise
        if self.activity_log is not None:
            try:
                payload = json.loads(result)
            except json.JSONDecodeError:
                payload = {"success": False, "raw": result[:1200]}
            await self.activity_log.record(
                "tool",
                f"AI 工具 {name} 执行{'成功' if payload.get('success') else '失败'}："
                f"{json.dumps(payload, ensure_ascii=False, default=str)[:1200]}",
                status="success" if payload.get("success") else "failed",
                user_id=context.requested_by,
                group_id=context.group_id,
                details={"tool": name, "result": payload},
            )
        return result

    async def _execute(self, name: str, arguments: dict[str, Any], context: ToolExecutionContext) -> str:
        if context.requested_by != context.subject_user_id:
            return _result(False, error="AI 不得指定无关用户为数据主体")
        try:
            if name == "help_lookup":
                spec = command_registry.get(str(arguments.get("command") or ""))
                if spec:
                    return _result(
                        True,
                        command=spec.name,
                        usage=spec.usage,
                        permission=spec.permission.value,
                        ai_callable=spec.ai_callable,
                        description=spec.description,
                    )
                return _result(True, commands=[spec.name for spec in command_registry.all()])
            if name == "calculate":
                return _result(True, value=format_result(calculate(str(arguments["expression"]))))
            if name == "ddl_add":
                if not self._feature_enabled("ddl", context):
                    return _result(False, error="当前群已关闭 DDL 功能")
                created = self.ddl.add(
                    context.subject_user_id,
                    str(arguments["deadline"]),
                    str(arguments["content"]),
                    reminder=str(arguments["reminder"]) if arguments.get("reminder") else None,
                )
                return _result(
                    True,
                    ddl=format_ddl(created.record),
                    reminder_reason=created.reminder_reason,
                )
            if name == "ddl_list":
                if not self._feature_enabled("ddl", context):
                    return _result(False, error="当前群已关闭 DDL 功能")
                status = str(arguments.get("status") or "todo")
                items = self.ddl.list(context.subject_user_id, status)
                return _result(True, items=[format_ddl(item) for item in items])
            if name == "ddl_show":
                item = self.ddl.repository.get_ddl(context.subject_user_id, int(arguments["ddl_id"]))
                return _result(
                    bool(item),
                    ddl=format_ddl(item) if item else None,
                    error=None if item else "DDL 不存在",
                )
            if name == "ddl_edit":
                item = self.ddl.edit(
                    context.subject_user_id,
                    int(arguments["ddl_id"]),
                    deadline_text=str(arguments["deadline"]) if arguments.get("deadline") else None,
                    content=str(arguments["content"]) if arguments.get("content") else None,
                )
                return _result(
                    bool(item),
                    ddl=format_ddl(item) if item else None,
                    error=None if item else "DDL 不存在或已完成",
                )
            if name == "ddl_remind":
                changed = self.ddl.set_reminder(
                    context.subject_user_id, int(arguments["ddl_id"]), str(arguments["advance"])
                )
                return _result(changed, error=None if changed else "DDL 不存在或已完成")
            if name == "ddl_done":
                if not self._feature_enabled("ddl", context):
                    return _result(False, error="当前群已关闭 DDL 功能")
                changed = self.ddl.done(context.subject_user_id, int(arguments["ddl_id"]))
                return _result(changed, error=None if changed else "DDL 不存在或已经完成")
            if name == "recommend_random":
                if not self._feature_enabled("recommendation", context):
                    return _result(False, error="当前群已关闭推荐功能")
                pool = _pool(arguments["pool"])
                item = self.repository.choose_recommendation(pool, str(arguments.get("path") or ""))
                return _result(
                    bool(item),
                    item=item.content if item else None,
                    error=None if item else "推荐池为空",
                )
            if name == "recommend_add":
                if not self._feature_enabled("recommendation", context):
                    return _result(False, error="当前群已关闭推荐功能")
                pool = _pool(arguments["pool"])
                item_id = self.repository.add_recommendation(
                    pool,
                    str(arguments.get("path") or ""),
                    str(arguments["content"]),
                    float(arguments.get("weight") or 1),
                    (),
                    context.requested_by,
                )
                return _result(True, recommendation_id=item_id, delegated_capability="AI_MEMBER_DELEGATE")
            if name == "course_list":
                rows = self.courses.list(context.subject_user_id, arguments.get("weekday"))
                return _result(
                    True,
                    courses=[
                        {
                            "id": row.course_id,
                            "name": row.name,
                            "weekday": row.weekday,
                            "sections": f"{row.start_section}-{row.end_section}",
                            "weeks": row.weeks,
                            "location": row.location,
                            "teacher": row.teacher,
                        }
                        for row in rows
                    ],
                )
            if name == "course_add":
                course_id = self.courses.add(
                    context.subject_user_id,
                    str(arguments["name"]),
                    parse_weekday(str(arguments["weekday"])),
                    parse_sections(str(arguments["sections"])),
                    str(arguments["weeks"]),
                    str(arguments.get("location") or ""),
                    str(arguments.get("teacher") or ""),
                )
                return _result(True, course_id=course_id)
            if name == "course_remind":
                changed = self.courses.set_reminder(
                    context.subject_user_id, int(arguments["course_id"]), arguments.get("minutes")
                )
                return _result(bool(changed), changed=changed)
            if name == "campus_query":
                source = str(arguments["source"])
                rows = self.repository.query_source_items(
                    source, str(arguments.get("query") or ""), int(arguments.get("limit") or 10)
                )
                return _result(True, items=rows)
            if name == "campus_subscribe":
                source = str(arguments["source"])
                self.repository.set_subscription(
                    source, "user", context.subject_user_id, bool(arguments["enabled"]), context.requested_by
                )
                return _result(True, source=source, enabled=bool(arguments["enabled"]))
            if name == "stats_context":
                if not context.group_id:
                    return _result(False, error="统计和总结只能在群聊中使用")
                window = AnalyticsService(self.log_root).load_group(context.group_id, int(arguments["hours"]))
                stats = AnalyticsService.deterministic(window)
                return _result(
                    True,
                    deterministic=format_deterministic(window, stats),
                    transcript=AnalyticsService.ai_transcript(window),
                )
            if name == "wife_show":
                if not context.group_id:
                    return _result(False, error="wife 只能在群聊中使用")
                pair = self.group_repository.get_wife(
                    context.group_id,
                    context.subject_user_id,
                    datetime.now(ZoneInfo("Asia/Shanghai")).date(),
                )
                return _result(
                    bool(pair),
                    partner_id=pair.partner_id if pair else None,
                    error=None if pair else "今天还没有配对",
                )
            if name == "wife_random":
                if not context.group_id or context.bot is None:
                    return _result(False, error="wife 只能在可访问群成员的群聊中使用")
                members = await context.bot.get_group_member_list(group_id=int(context.group_id))
                excluded = {context.subject_user_id, str(context.bot.self_id)}
                candidates = [
                    str(row.get("user_id"))
                    for row in members
                    if str(row.get("user_id", "")).isdigit() and str(row.get("user_id")) not in excluded
                ]
                pair = self.group_repository.assign_wife(
                    context.group_id,
                    context.subject_user_id,
                    candidates,
                    datetime.now(ZoneInfo("Asia/Shanghai")).date(),
                )
                return _result(True, partner_id=pair.partner_id)
            if name == "poke_once":
                if not context.group_id or context.bot is None:
                    return _result(False, error="只能在群聊中戳人")
                await context.bot.call_api(
                    "group_poke", group_id=int(context.group_id), user_id=int(arguments["target_user_id"])
                )
                return _result(True, delegated_capability="AI_MEMBER_DELEGATE")
            if name == "stick_once":
                if context.bot is None or not context.replied_message_id:
                    return _result(False, error="当前消息没有回复目标")
                await context.bot.call_api(
                    "set_msg_emoji_like",
                    message_id=int(context.replied_message_id),
                    emoji_id=int(arguments["emoji_id"]),
                    set=True,
                )
                return _result(True, delegated_capability="AI_MEMBER_DELEGATE")
        except (KeyError, TypeError, ValueError) as exc:
            return _result(False, error=str(exc))
        return _result(False, error=f"未知或未授权的 AI 工具：{name}")

    def _feature_enabled(self, feature: str, context: ToolExecutionContext) -> bool:
        return context.group_id is None or self.features.status(feature, context.group_id).enabled


def _function(
    name: str,
    description: str,
    properties: dict[str, Any],
    required: list[str],
) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


def _pool(value: Any) -> str:
    pool = str(value)
    if pool not in {"activity", "food", "music"}:
        raise ValueError("pool 必须是 activity、food 或 music")
    return pool


def _result(success: bool, **values: Any) -> str:
    return json.dumps({"success": success, **values}, ensure_ascii=False)
