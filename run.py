# -*- coding: utf-8 -*-
import asyncio
import uvloop

import json
import logging

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

# TODO: use YAML instead
with open("config.json", 'rb') as fp:
    config = json.load(fp)

token = config.pop("token")


bot = DropBot('.', config=config)

bot.run(token)
