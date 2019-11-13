# -*- coding: utf-8 -*-
import asyncio

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

with open('config.toml', 'r', encoding='utf-8') as fp:
    config = toml.load(fp)

token = config.pop("token")


bot = DropBot('.', config=config)

bot.load_extension("jishaku")
bot.load_extension("cogs.coindrop")
bot.run(token)
