# -*- coding: utf-8 -*-
import asyncio
import datetime
import os

import logging
import sys

import toml

from bot import DropBot

try:
    import uvloop
except ImportError:
    pass
else:
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())


logging.getLogger('discord').setLevel(logging.INFO)
logging.getLogger('dropbot').setLevel(logging.DEBUG)

formatter = logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s')

handler = logging.FileHandler(filename='dropbot.log', encoding='utf-8', mode='a')
handler.setFormatter(formatter)

stream = logging.StreamHandler(stream=sys.stdout)
stream.setFormatter(formatter)

logging.getLogger().addHandler(handler)
logging.getLogger().addHandler(stream)


async def async_context_test(bot):
    await asyncio.wait_for(bot.db_available.wait(), timeout=15)

    # no virtual login since logic is too cramped right now

    coindrop = bot.get_cog("CoinDrop")
    await coindrop._add_coin(234567890123456789, datetime.datetime.utcnow())

    await bot.close()


def test_load_run():
    with open('config.toml', 'r', encoding='utf-8') as fp:
        config = toml.load(fp)

    config.pop("token")

    bot = DropBot('.', config=config)

    bot.load_extension("jishaku")
    bot.load_extension("cogs.coindrop")

    loop = asyncio.get_event_loop()
    loop.run_until_complete(async_context_test(bot))
