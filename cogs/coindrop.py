# -*- coding: utf-8 -*-

import asyncio
import itertools
import random
import time
from io import BytesIO

from PIL import Image, ImageFilter

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
        self.last_blob = None
        self.blob_options = []
        self.last_coin_id = None
        self.additional_pickers = []

    async def on_message(self, message):
        max_additional_delay = self.bot.config.get("additional_delay", 5)

        immediate_time = time.monotonic()
        if (message.content.lower() in self.blob_options and
                immediate_time < (self.last_drop + max_additional_delay)):
            if message.author.id not in self.additional_pickers:
                self.additional_pickers.append(message.author.id)
                self.bot.loop.create_task(self.add_coin(message.author, message.created_at))
                self.bot.logger.info(f"User {message.author.id} additional-guessed blob ({self.last_coin_id}) in "
                                     f"{immediate_time-self.last_drop:.3f} seconds.")
                try:
                    await message.delete()
                except (discord.Forbidden, discord.HTTPException):
                    pass

                return

        if self.no_drops:
            return

        if message.content.startswith("."):
            return  # do not drop coins on commands

        if message.channel.id not in self.bot.config.get("drop_channels", []):
            return

        if self.drop_lock.locked():
            return

        recovery = self.bot.config.get("recovery_time", 10)
        drop_chance = self.bot.config.get("drop_chance", 0.1)

        exponential_element = min(max((time.monotonic() - self.wait_until) / recovery, 0), 1)

        weight = exponential_element ** 3

        probability = weight * drop_chance

        if random.random() < probability:
            coin_id = '%016x' % random.randrange(16**16)
            self.bot.logger.info(f"A natural blob has dropped ({coin_id})")
            self.last_coin_id = coin_id
            await self.perform_natural_drop(message.channel, coin_id)

    async def perform_natural_drop(self, channel, coin_id):
        async with self.drop_lock:
            max_additional_delay = self.bot.config.get("additional_delay", 5)

            cooldown = self.bot.config.get("cooldown_time", 20)

            currency_name = self.bot.config.get("currency", {})
            singular_coin = currency_name.get("singular", "coins")
            plural_coin = currency_name.get("plural", "coins")

            drop_strings = self.bot.config.get("drop_strings",
                                               ["I found this blob, but I can't remember what it's called! What was it?"])

            drop_string = random.choice(drop_strings)

            # round up all emojis and pick one
            guild_ids = self.bot.config.get("emoji_sources", [272885620769161216])
            guilds = tuple(filter(None, map(self.bot.get_guild, guild_ids)))
            emojis = tuple(filter(lambda x: not x.animated, itertools.chain(*[g.emojis for g in guilds])))

            if not emojis:
                self.bot.logger.error(f"I wanted to drop a blob, but I couldn't find any suitable emoji!")
                return

            emoji_chosen = random.choice(emojis)

            self.last_blob = emoji_chosen
            self.blob_options = [emoji_chosen.name, str(emoji_chosen)]

            if len(emoji_chosen.name) > 4:  # don't cut off 'blob'
                if emoji_chosen.name.startswith('blob'):  # allow omitting blob
                    self.blob_options.append(emoji_chosen.name[4:])
                elif emoji_chosen.name.endswith('blob'):
                    self.blob_options.append(emoji_chosen.name[:-4])
                elif emoji_chosen.name.startswith('google'):  # allow omitting google
                    self.blob_options.append(emoji_chosen.name[6:])

            # now let's go get it
            async with self.bot.session.get(emoji_chosen.url) as resp:
                emoji_bytes = await resp.read()

            # perform a filter and get new file
            file = await self.bot.loop.run_in_executor(None, self.do_filters, emoji_bytes)

            drop_message = await channel.send(drop_string, file=file)

            self.additional_pickers = []
            self.last_drop = time.monotonic()
            self.wait_until = self.last_drop + cooldown
            self.bot.loop.create_task(self.count_additional(channel, max_additional_delay))

            try:
                def pick_check(m):
                    return m.channel.id == channel.id and m.content.lower() in self.blob_options

                drop_time = time.monotonic()
                pick_message = await self.bot.wait_for('message', check=pick_check, timeout=90)
                pick_time = time.monotonic()
                self.bot.logger.info(f"User {pick_message.author.id} correctly guessed a blob ({coin_id}) in "
                                     f"{pick_time-drop_time:.3f} seconds.")
            except asyncio.TimeoutError:
                await drop_message.delete()
                return
            else:
                self.bot.loop.create_task(self.add_coin(pick_message.author, pick_message.created_at))
                if time.monotonic() < (self.last_drop + max_additional_delay):
                    await channel.send(f"{pick_message.author.mention} That's the one! Have 2 {plural_coin}!")
                else:
                    await channel.send(f"{pick_message.author.mention} That's the one! Have a {singular_coin}!")
                await asyncio.sleep(1)
                await drop_message.delete()

    def do_filters(self, image_bytes: bytes) -> discord.File:
        with Image.open(BytesIO(image_bytes)) as im:
            filter_chosen = random.choice((
                ImageFilter.GaussianBlur(radius=3),
                ImageFilter.UnsharpMask(),
                ImageFilter.ModeFilter(size=5),
                ImageFilter.MinFilter(size=3)
            ))

            with im.convert('RGBA').filter(filter_chosen) as im2:
                buffer = BytesIO()
                im2.save(buffer, 'png')

        buffer.seek(0)
        return discord.File(fp=buffer, filename="blob.png")

    async def _add_coin(self, user_id, when):
        await self.bot.db_available.wait()

        async with self.bot.db.acquire() as conn:
            async with conn.transaction():
                return conn.fetchval(
                    """
                    INSERT INTO currency_users (user_id, coins, last_picked)
                    VALUES ($1, 1, $2)
                    ON CONFLICT (user_id) DO UPDATE
                    SET coins = currency_users.coins + 1, last_picked = $2
                    RETURNING coins
                    """,
                    user_id,
                    when
                )

    async def add_coin(self, member, when):
        coins = await self._add_coin(member.id, when)

        rewards = self.bot.config.get('reward_roles', {})

        if coins not in rewards:
            return

        role = member.guild.get_role(rewards[coins])

        if role is None:
            self.bot.logger.warning(f'Failed to find reward role for {coins} coins.')
            return

        try:
            await member.add_roles(role, reason=f'Reached {coins} coins reward.')
        except discord.HTTPException:
            self.bot.logger.exception(f'Failed to add reward role for {coins} coins to {member!r}.')

    async def count_additional(self, channel, wait_time):
        await asyncio.sleep(wait_time)
        picker_count = len(self.additional_pickers)

        if picker_count > 1:
            await channel.send(f"(The correct blob was {self.last_blob}, "
                               f"{picker_count - 1} user(s) were fast enough to get a bonus coin)")
        else:
            await channel.send(f"(The correct blob was {self.last_blob}")

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

            try:
                if record is None:
                    await ctx.author.send(f"You haven't got any {plural_coin} yet!")
                else:
                    coins = record["coins"]
                    coin_text = f"{coins} {singular_coin if coins==1 else plural_coin}"
                    await ctx.author.send(f"You have {coin_text}.")
                await ctx.message.delete()
            except (discord.Forbidden, discord.HTTPException):
                pass

    @commands.has_permissions(ban_members=True)
    @commands.check(utils.check_granted_server)
    @commands.command("peek")
    async def peek_command(self, ctx: commands.Context, *, target: discord.Member):
        """Check another user's coin balance"""
        if not self.bot.db_available.is_set():
            return

        currency_name = self.bot.config.get("currency", {})
        singular_coin = currency_name.get("singular", "coin")
        plural_coin = currency_name.get("plural", "coins")

        async with self.bot.db.acquire() as conn:
            record = await conn.fetchrow("SELECT coins FROM currency_users WHERE user_id = $1", target.id)

            if record is None:
                await ctx.send(f"{target.mention} hasn't gotten any {plural_coin} yet!")
            else:
                coins = record["coins"]
                coin_text = f"{coins} {singular_coin if coins==1 else plural_coin}"
                await ctx.send(f"{target.mention} has {coin_text}.")

    @commands.cooldown(1, 4, commands.BucketType.user)
    @commands.cooldown(1, 1.5, commands.BucketType.channel)
    @commands.command("stats")
    async def stats_command(self, ctx: commands.Context, *, mode: str=''):
        """Coin leaderboard"""
        if not self.bot.db_available.is_set():
            return

        currency_name = self.bot.config.get("currency", {})
        singular_coin = currency_name.get("singular", "coin")
        plural_coin = currency_name.get("plural", "coins")

        limit = 8

        if mode == 'long' and (not ctx.guild or ctx.author.guild_permissions.ban_members):
            limit = 25

        async with self.bot.db.acquire() as conn:
            records = await conn.fetch("""
            SELECT * FROM currency_users
            ORDER BY coins DESC
            LIMIT $1
            """, limit)

            listing = []
            for index, record in enumerate(records):
                coins = record["coins"]
                coin_text = f"{coins} {singular_coin if coins==1 else plural_coin}"
                listing.append(f"{index+1}: <@{record['user_id']}> with {coin_text}")

        await ctx.send(embed=discord.Embed(description="\n".join(listing), color=0xff0000))

    @commands.has_permissions(ban_members=True)
    @commands.check(utils.check_granted_server)
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

            confirm_text = f"confirm {random.randint(0, 999999):06}"

            await ctx.send(f"Are you sure? This user has {record['coins']} coins, last picking one up at "
                           f"{record['last_picked']} UTC. (type '{confirm_text}' or 'cancel')")

            def wait_check(msg):
                return msg.author.id == ctx.author.id and msg.content.lower() in (confirm_text, "cancel")

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
    async def drop_setting(self, ctx: commands.Context, setting: bool=None):
        """Set whether coins will drop at random or not."""
        if setting is None:
            await ctx.send(f"Currently{' NOT' if self.no_drops else ''} doing random drops.")
            return

        self.no_drops = not setting
        await ctx.send(f"Will{'' if setting else ' **NOT**'} do random drops.")

    @staticmethod
    async def attempt_add_reaction(message: discord.Message, reaction):
        try:
            await message.add_reaction(reaction)
        except discord.HTTPException:
            pass

    @commands.has_permissions(ban_members=True)
    @commands.check(utils.check_granted_server)
    @commands.command("force_spawn")
    async def force_spawn_command(self, ctx: commands.Context, where: discord.TextChannel = None):
        """Force spawns a coin in a given channel."""
        if where is None:
            await ctx.send("You must specify a drop channel.")
            return

        if not self.bot.db_available.is_set():
            await ctx.send("Cannot access the db right now.")
            return

        if self.drop_lock.locked():
            await ctx.send("A coin is already spawned somewhere.")
            return

        if where.id not in self.bot.config.get("drop_channels", []):
            await ctx.send("Channel is not in drop list.")
            return

        coin_id = '%016x' % random.randrange(16 ** 16)
        self.bot.logger.info(f"A random coin was force dropped by {ctx.author.id} ({coin_id})")
        self.last_coin_id = coin_id
        self.bot.loop.create_task(self.attempt_add_reaction(ctx.message, "\N{WHITE HEAVY CHECK MARK}"))
        await self.perform_natural_drop(where, coin_id)


def setup(bot):
    bot.add_cog(CoinDrop(bot))
