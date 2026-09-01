from __future__ import annotations

import os

from nonebot.adapters.onebot.v11 import MessageSegment
from nonebot.matcher import Matcher
from nonebot.permission import Permission

from amadeus_bot.bootstrap import get_container
from amadeus_bot.domain.permissions import PermissionLevel
from amadeus_bot.services.event_utils import event_group_id as event_group_id
from amadeus_bot.services.event_utils import onebot_message as onebot_message
from amadeus_bot.services.event_utils import reply_message_id as reply_message_id


async def member_allowed(event) -> bool:
    return get_container().permissions.has_role(event.get_user_id(), PermissionLevel.MEMBER)


MEMBER_PERMISSION = Permission(member_allowed)


async def finish_text_or_image(
    matcher: Matcher,
    text: str,
    *,
    title: str,
    force_image: bool = False,
    variant: str = "default",
) -> None:
    threshold = int(os.getenv("AMADEUS_RENDER_TEXT_THRESHOLD", "500"))
    if force_image or len(text) >= threshold:
        try:
            image_path = await get_container().renderer.render_text(text, title=title, variant=variant)
        except Exception:
            pass
        else:
            await matcher.finish(MessageSegment.image(image_path.resolve().as_uri()))
    await matcher.finish(text)
