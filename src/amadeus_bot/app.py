from __future__ import annotations

import nonebot
from nonebot.adapters.onebot.v11 import Adapter

from amadeus_bot.settings import load_project_env

PLUGIN_MODULES = (
    "amadeus_bot.plugins.message_logger",
    "amadeus_bot.plugins.calc",
    "amadeus_bot.plugins.broadcast",
    "amadeus_bot.plugins.recommendations",
    "amadeus_bot.plugins.ddl",
    "amadeus_bot.plugins.member_admin",
    "amadeus_bot.plugins.utility",
    "amadeus_bot.plugins.wife",
    "amadeus_bot.plugins.group_content",
    "amadeus_bot.plugins.memory",
    "amadeus_bot.plugins.privacy",
    "amadeus_bot.plugins.campus",
    "amadeus_bot.plugins.courses",
    "amadeus_bot.plugins.logs",
    "amadeus_bot.plugins.issue_report",
    "amadeus_bot.plugins.data_admin",
    "amadeus_bot.plugins.feature_admin",
    "amadeus_bot.plugins.health",
    "amadeus_bot.plugins.chat",
    "amadeus_bot.plugins.scheduler",
    "amadeus_bot.plugins.help",
    "amadeus_bot.plugins.runtime_logging",
)


def create_app() -> None:
    load_project_env()
    nonebot.init()
    driver = nonebot.get_driver()
    driver.register_adapter(Adapter)
    for module_name in PLUGIN_MODULES:
        nonebot.load_plugin(module_name)


def main() -> None:
    create_app()
    nonebot.run()
