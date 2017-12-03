# -*- coding: utf-8 -*-

import asyncio
import random
import time

import discord
from discord.ext import commands

from . import utils


class Rollback(Exception):
    pass


class CoinDrop:
    def __init__(self, bot):
        self.bot = bot
        self.last_drop = time.monotonic()
        self.wait_until = self.last_drop
        self.drop_lock = asyncio.Lock()
        self.no_drops = False
        self.no_places = True

    async def on_message(self, message):
        pick_strings = self.bot.config.get("pick_strings", ['pick'])

        if message.content.lower().startswith(tuple(f".{pick_string}" for pick_string in pick_strings)):
            await message.delete()
            return

        if self.no_drops:
            return

        if message.content.startswith("."):
            return  # do not drop coins on commands

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
            plural_coin = currency_name.get("plural", "coins")

            drop_strings = self.bot.config.get("drop_strings",
                                               ["A {singular} dropped! Type `.{cmd}` to {cmd} it!"])

            exponential_element = min(max((time.monotonic() - self.wait_until) / recovery, 0), 1)

            weight = exponential_element ** 3

            probability = weight * drop_chance

            pick_string = random.choice(pick_strings)
            drop_string = random.choice(drop_strings)

            if random.random() < probability:
                drop_message = await message.channel.send(drop_string.format(singular=singular_coin, plural=plural_coin,
                                                                             cmd=pick_string))
                self.last_drop = time.monotonic()
                self.wait_until = self.last_drop + cooldown

                try:
                    def pick_check(m):
                        return m.channel.id == message.channel.id and m.content.lower() == f".{pick_string}"

                    drop_time = time.monotonic()
                    pick_message = await self.bot.wait_for('message', check=pick_check, timeout=90)
                    pick_time = time.monotonic()
                    self.bot.logger.info(f"User {pick_message.author.id} picked up a random coin in "
                                         f"{pick_time-drop_time} seconds.")
                except asyncio.TimeoutError:
                    await drop_message.delete()
                    return
                else:
                    self.bot.loop.create_task(self.add_coin(pick_message.author.id, pick_message.created_at))
                    await drop_message.delete()
                    await message.channel.send(f"{pick_message.author.mention} got the {singular_coin}!")

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

    @commands.cooldown(1, 4, commands.BucketType.user)
    @commands.cooldown(1, 1.5, commands.BucketType.channel)
    @commands.command("check")
    async def check_command(self, ctx: commands.Context):
        """Check your coin balance"""
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

    @commands.cooldown(1, 4, commands.BucketType.user)
    @commands.cooldown(1, 1.5, commands.BucketType.channel)
    @commands.command("place", enabled=False)
    async def place_command(self, ctx: commands.Context):
        """Place down a coin for others to pick up"""
        if self.no_places:
            return

        if not self.bot.db_available.is_set():
            return  # don't allow coin place if we can't connect to the db yet

        if self.drop_lock.locked():
            return  # don't allow coin place if one is already dropped at random

        currency_name = self.bot.config.get("currency", {})
        singular_coin = currency_name.get("singular", "coin")
        plural_coin = currency_name.get("plural", "coins")
        pick_strings = self.bot.config.get("pick_strings", ['pick'])

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

                        pick_string = random.choice(pick_strings)

                        drop_message = await ctx.send(f"{ctx.author.mention} dropped a {singular_coin}! "
                                                      f"Type `.{pick_string}` to {pick_string} it!")

                        try:
                            def pick_check(m):
                                return m.channel.id == ctx.channel.id and m.content.lower() == f".{pick_string}"

                            drop_time = time.monotonic()
                            pick_message = await self.bot.wait_for('message', check=pick_check, timeout=90)
                            pick_time = time.monotonic()
                            self.bot.logger.info(f"User {pick_message.author.id} picked up a placed coin in "
                                                 f"{pick_time-drop_time} seconds.")
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
                            await ctx.send(f"{pick_message.author.mention} grabbed "
                                           f"{ctx.author.mention}'s {singular_coin}!")

                except Rollback:
                    pass

    @commands.cooldown(1, 4, commands.BucketType.user)
    @commands.cooldown(1, 1.5, commands.BucketType.channel)
    @commands.command("stats")
    async def stats_command(self, ctx: commands.Context):
        """Coin leaderboard"""
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

    @commands.has_permissions(ban_members=True)
    @commands.command("reset_user")
    async def reset_user(self, ctx: commands.Context, user: discord.User):
        """Reset users' coin accounts"""
        if not self.bot.db_available.is_set():
            await ctx.send("No connection to database.")
            return

        async with self.bot.db.acquire() as conn:
            record = await conn.fetchrow("SELECT * FROM currency_users WHERE user_id = $1", user.id)
            if record is None:
                await ctx.send("This user doesn't have a database entry.")
                return

            await ctx.send(f"Are you sure? This user has {record['coins']} coins, last picking one up at "
                           f"{record['last_picked']} UTC. (type 'confirm' or 'cancel')")

            def wait_check(msg):
                return msg.author.id == ctx.author.id and msg.content.lower() in ("confirm", "cancel")

            try:
                validate_message = await self.bot.wait_for('message', check=wait_check, timeout=30)
            except asyncio.TimeoutError:
                await ctx.send(f"Timed out request to reset {user.id}.")
                return
            else:
                if validate_message.content.lower() == 'cancel':
                    await ctx.send("Cancelled.")
                    return

                async with conn.transaction():
                    await conn.execute("DELETE FROM currency_users WHERE user_id = $1", user.id)

                await ctx.send(f"Cleared entry for {user.id}")

    @commands.has_permissions(ban_members=True)
    @commands.check(utils.check_granted_server)
    @commands.command("drop_setting")
    async def drop_setting(self, ctx: commands.Context, setting: bool):
        """Set whether coins will drop at random or not."""
        self.no_drops = not setting
        await ctx.send(f"{'Will' if setting else 'Will **NOT**'} do random drops.")

    @commands.has_permissions(ban_members=True)
    @commands.check(utils.check_granted_server)
    @commands.command("place_setting")
    async def place_setting(self, ctx: commands.Context, setting: bool):
        """Set whether users can place coins or not."""
        self.no_places = not setting
        await ctx.send(f"{'Will' if setting else 'Will **NOT**'} allow users to place new coins.")


def setup(bot):
    bot.add_cog(CoinDrop(bot))
