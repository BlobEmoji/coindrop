# -*- coding: utf-8 -*-


def check_granted_server(ctx):
    allowed_channels = map(ctx.bot.get_channel, ctx.bot.config.get("drop_channels", []))
    allowed_guilds = set([channel.guild for channel in allowed_channels if channel])
    if ctx.guild in allowed_guilds:
        return True
    return False


def in_drop_channel(ctx):
    return ctx.channel.id in ctx.bot.config.get("drop_channels", [])
