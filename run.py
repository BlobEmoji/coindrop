# -*- coding: utf-8 -*-
import asyncio
import uvloop

import logging
import sys

import yaml

from bot import DropBot

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

with open("config.yaml", 'rb') as fp:
    config = yaml.safe_load(fp)

token = config.pop("token")


bot = DropBot('.', config=config)

bot.load_extension("jishaku")
bot.load_extension("cogs.coindrop")
bot.run(token)
