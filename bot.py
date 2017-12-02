# -*- coding: utf-8 -*-

import asyncio
import asyncpg
import logging

from discord.ext import commands

logger = logging.getLogger("dropbot")


class DropBot(commands.Bot):
    def __init__(self, *args, config=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.config = config or {}
        self.db = None
        self.db_available = asyncio.Event()

        self.loop.create_task(self.acquire_pool())

    async def acquire_pool(self):
        credentials = self.config.pop("db_credentials")

        if credentials is None:
            logger.critical("Cannot connect to db, no credentials!")
            await self.logout()

        self.db = await asyncpg.create_pool(**credentials)
        self.db_available.set()

