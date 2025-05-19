
import json
import base64
import re
import os
from collections import defaultdict

import discord
from discord.ext import commands
import aiohttp
import asyncio
from datetime import datetime, timedelta

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='(', intents=intents)

URLS_FILE = 'glitch_urls.json'
USERS_FILE = 'user_projects.json'
AUTOMSG_FILE = 'auto_messages.json'

scheduled_messages = {}  # Store scheduled message tasks
auto_messages = {}  # {channel_id: {"text": message_text}}

# Load auto messages from file
if os.path.exists(AUTOMSG_FILE):
    with open(AUTOMSG_FILE, 'r') as f:
        saved_messages = json.load(f)
        for channel_id, data in saved_messages.items():
            auto_messages[channel_id] = data

# Load existing URLs and user data
glitch_urls = defaultdict(set)
user_projects = defaultdict(list)  # {server_id: [{project: "", username: ""}]}

if os.path.exists(URLS_FILE):
    with open(URLS_FILE, 'r') as f:
        saved_urls = json.load(f)
        for server_id, urls in saved_urls.items():
            glitch_urls[server_id] = set(urls)

if os.path.exists(USERS_FILE):
    with open(USERS_FILE, 'r') as f:
        user_projects = json.load(f)

@bot.event
async def on_message(message):
    if message.author.bot:
        # Handle p2assistant messages (starboard and stats)
        if message.author.id == 854233015475109888:
            if "Rare ping:" in message.content or "Regional ping:" in message.content:
                if message.reference and message.reference.message_id:
                    try:
                        original_msg = await message.channel.fetch_message(message.reference.message_id)
                        if original_msg.author.id == 716390085896962058:  # Poketwo
                            starboard = discord.utils.get(message.guild.channels, name="🌟︱starboard")
                            if starboard:
                                embed = discord.Embed(color=discord.Color.gold())
                                embed.set_image(url=original_msg.attachments[0].url if original_msg.attachments else None)
                                embed.add_field(name="Original Message", value=f"[Jump to message]({original_msg.jump_url})")
                                await starboard.send(embed=embed)
                    except:
                        pass
            # Handle stats message
            elif ":" in message.content and "Best name" in message.content:
                try:
                    content_before_colon = message.content.split(":", 1)[0].strip()
                    await message.channel.edit(topic=content_before_colon)
                except:
                    pass
        # Handle Poketwo messages
        elif message.author.id == 716390085896962058:
            if "in the daycare have produced" in message.content:
                await message.channel.send("<@1131217949672353832> You got an Egg! 🥚🥚🥚")
            return
        # Handle congratulations message
        if "Congratulations" in message.content and "You caught a" in message.content and message.author.id == 716390085896962058:
            try:
                await message.channel.edit(topic="")
            except:
                pass
            return

    # Check for project-username pattern
    lines = message.content.split('\n')
    if len(lines) == 3 and lines[2].startswith('by '):
        project = lines[0].strip()
        username = lines[1].strip()
        by_username = lines[2][3:].strip()
        
        if username == by_username:
            server_id = str(message.guild.id)
            if server_id not in user_projects:
                user_projects[server_id] = []
            
            entry = {"project": project, "username": username}
            if entry not in user_projects[server_id]:
                user_projects[server_id].append(entry)
                with open(USERS_FILE, 'w') as f:
                    json.dump(user_projects, f)

    await bot.process_commands(message)

@bot.command(name='list')
async def list_projects(ctx):
    server_id = str(ctx.guild.id)
    if server_id not in user_projects or not user_projects[server_id]:
        await ctx.send("No projects recorded in this server yet!")
        return

    embed = discord.Embed(title="Projects List", color=discord.Color.blue())
    for idx, entry in enumerate(user_projects[server_id], 1):
        embed.add_field(
            name=f"{idx}) {entry['project']}", 
            value=f"by {entry['username']}", 
            inline=False
        )
    await ctx.send(embed=embed)

@bot.command(name='ids')
async def list_ids(ctx):
    all_usernames = set()
    for server_projects in user_projects.values():
        for entry in server_projects:
            all_usernames.add(entry['username'])
    
    if not all_usernames:
        await ctx.send("No usernames recorded yet!")
        return

    message = "Recorded usernames:\n"
    for idx, username in enumerate(sorted(all_usernames), 1):
        message += f"{idx}) {username}\n"
    
    await ctx.send(message)

@bot.command(name='detect')
async def detect(ctx):
    server_id = str(ctx.guild.id)
    if server_id not in glitch_urls or not glitch_urls[server_id]:
        await ctx.send("No Glitch URLs detected in this server yet!")
        return

    message = "Detected Glitch Projects:\n\n"
    for project_name in sorted(glitch_urls[server_id]):
        transformed_url = f"https://glitch.com/~{project_name}"
        message += f"• {transformed_url}\n"

    await ctx.send(message)

@bot.command(name='cmd')
async def cmd(ctx):
    embed = discord.Embed(title="Available Commands", color=discord.Color.green())
    commands_list = [
        ("detect", "Shows detected Glitch URLs in this server"),
        ("list", "Shows numbered projects with usernames for this server"),
        ("ids", "Shows all unique usernames across servers"),
        ("cmd", "Shows this command list"),
        ("run", "Sends a message every 3 minutes (admin only)"),
        ("runall", "Sends multiple messages in different channels: (channelid) message, (channelid2) message2"),
        ("remove", "Stops the auto-message in the current channel"),
        ("runstatus", "Shows channels with active auto-messages"),
        ("check", "Checks if a user has 'special access' role"),
        ("listremove", "Removes an item from the project list by index"),
        ("clear", "Clears channel topics in the server")
    ]
    
    for cmd_name, description in commands_list:
        embed.add_field(name=f"({cmd_name}", value=description, inline=False)
    
    await ctx.send(embed=embed)

async def send_repeated_message(ctx, message):
    while True:
        await ctx.send(message)
        await asyncio.sleep(180)  # 3 minutes

@bot.command(name='run')
async def run(ctx, *, text):
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("This command is only available for administrators!")
        return
        
    channel_id = str(ctx.channel.id)
    if channel_id in scheduled_messages:
        scheduled_messages[channel_id].cancel()
    
    task = asyncio.create_task(send_repeated_message(ctx, text))
    scheduled_messages[channel_id] = task
    await ctx.send(f"Started sending '{text}' every 3 minutes in this channel. Data saved in auto_messages.json")
    
    # Save auto message data
    auto_messages[channel_id] = {"text": text}
    with open(AUTOMSG_FILE, 'w') as f:
        json.dump(auto_messages, f)

@bot.command(name='runall')
async def runall(ctx, *, content):
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("This command is only available for administrators!")
        return

    try:
        # Split by comma and strip whitespace
        channel_messages = [pair.strip() for pair in content.split(',')]
        
        for pair in channel_messages:
            # Split channel ID and message
            parts = pair.split(')', 1)
            if len(parts) != 2:
                continue
                
            channel_id = parts[0].strip('( ')
            message = parts[1].strip()
            
            try:
                channel = bot.get_channel(int(channel_id))
                if channel:
                    if channel_id in scheduled_messages:
                        scheduled_messages[channel_id].cancel()
                    
                    task = asyncio.create_task(send_repeated_message(channel, message))
                    scheduled_messages[channel_id] = task
                    
                    # Save auto message data
                    auto_messages[channel_id] = {"text": message}
                    with open(AUTOMSG_FILE, 'w') as f:
                        json.dump(auto_messages, f)
                        
                    await ctx.send(f"Started sending messages in channel {channel.name}")
            except:
                await ctx.send(f"Failed to setup messages for channel {channel_id}")
                
    except Exception as e:
        await ctx.send(f"Error processing command: {str(e)}")

@bot.command(name='remove')
async def remove(ctx):
    channel_id = str(ctx.channel.id)
    if channel_id in scheduled_messages:
        scheduled_messages[channel_id].cancel()
        del scheduled_messages[channel_id]
        if channel_id in auto_messages:
            del auto_messages[channel_id]
            with open(AUTOMSG_FILE, 'w') as f:
                json.dump(auto_messages, f)
        await ctx.send("Auto-message stopped in this channel.")
    else:
        await ctx.send("No auto-message running in this channel.")

@bot.command(name='runstatus')
async def runstatus(ctx):
    server_channels = {str(channel.id): channel.name for channel in ctx.guild.channels}
    active_channels = [server_channels[cid] for cid in scheduled_messages.keys() if cid in server_channels]
    
    if not active_channels:
        await ctx.send("No auto-messages are currently running in this server.")
        return
        
    message = "Active auto-messages:\n"
    for i, channel in enumerate(active_channels, 1):
        message += f"{i}. #{channel}\n"
    await ctx.send(message)

@bot.command(name='check')
async def check(ctx, user: discord.Member):
    results = []
    for guild in bot.guilds:
        member = guild.get_member(user.id)
        if member:
            role = discord.utils.get(guild.roles, name="special access")
            if role and role in member.roles:
                results.append(guild.name)
    
    if results:
        await ctx.send(f"{user.name} has 'special access' in: {', '.join(results)}")
    else:
        await ctx.send(f"{user.name} doesn't have 'special access' in any server.")

@bot.command(name='clear')
async def clear(ctx):
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("This command is only available for administrators!")
        return
        
    status_msg = await ctx.send("Checking channels with topics...")
    success = 0
    failed = 0
    
    channels_with_topics = [channel for channel in ctx.guild.text_channels if channel.topic]
    if not channels_with_topics:
        await status_msg.edit(content="No channels with topics found!")
        return
        
    await status_msg.edit(content=f"Found {len(channels_with_topics)} channels with topics. Clearing...")
    
    for channel in channels_with_topics:
        try:
            await channel.edit(topic="")
            success += 1
            await asyncio.sleep(1)  # Reduced delay since we're processing fewer channels
        except discord.errors.HTTPException as e:
            if e.code == 429:  # Rate limit error
                retry_after = e.retry_after
                await status_msg.edit(content=f"Rate limited. Waiting {retry_after:.2f} seconds...")
                await asyncio.sleep(retry_after)
                try:
                    await channel.edit(topic="")
                    success += 1
                except:
                    failed += 1
            else:
                failed += 1
        except:
            failed += 1
            
    await status_msg.edit(content=f"Finished! Cleared {success} channel topics. Failed to clear {failed} channels.")

@bot.command(name='listremove')
async def listremove(ctx, index: int):
    server_id = str(ctx.guild.id)
    if server_id not in user_projects or not user_projects[server_id]:
        await ctx.send("No projects recorded in this server!")
        return
        
    try:
        if 1 <= index <= len(user_projects[server_id]):
            removed = user_projects[server_id].pop(index - 1)
            with open(USERS_FILE, 'w') as f:
                json.dump(user_projects, f)
            await ctx.send(f"Removed project {removed['project']} by {removed['username']}")
        else:
            await ctx.send("Invalid index!")
    except:
        await ctx.send("Error removing project!")

# Run the bot
bot.run(os.getenv('DISCORD_TOKEN'))
