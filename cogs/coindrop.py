# -*- coding: utf-8 -*-

import random
import time


class CoinDrop:
    def __init__(self, bot):
        self.bot = bot
        self.last_drop = time.monotonic()

    async def on_message(self, message):
        if message.channel.id not in self.bot.config.get("drop_channels", []):
            return

        cooldown = min(max((time.monotonic() - self.last_drop) / self.bot.config.get("cooldown_time", 20), 0), 1)

        weight = cooldown ** 3

        probability = weight * self.bot.config.get("drop_chance", 0.1)

        if random.random() < probability:
            # TODO: coin drop logic here
            ...


def setup(bot):
    bot.add_cog(CoinDrop(bot))
