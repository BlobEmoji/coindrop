# -*- coding: utf-8 -*-

import asyncio
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
            drop_message = await message.channel.send("A coin dropped! Type `.pick` to pick it up!")

            try:
                def pick_check(m):
                    return m.channel.id == message.channel.id and m.content.lower() == ".pick"

                pick_message = await self.bot.wait_for('message', check=pick_check, timeout=90)
            except asyncio.TimeoutError:
                await drop_message.delete()
                return
            else:
                self.bot.loop.create_task(self.add_coin(pick_message.author.id, pick_message.created_at))
                await drop_message.delete()
                await pick_message.delete()

    async def add_coin(self, user_id, when):
        await self.bot.db_available.wait()

        async with self.bot.db.acquire() as conn:
            async with conn.transaction():
                await conn.execute("""
                INSERT INTO currency_users (user_id, coins, last_picked)
                VALUES ($1, 1, $2)
                ON CONFLICT (user_id) DO UPDATE
                SET coins = coins + 1,
                last_picked = $2
                """, user_id, when)


def setup(bot):
    bot.add_cog(CoinDrop(bot))
