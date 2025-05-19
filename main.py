import discord
from discord.ext import commands
import os
import asyncio

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='(', intents=intents)

@bot.event
async def on_message(message):
    if message.author.bot:
        # Handle p2assistant messages (stats)
        if message.author.id == 854233015475109888:
            if ":" in message.content and "Best name" in message.content:
                try:
                    content_before_colon = message.content.split(":", 1)[0].strip()
                    await message.channel.edit(topic=content_before_colon)
                except:
                    pass
        # Handle congratulations message
        elif message.author.id == 716390085896962058:
            if "Congratulations" in message.content and "You caught a" in message.content:
                try:
                    await message.channel.edit(topic="")
                except:
                    pass
                return

    await bot.process_commands(message)

@bot.command(name='clear')
async def clear(ctx, limit: int = None):
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("This command is only available for administrators!")
        return

    current_channel_pos = ctx.channel.position
    channels_with_topics = [c for c in ctx.guild.text_channels if c.topic and c.position >= current_channel_pos]
    
    if not channels_with_topics:
        await ctx.send("No channels with topics found!")
        return

    if limit:
        channels_with_topics = channels_with_topics[:limit]

    success = 0
    failed = 0

    for channel in channels_with_topics:
        try:
            await channel.edit(topic="")
            success += 1
            await asyncio.sleep(1)  # 1 second delay
        except:
            failed += 1

    await ctx.send(f"Cleared {success} channel topics. Failed to clear {failed} channels.")

@commands.command(name='say')
async def say(ctx, limit: int = None):
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("This command is only available for administrators!")
        return
        
    channels = ctx.guild.text_channels
    current_channel_pos = ctx.channel.position

    # Get channels after current position up to the limit
    relevant_channels = [c for c in channels if c.position >= current_channel_pos and c.topic]
    if limit:
        relevant_channels = relevant_channels[:limit]

    sent_count = 0
    for channel in relevant_channels:
        if channel.topic:
            try:
                await channel.send(channel.topic)
                sent_count += 1
                await asyncio.sleep(1)  # 1 second delay
            except:
                pass

    await ctx.send(f"Sent messages in {sent_count} channels.")

# Add the command to the bot
bot.add_command(say)

bot.run(os.getenv('DISCORD_TOKEN'))
