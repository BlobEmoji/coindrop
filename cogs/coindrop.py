# -*- coding: utf-8 -*-

import asyncio
import random
import time

import discord
from discord.ext import commands


class Rollback(Exception):
    pass


class CoinDrop:
    def __init__(self, bot):
        self.bot = bot
        self.last_drop = time.monotonic()
        self.wait_until = self.last_drop
        self.drop_lock = asyncio.Lock()

    async def on_message(self, message):
        if message.channel.id not in self.bot.config.get("drop_channels", []):
            return

        if self.drop_lock.locked():
            return

        async with self.drop_lock:
            cooldown = self.bot.config.get("cooldown_time", 20)
            recovery = self.bot.config.get("recovery_time", 10)
            drop_chance = self.bot.config.get("drop_chance", 0.1)
            currency_name = self.bot.config.get("currency", {})
            singular_coin = currency_name.get("singular", "coin")

            exponential_element = min(max((time.monotonic() - self.wait_until) / recovery, 0), 1)

            weight = exponential_element ** 3

            probability = weight * drop_chance

            if random.random() < probability:
                drop_message = await message.channel.send(f"A {singular_coin} dropped! Type `.pick` to pick it up!")
                self.last_drop = time.monotonic()
                self.wait_until = self.last_drop + cooldown

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
                SET coins = currency_users.coins + 1,
                last_picked = $2
                """, user_id, when)

    @commands.cooldown(1, 5, commands.BucketType.channel)
    @commands.command("check")
    async def check_command(self, ctx: commands.Context):
        if not self.bot.db_available.is_set():
            return

        currency_name = self.bot.config.get("currency", {})
        singular_coin = currency_name.get("singular", "coin")
        plural_coin = currency_name.get("plural", "coins")

        async with self.bot.db.acquire() as conn:
            record = await conn.fetchrow("SELECT coins FROM currency_users WHERE user_id = $1", ctx.author.id)
            if record is None:
                await ctx.send(f"You haven't picked up any {plural_coin} yet!")
            else:
                coins = record["coins"]
                coin_text = f"{coins} {singular_coin if coins==1 else plural_coin}"
                await ctx.send(f"{ctx.author.mention} You have {coin_text}.")

    @commands.cooldown(1, 5, commands.BucketType.channel)
    @commands.command("place")
    async def place_command(self, ctx: commands.Context):
        if not self.bot.db_available.is_set():
            return  # don't allow coin place if we can't connect to the db yet

        if self.drop_lock.locked():
            return  # don't allow coin place if one is already dropped at random

        currency_name = self.bot.config.get("currency", {})
        singular_coin = currency_name.get("singular", "coin")
        plural_coin = currency_name.get("plural", "coins")

        async with self.drop_lock:  # when someone places a coin, lock random coins from dropping
            async with self.bot.db.acquire() as conn:
                try:
                    async with conn.transaction():
                        record = await conn.fetchrow("""
                        UPDATE currency_users
                        SET coins = coins - 1
                        WHERE user_id = $1 AND coins > 0
                        RETURNING user_id, coins
                        """, ctx.author.id)

                        if record is None:
                            await ctx.send(f"You don't have any {plural_coin} to drop!")
                            return

                        drop_message = await ctx.send(f"{ctx.author.mention} dropped a {singular_coin}! "
                                                      f"Type `.pick` to pick it up!")

                        try:
                            def pick_check(m):
                                return m.channel.id == ctx.channel.id and m.content.lower() == ".pick"

                            pick_message = await self.bot.wait_for('message', check=pick_check, timeout=90)
                        except asyncio.TimeoutError:
                            await drop_message.delete()
                            await ctx.send(f"{ctx.author.mention} Nobody picked up your {singular_coin}, so "
                                           f"it's been returned to your pocket. Woosh!")
                            raise Rollback() from None
                        else:
                            await conn.execute("""
                            INSERT INTO currency_users (user_id, coins, last_picked)
                            VALUES ($1, 1, $2)
                            ON CONFLICT (user_id) DO UPDATE
                            SET coins = currency_users.coins + 1,
                            last_picked = $2
                            """, pick_message.author.id, pick_message.created_at)
                            await drop_message.delete()
                            await pick_message.delete()

                except Rollback:
                    pass

    @commands.cooldown(1, 5, commands.BucketType.channel)
    @commands.command("stats")
    async def stats_command(self, ctx: commands.Context):
        if not self.bot.db_available.is_set():
            return

        currency_name = self.bot.config.get("currency", {})
        singular_coin = currency_name.get("singular", "coin")
        plural_coin = currency_name.get("plural", "coins")

        async with self.bot.db.acquire() as conn:
            records = await conn.fetch("""
            SELECT * FROM currency_users
            ORDER BY -coins
            LIMIT 5
            """)

            listing = []
            for index, record in enumerate(records):
                coins = record["coins"]
                coin_text = f"{coins} {singular_coin if coins==1 else plural_coin}"
                listing.append(f"{index+1}: <@{record['user_id']}> with {coin_text}")

        await ctx.send(embed=discord.Embed(description="\n".join(listing), color=0xff0000))


def setup(bot):
    bot.add_cog(CoinDrop(bot))
