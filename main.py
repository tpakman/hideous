import discord
import asyncio
import os
import json

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True  # Enable members intent to fetch guild members

client = discord.Client(intents=intents, command_prefix='.')

periodic_tasks = {}  # {channel_id: (task, message)}

TRIGGER_WORDS = set()

def load_trigger_words():
    try:
        with open('trigger_words.json', 'r') as f:
            global TRIGGER_WORDS
            TRIGGER_WORDS = set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        pass

def save_trigger_words(words):
    with open('trigger_words.json', 'w') as f:
        json.dump(list(words), f)

def normalize_text(text):
    return text.lower().strip()

load_trigger_words()

def load_periodic_messages():
    try:
        with open('periodic_messages.json', 'r') as f:
            data = json.load(f)
            for channel_id_str, message in data.items():
                channel_id = int(channel_id_str)
                task = client.loop.create_task(send_periodic_message(channel_id, message))
                periodic_tasks[channel_id] = (task, message)
    except (FileNotFoundError, json.JSONDecodeError):
        pass

def save_periodic_messages():
    data = {str(channel_id): message for channel_id, (_, message) in periodic_tasks.items()}
    with open('periodic_messages.json', 'w') as f:
        json.dump(data, f)
shiny_channel = None  # Channel to forward shiny pokemon messages to


async def log_fix_command(message, original_name, new_category_name, new_name):
    logs_channel = discord.utils.get(message.guild.channels, name='logs')
    if logs_channel:
        embed = discord.Embed(
            title="Channel Fix Log",
            color=discord.Color.green(),
            timestamp=message.created_at
        )
        embed.add_field(name="Command Used", value=message.content, inline=False)
        embed.add_field(name="Used By", value=message.author.mention, inline=True)
        embed.add_field(name="Original Channel", value=f"#{original_name}", inline=True)
        embed.add_field(name="New Category", value=new_category_name, inline=True)
        embed.add_field(name="New Name", value=f"#{new_name}", inline=True)
        embed.add_field(name="Channel ID", value=message.channel.id, inline=True)
        await logs_channel.send(embed=embed)


async def send_periodic_message(channel_id, message):
    channel = client.get_channel(channel_id)
    while True:
        try:
            if channel:
                await channel.send(message)
            await asyncio.sleep(300)  # 5 minutes interval
        except Exception as e:
            print(f"Error sending periodic message: {e}")
            await asyncio.sleep(300)

async def check_and_fix_permissions(guild):
    poketwo = guild.get_member(716390085896962058)
    if not poketwo:
        return "Poketwo bot not found in the server!"

    fixed_channels = []
    for channel in guild.text_channels:
        # Get the specific overwrite object for Poketwo
        overwrites = channel.overwrites_for(poketwo)
        if overwrites.view_channel is False or overwrites.send_messages is False:
            try:
                # Only remove the denied permissions by setting them to None
                if overwrites.view_channel is False:
                    overwrites.view_channel = None
                if overwrites.send_messages is False:
                    overwrites.send_messages = None

                await channel.set_permissions(poketwo, overwrite=overwrites)
                await channel.send("This Channel Has Been Unlocked for Poketwo!")
                fixed_channels.append(channel.name)
            except discord.Forbidden:
                print(f"Cannot modify permissions in {channel.name}")

    return fixed_channels

async def check_poketwo_permissions():
    await client.wait_until_ready()

    # Get the server
    guild = client.get_guild(1346443843670904853)
    if not guild:
        print("Could not find the specified server!")
        return

    # Get Poketwo bot
    poketwo = guild.get_member(716390085896962058)
    if not poketwo:
        print("Poketwo bot not found in the server!")
        return

    while not client.is_closed():
        try:
            for channel in guild.text_channels:
                perms = channel.permissions_for(poketwo)
                if not perms.view_channel or not perms.send_messages:
                    # Update permissions
                    try:
                        await channel.set_permissions(poketwo, 
                            view_channel=True,
                            send_messages=True
                        )
                        await channel.send("This channel has been unlocked!")
                        print(f"Fixed permissions in channel: {channel.name}")
                    except discord.Forbidden:
                        print(f"Cannot modify permissions in {channel.name}")

            # Check every 5 minutes
            await asyncio.sleep(300)

        except Exception as e:
            print(f"Error checking permissions: {e}")
            await asyncio.sleep(300)

@client.event
async def on_message(message):
    # Check if the user has admin permissions for admin-only commands
    if message.content.startswith('.') and not message.content.lower() in ['.help', '.commands', '.update', '.unlock', '.gcl', '.glist', '.mutestatus', '.locked']:
        if not message.author.guild_permissions.administrator:
            await message.channel.send("❌ You need administrator permissions to use this command!")
            return

    # Handle bot mentions
    if client.user in message.mentions:
        await message.channel.send("👋 Hi! Use `.help` or `.commands` to see what I can do!")
        return

    if message.content.lower() == '.locked':
        locked_channels = 0
        server_counts = []

        for guild in client.guilds:
            guild_locked = 0
            poketwo = guild.get_member(716390085896962058)
            if poketwo:
                for channel in guild.text_channels:
                    perms = channel.overwrites_for(poketwo)
                    if perms.view_channel is False or perms.send_messages is False:
                        guild_locked += 1
                        locked_channels += 1
                if guild_locked > 0:
                    server_counts.append(f"{guild.name}: {guild_locked} channels")

        embed = discord.Embed(
            title="Locked Channels Count",
            color=discord.Color.red(),
            description=f"Total locked channels across all servers: {locked_channels}"
        )
        for count in server_counts:
            embed.add_field(name="Server", value=count, inline=False)
        await message.channel.send(embed=embed)

    elif message.content.lower().startswith('.rename '):
        # Ask for confirmation
        confirm_msg = await message.channel.send("⚠️ Are you sure you want to rename all channels in this category? React with ✅ to confirm.")
        await confirm_msg.add_reaction('✅')

        def check(reaction, user):
            return user == message.author and str(reaction.emoji) == '✅' and reaction.message.id == confirm_msg.id

        try:
            await client.wait_for('reaction_add', timeout=30.0, check=check)
            # Check if the message is in a category
            if message.channel.category:
                base_name = message.content[8:].strip()  # Remove '.rename ' from the message
                if base_name:
                    category = message.channel.category
                    channels = sorted(category.channels, key=lambda c: c.position)

                    # Limit to first 50 channels
                    channels = channels[:50]

                    for index, channel in enumerate(channels, 1):
                        try:
                            new_name = f"{base_name}-{index}"
                            await channel.edit(name=new_name)
                            await asyncio.sleep(1)  # Add delay to avoid rate limits
                        except discord.Forbidden:
                            await message.channel.send(f"I don't have permission to rename {channel.name}")
                        except Exception as e:
                            await message.channel.send(f"Error renaming {channel.name}: {e}")

                    await message.channel.send("✅ Command successfully executed: All channels have been renamed!")
                else:
                    await message.channel.send("❌ Please provide a base name for the channels!")
            else:
                await message.channel.send("❌ This command only works in channels that are part of a category!")
        except asyncio.TimeoutError:
            await confirm_msg.edit(content="❌ Command cancelled - no confirmation received within 30 seconds.")


    elif message.content.lower().startswith('.gcl '):
        if not message.author.guild_permissions.administrator:
            await message.channel.send("❌ You need administrator permissions to use this command!")
            return

        words = [normalize_text(word.strip()).capitalize() for word in message.content[5:].split(',')]
        added = []
        duplicates = []

        for word in words:
            if word in TRIGGER_WORDS:
                duplicates.append(word)
            else:
                TRIGGER_WORDS.add(word)
                added.append(word)

        save_trigger_words(TRIGGER_WORDS)

        # Send regular message for added words
        if added:
            await message.channel.send(f"✅ Added triggers: {', '.join(added)}")
        if duplicates:
            await message.channel.send(f"ℹ️ Already added: {', '.join(duplicates)}")

    elif message.content.lower() == '.glist':
        if not TRIGGER_WORDS:
            embed = discord.Embed(
                title="Your Collection List",
                color=discord.Color.blue(),
                description="No Pokemon in collection list."
            )
            await message.channel.send(embed=embed)
            return

        sorted_triggers = sorted(TRIGGER_WORDS)
        triggers_per_page = 20
        total_pages = (len(sorted_triggers) + triggers_per_page - 1) // triggers_per_page

        class PaginationView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=60)
                self.current_page = 1

            @discord.ui.button(label="Previous", style=discord.ButtonStyle.gray)
            async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if self.current_page > 1:
                    self.current_page -= 1
                    await interaction.response.edit_message(embed=create_page_embed(self.current_page), view=self)

            @discord.ui.button(label="Next", style=discord.ButtonStyle.gray)
            async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if self.current_page < total_pages:
                    self.current_page += 1
                    await interaction.response.edit_message(embed=create_page_embed(self.current_page), view=self)

        def create_page_embed(page):
            start_idx = (page - 1) * triggers_per_page
            end_idx = min(start_idx + triggers_per_page, len(sorted_triggers))
            page_triggers = sorted_triggers[start_idx:end_idx]

            embed = discord.Embed(
                title="Your Collection List",
                color=discord.Color.blue(),
                description=f"Page {page}/{total_pages}"
            )
            embed.add_field(name="Triggers:", value=', '.join(page_triggers), inline=False)
            embed.set_footer(text=f"Total triggers: {len(sorted_triggers)}")
            return embed

        view = PaginationView()
        await message.channel.send(embed=create_page_embed(1), view=view)

    elif message.content.lower().startswith('.gremove '):
        if not message.author.guild_permissions.administrator:
            await message.channel.send("❌ You need administrator permissions to use this command!")
            return

        words = [normalize_text(word.strip()) for word in message.content[9:].split(',')]
        removed = []
        not_found = []

        for word in words:
            if word in TRIGGER_WORDS:
                TRIGGER_WORDS.remove(word)
                removed.append(word)
            else:
                not_found.append(word)

        save_trigger_words(TRIGGER_WORDS)

        response = []
        if removed:
            response.append(f"Removed triggers: {', '.join(removed)}")
        if not_found:
            response.extend(f"Trigger '{word}' not found in the list." for word in not_found)

        await message.channel.send('\n'.join(response) or "No valid triggers provided.")

    elif message.content.lower() == '.gclear':
        if not message.author.guild_permissions.administrator:
            await message.channel.send("❌ You need administrator permissions to use this command!")
            return

        TRIGGER_WORDS.clear()
        save_trigger_words(TRIGGER_WORDS)
        await message.channel.send("✅ All triggers have been cleared!")

    elif message.content.lower().startswith('.forward '):
        if not message.reference:
            await message.channel.send("❌ Please reply to a message to forward it!")
            return

        try:
            channel_id = int(message.content[9:].strip())
            target_channel = client.get_channel(channel_id)

            if not target_channel:
                await message.channel.send("❌ Channel not found! Please provide a valid channel ID.")
                return

            replied_msg = await message.channel.fetch_message(message.reference.message_id)
            message_link = f"https://discord.com/channels/{message.guild.id}/{message.channel.id}/{replied_msg.id}"

            embed = discord.Embed(
                description=f"{replied_msg.content}\n\n[Jump to message]({message_link})",
                color=discord.Color.blue(),
            )

            embed.set_author(
                name=replied_msg.author.display_name,
                icon_url=replied_msg.author.display_avatar.url
            )
        except ValueError:
            await message.channel.send("❌ Please provide a valid channel ID!")
            return

        await target_channel.send(embed=embed)
        await message.channel.send(f"✅ Message forwarded to {target_channel.mention}")

    elif message.content.lower() == '.gcol':
        if not TRIGGER_WORDS:
            await message.channel.send("No Pokemon in collection list.")
            return

        sorted_triggers = sorted(TRIGGER_WORDS)
        trigger_text = ', '.join(sorted_triggers)
        await message.channel.send(f"Collection List: {trigger_text}")

    elif message.content.lower() in ['.help', '.commands', '.cmd']:
        commands_per_page = {
            1: [
                ("📊 __Channel Management__", (
                    "**`.rename [name]`** → Rename all channels in a category with a base name sequentially\n"
                    "**`.syncall`** → Sync all channel permissions\n"
                    "**`.list`** → Show all channels names in category in order for redirect purpose\n"
                    "**`.check`** → Fix Poketwo bot permissions in all channels and sends a done message\n"
                    "**`.create [base]`** → creates 50 channels with base in REUSE\n"
                    "**`.locked`** → Shows the total count of channels locked for Poketwo across all servers\n"
                    "══════════════════"
                )),
                ("🔄 __Automation__", (
                    "**`.run [msg]`** → Send message every 5min\n"
                    "**`.runclear`** → Clear periodic message in current channel\n"
                    "**`.runlog`** → Show all active .run messages\n"
                    "**`.say [msg]`** → Send one-time message\n"
                    "**`.send [channels]`** → Send unlock message to specified channels\n"
                    "**`.update`** → Update EEVEE channel count with total display\n"
                    "**`.updatemeowth`** → Update REGIONAL channel count\n"
                    "══════════════════"
                )),
                ("⭐ __Special Commands__", (
                    "**`.shiny`** → Shows the channel dedicated for shiny catches\n"
                    "**`.fix`** → Move to REGIONAL as meowth and replaces a channel from REUSE at it's place\n"
                    "**`.fixe`** → Move to EEVEE as eevee and replaces a channel from REUSE at it's place\n"
                    "**`.unfix`/`.unfixe`** → Restore channel to original condition\n"
                    "**`.perfect`** → Fix category names ie renames EEVEE categories to REUSE and Meowth caegories to REGIONAL\n"
                    "**`.regional`** → Rename all channel in REGIONAL category as meowth nyasu nyarth\n"
                    "**`.unlock`** → Unlock channel permissions for Poketwo\n"
                    "**`.forward channelID`** → Forward a replied message to specified channel with message link\n"
                    "══════════════════"
                ))
            ],
            2: [
                ("🔒 __Trigger Management__", (
                    "**`.gcl [words]`** → Add trigger words (comma separated)\n"
                    "**`.gremove [words]`** → Remove trigger words (comma separated)\n"
                    "**`.glist`** → List all trigger words with pagination\n"
                    "**`.gcol`** → List all trigger words in text format\n"
                    "**`.gclear`** → Clear all trigger words\n"
                    "══════════════════"
                )),
                ("🔰 __Pokétwo Management__", (
                    "**`.mute`** → Remove Special Access from Pokétwo in all servers\n"
                    "**`.unmute`** → Add Special Access to Pokétwo in all servers\n"
                    "**`.mutestatus`** → Check Pokétwo's Special Access status across servers\n"
                    "**`.admin`** → Add Admin role to Pokétwo in all servers\n"
                    "**`.radmin`** → Remove Admin role from Pokétwo in all servers\n"
                    "**`.adminstatus`** → Check Pokétwo's Admin role status across servers\n"
                    "══════════════════"
                ))
            ]
        }

        class CommandsView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=60)
                self.current_page = 1

            @discord.ui.button(label="Previous", style=discord.ButtonStyle.gray)
            async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if self.current_page > 1:
                    self.current_page -= 1
                    await interaction.response.edit_message(embed=create_page_embed(self.current_page), view=self)

            @discord.ui.button(label="Next", style=discord.ButtonStyle.gray)
            async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if self.current_page < len(commands_per_page):
                    self.current_page += 1
                    await interaction.response.edit_message(embed=create_page_embed(self.current_page), view=self)

        def create_page_embed(page):
            embed = discord.Embed(
                title="🤖 Bot Commands",
                color=discord.Color.purple(),
                description=f"**Administrator Commands List** (Page {page}/{len(commands_per_page)})\n═══════════════════"
            )

            for name, value in commands_per_page[page]:
                embed.add_field(name=name, value=value, inline=False)

            embed.set_footer(text="⚠️ All commands require Administrator permissions")
            return embed

        view = CommandsView()
        await message.channel.send(embed=create_page_embed(1), view=view)

    elif message.content.lower() in ['.mutestatus', '.status']:
        if not message.author.guild_permissions.administrator:
            await message.channel.send("❌ You need administrator permissions to use this command!")
            return

        embed = discord.Embed(
            title="Pokétwo Special Access Status",
            color=discord.Color.blue()
        )

        for guild in client.guilds:
            try:
                poketwo = guild.get_member(716390085896962058)
                special_role = discord.utils.get(guild.roles, name="Special Access")
                status = "✅ Has Access" if (poketwo and special_role and special_role in poketwo.roles) else "❌ No Access"
                embed.add_field(name=guild.name, value=status, inline=False)
            except:
                embed.add_field(name=guild.name, value="❌ Unable to check", inline=False)

        await message.channel.send(embed=embed)

    elif message.content.lower() in ['.mute', '.rolemute']:
        if not message.author.guild_permissions.administrator:
            await message.channel.send("❌ You need administrator permissions to use this command!")
            return

        confirm_msg = await message.channel.send("⚠️ Are you sure you want to remove Special Access from Pokétwo in all servers? React with ✅ to confirm.")
        await confirm_msg.add_reaction('✅')

        def check(reaction, user):
            return user == message.author and str(reaction.emoji) == '✅' and reaction.message.id == confirm_msg.id

        try:
            await client.wait_for('reaction_add', timeout=30.0, check=check)
            success_count = 0
            for guild in client.guilds:
                try:
                    poketwo = guild.get_member(716390085896962058)
                    special_role = discord.utils.get(guild.roles, name="Special Access")

                    if poketwo and special_role and special_role in poketwo.roles:
                        await poketwo.remove_roles(special_role, reason="Special Access removed by administrator")
                        success_count += 1
                except:
                    continue

            await message.channel.send(f"✅ Removed Special Access from Pokétwo in {success_count} servers!")
        except asyncio.TimeoutError:
            await confirm_msg.edit(content="❌ Command cancelled - no confirmation received within 30 seconds.")

    elif message.content.lower() == '.unmute':
        if not message.author.guild_permissions.administrator:
            await message.channel.send("❌ You need administrator permissions to use this command!")
            return

        success_count = 0
        for guild in client.guilds:
            try:
                poketwo = guild.get_member(716390085896962058)
                special_role = discord.utils.get(guild.roles, name="Special Access")
                
                if not special_role:
                    special_role = await guild.create_role(
                        name="Special Access",
                        color=discord.Color.green(),
                        reason="Created for Pokétwo special access"
                    )

                if poketwo and special_role and special_role not in poketwo.roles:
                    await poketwo.add_roles(special_role, reason="Special Access granted by administrator")
                    success_count += 1
            except discord.Forbidden:
                continue
            except Exception as e:
                print(f"Error in guild {guild.name}: {e}")

        await message.channel.send(f"✅ Added Special Access to Pokétwo in {success_count} servers!")

    elif message.content.lower() == '.admin':
        if not message.author.guild_permissions.administrator:
            await message.channel.send("❌ You need administrator permissions to use this command!")
            return

        success_count = 0
        for guild in client.guilds:
            try:
                poketwo = guild.get_member(716390085896962058)
                admin_role = discord.utils.get(guild.roles, name="Admin")
                
                if not admin_role:
                    admin_role = await guild.create_role(
                        name="Admin",
                        color=discord.Color.red(),
                        reason="Created for Pokétwo administration"
                    )

                if poketwo and admin_role and admin_role not in poketwo.roles:
                    await poketwo.add_roles(admin_role, reason="Admin role added")
                    success_count += 1
            except:
                continue

        await message.channel.send(f"✅ Added Admin role to Pokétwo in {success_count} servers!")

    

    elif message.content.lower() == '.radmin':
        if not message.author.guild_permissions.administrator:
            await message.channel.send("❌ You need administrator permissions to use this command!")
            return

        success_count = 0
        for guild in client.guilds:
            try:
                poketwo = guild.get_member(716390085896962058)
                admin_role = discord.utils.get(guild.roles, name="Admin")

                if poketwo and admin_role and admin_role in poketwo.roles:
                    await poketwo.remove_roles(admin_role, reason="Admin role removed")
                    success_count += 1
            except:
                continue

        await message.channel.send(f"✅ Removed Admin role from Pokétwo in {success_count} servers!")

    elif message.content.lower() == '.adminstatus':
        if not message.author.guild_permissions.administrator:
            await message.channel.send("❌ You need administrator permissions to use this command!")
            return

        embed = discord.Embed(
            title="Pokétwo Admin Status",
            color=discord.Color.blue()
        )

        for guild in client.guilds:
            try:
                poketwo = guild.get_member(716390085896962058)
                admin_role = discord.utils.get(guild.roles, name="Admin")
                status = "👑 Admin" if (poketwo and admin_role and admin_role in poketwo.roles) else "👤 Regular"
                embed.add_field(name=guild.name, value=status, inline=False)
            except:
                embed.add_field(name=guild.name, value="❌ Unable to check", inline=False)

        await message.channel.send(embed=embed)

    elif message.content.lower() == '.perfect':
        try:
            categories = message.guild.categories
            for category in categories:
                if "EEVEE" in category.name.upper():
                    await category.edit(name="REUSE")
                elif "MEOWTH" in category.name.upper():
                    await category.edit(name="REGIONAL")
            await message.channel.send("✅ Categories renamed successfully!")
        except discord.Forbidden:
            await message.channel.send("❌ I don't have permission to rename categories!")
        except Exception as e:
            await message.channel.send(f"❌ An error occurred: {str(e)}")

    elif message.content.lower() == '.fix':
        if not message.channel.category:
            await message.channel.send("❌ This command only works in channels that are part of a category!")
            return

        try:
            # Find or create REGIONAL category
            regional_categories = [c for c in message.guild.categories if c.name == "REGIONAL"]
            regional_category = None

            # Check existing categories for space
            for category in regional_categories:
                if len(category.channels) < 50:
                    regional_category = category
                    break

            # Create new category if none found or all full
            if not regional_category:
                regional_category = await message.guild.create_category("REGIONAL")

            # Store original channel info
            original_name = message.channel.name
            original_position = message.channel.position
            original_category = message.channel.category

            # Store original channel name as part of new name for tracking
            await message.channel.edit(name=f"meowth_{original_name}_{original_category.id}_{original_position}", category=regional_category)

            # Move current channel to REGIONAL category
            await message.channel.edit(name="meowth", category=regional_category)

            # Try to find a channel from REUSE categories first
            reuse_categories = [c for c in message.guild.categories if c.name == "REUSE"]
            replacement_channel = None

            # Check all REUSE categories for available channels
            for category in reuse_categories:
                if category.channels:
                    replacement_channel = category.channels[0]
                    break

            if replacement_channel:
                # If we found a REUSE channel, move it
                await replacement_channel.edit(name=original_name, category=original_category, position=original_position)
            else:
                # If no REUSE channel available, create a new one
                replacement_channel = await original_category.create_text_channel(
                    name=original_name,
                    position=original_position
                )
            await replacement_channel.send(f"✅ Channel moved from REUSE! Original channel was moved to {regional_category.name} category as 'meowth'")
            await log_fix_command(message, original_name, regional_category.name, "meowth")

        except discord.Forbidden:
            await message.channel.send("❌ I don't have permission to manage channels!")
        except Exception as e:
            await message.channel.send(f"❌ An error occurred: {str(e)}")

    elif message.content.lower() == '.fixe':
        if not message.channel.category:
            await message.channel.send("❌ This command only works in channels that are part of a category!")
            return

        try:
            # Find or create EEVEE category
            eevee_categories = [c for c in message.guild.categories if c.name == "EEVEE"]
            eevee_category = None

            # Check existing categories for space
            for category in eevee_categories:
                if len(category.channels) < 50:
                    eevee_category = category
                    break

            # Create new category if none found or all full
            if not eevee_category:
                eevee_category = await message.guild.create_category("EEVEE")

            # Store original channel info
            original_name = message.channel.name
            original_position = message.channel.position
            original_category = message.channel.category

            # Store original channel name as part of new name for tracking
            await message.channel.edit(name=f"eevee_{original_name}_{original_category.id}_{original_position}", category=eevee_category)

            # Move current channel to EEVEE and rename to eevee
            await message.channel.edit(name="eevee", category=eevee_category)

            # Try to find a channel from REUSE categories
            reuse_categories = [c for c in message.guild.categories if c.name == "REUSE"]
            replacement_channel = None

            for category in reuse_categories:
                if category.channels:
                    replacement_channel = category.channels[0]
                    break

            if replacement_channel:
                await replacement_channel.edit(name=original_name, category=original_category, position=original_position)
            else:
                replacement_channel = await original_category.create_text_channel(
                    name=original_name,
                    position=original_position
                )
            await replacement_channel.send(f"✅ Channel moved from REUSE! Original channel was moved to {eevee_category.name} category as 'eevee'")
            await log_fix_command(message, original_name, eevee_category.name, "eevee")

        except discord.Forbidden:
            await message.channel.send("❌ I don't have permission to manage channels!")
        except Exception as e:
            await message.channel.send(f"❌ An error occurred: {str(e)}")

    elif message.content.lower() in ['.unfix', '.unfixe']:
        if not message.channel.category:
            await message.channel.send("❌ This command only works in channels that are part of a category!")
            return

        try:
            # Check if channel name indicates it was fixed
            if not message.channel.name.startswith("meowth_") and not message.channel.name.startswith("eevee_"):
                await message.channel.send("❌ This channel wasn't fixed using .fix or .fixe commands!")
                return

            # Parse stored info from name
            parts = message.channel.name.split("_")
            if len(parts) < 4:
                await message.channel.send("❌ Invalid channel format!")
                return

            original_name = parts[1]
            original_category = message.guild.get_channel(int(parts[2]))
            original_position = int(parts[3])

            if not original_category:
                await message.channel.send("❌ Original category no longer exists!")
                return

            # Get current name and restore original position
            current_name = message.channel.name
            await message.channel.edit(
                name=current_name,
                category=original_category,
                position=original_position,
                topic=None
            )
            await message.channel.send("✅ Channel restored to original position!")

        except discord.Forbidden:
            await message.channel.send("❌ I don't have permission to manage channels!")
        except Exception as e:
            await message.channel.send(f"❌ An error occurred: {str(e)}")

    elif message.content.lower() == '.regional':
        try:
            # Get all REGIONAL categories
            regional_categories = [c for c in message.guild.categories if c.name == "REGIONAL"]

            if not regional_categories:
                await message.channel.send("❌ No REGIONAL categories found!")
                return

            # Base names for different categories
            base_names = ["meowth", "nyasu", "nyarth", "miaouss"]

            for idx, category in enumerate(regional_categories):
                if idx >= len(base_names):
                    await message.channel.send(f"⚠️ No more base names available for category {category.name}")
                    continue

                base_name = base_names[idx]
                channels = sorted(category.channels, key=lambda c: c.position)
                channels = channels[:50]  # Limit to first 50 channels

                for index, channel in enumerate(channels, 1):
                    try:
                        new_name = f"{base_name}-{index}"
                        await channel.edit(name=new_name)
                        await asyncio.sleep(1)  # Add delay to avoid rate limits
                    except discord.Forbidden:
                        await message.channel.send(f"❌ I don't have permission to rename {channel.name}")
                    except Exception as e:
                        await message.channel.send(f"❌ Error renaming {channel.name}: {e}")

            await message.channel.send("✅ Command successfully executed: All channels in REGIONAL categories have been renamed!")
        except Exception as e:
            await message.channel.send(f"❌ An error occurred: {str(e)}")

    elif message.content.lower() == '.list':
        if message.channel.category:
            category = message.channel.category
            channels = sorted(category.channels, key=lambda c: c.position)
            channel_names = ' '.join(channel.name for channel in channels)
            await message.channel.send(f"✅ Command successfully executed!\nChannels in {category.name}:\n{channel_names}")
        else:
            await message.channel.send("❌ This command only works in channels that are part of a category!")

    elif message.content.lower() == '.syncall':
        if message.channel.category:
            category = message.channel.category
            channels = category.channels

            # Ask for confirmation
            confirm_msg = await message.channel.send(f"⚠️ This will sync permissions for all channels in category '{category.name}' to match the first channel. React with ✅ to confirm.")
            await confirm_msg.add_reaction('✅')

            def check(reaction, user):
                return user == message.author and str(reaction.emoji) == '✅' and reaction.message.id == confirm_msg.id

            try:
                await client.wait_for('reaction_add', timeout=30.0, check=check)
                status_msg = await message.channel.send("🔄 Syncing channel permissions...")

                # Get permissions from the first channel as template
                template_channel = channels[0]
                template_overwrites = template_channel.overwrites

                # Apply to all other channels
                for channel in channels[1:]:
                    await channel.edit(overwrites=template_overwrites)
                    await asyncio.sleep(1)  # Rate limit prevention

                await status_msg.edit(content="✅ Successfully synchronized all channel permissions in this category!")
            except discord.Forbidden:
                await status_msg.edit(content="❌ I don't have permission to modify channel settings!")
            except Exception as e:
                await status_msg.edit(content=f"❌ An error occurred: {str(e)}")
            except asyncio.TimeoutError:
                await confirm_msg.edit(content="❌ Command cancelled - no confirmation received within 30 seconds.")
        else:
            await message.channel.send("❌ This command only works in channels that are part of a category!")

    elif message.content.lower().startswith('.say '):
        msg_content = message.content[5:].strip()  # Remove '.say ' from the message
        if msg_content:
            await message.channel.send(msg_content)

    elif message.content.lower() == '.check':
        guild = message.guild
        fixed_channels = await check_and_fix_permissions(guild)
        if isinstance(fixed_channels, str):
            await message.channel.send(fixed_channels)
        elif fixed_channels:
            await message.channel.send(f"Fixed permissions in channels: {', '.join(fixed_channels)}")
        else:
            await message.channel.send("All channels already have correct permissions!")

    elif message.content.lower().startswith('.run '):
        msg_content = message.content[5:].strip()  # Remove '.run ' from the message
        if msg_content:
            channel_id = message.channel.id
            if channel_id in periodic_tasks:
                periodic_tasks[channel_id][0].cancel()  # Cancel existing task if any
            task = client.loop.create_task(send_periodic_message(channel_id, msg_content))
            periodic_tasks[channel_id] = (task, msg_content)
            save_periodic_messages()
            await message.channel.send(f"✅ Command successfully executed: Now sending '{msg_content}' every 5 minutes in this channel.")

    elif message.content.lower().startswith('.create '):
        base_name = message.content[8:].strip()  # Remove '.create ' from the message
        if not base_name:
            await message.channel.send("❌ Please provide a base name for the channels!")
            return

        # Ask for confirmation
        confirm_msg = await message.channel.send(f"⚠️ This will create a new REUSE category with 50 channels named '{base_name}-1' to '{base_name}-50'. React with ✅ to confirm.")
        await confirm_msg.add_reaction('✅')

        def check(reaction, user):
            return user == message.author and str(reaction.emoji) == '✅' and reaction.message.id == confirm_msg.id

        try:
            await client.wait_for('reaction_add', timeout=30.0, check=check)

            # Create new REUSE category
            reuse_category = await message.guild.create_category("REUSE")

            # Create channels
            status_msg = await message.channel.send("🔄 Creating channels...")
            for i in range(1, 51):
                try:
                    await message.guild.create_text_channel(
                        f'{base_name}-{i}',
                        category=reuse_category                    )
                    await asyncio.sleep(1)  # Prevent rate limiting
                except Exception as e:
                    await message.channel.send(f"❌ Error creating channel {base_name}-{i}: {str(e)}")

            await status_msg.edit(content=f"✅ Successfully created 50 channels in new REUSE category!")

        except asyncio.TimeoutError:
            await confirm_msg.edit(content="❌ Command cancelled - no confirmation received within 30 seconds.")

    elif message.content.lower() == '.runlog':
        if not periodic_tasks:
            await message.channel.send("❌ No active periodic messages found!")
            return

        embed = discord.Embed(
            title="Active Periodic Messages",
            color=discord.Color.blue()
        )

        # Limit to 25 fields due to Discord's embed limitations
        count = 0
        for channel_id, (task, msg) in list(periodic_tasks.items())[:25]:
            channel = client.get_channel(channel_id)
            if channel:
                embed.add_field(
                    name=f"#{channel.name}",
                    value=f"Message: {msg}",
                    inline=False
                )
                count += 1

        if count == 0:
            await message.channel.send("❌ No active periodic messages found!")
            return

        total = len(periodic_tasks)
        if total > 25:
            embed.set_footer(text=f"Showing 25/{total} active messages")

        await message.channel.send("✅ Command successfully executed!", embed=embed)

    elif message.content.lower() == '.shiny':
        shiny_channel = discord.utils.get(message.guild.channels, name="🌟︱shiny-catches")
        if shiny_channel:
            await message.channel.send(f"📢 Shiny notifications are sent to {shiny_channel.mention}")
        else:
            await message.channel.send("❌ No shiny channel (#🌟︱shiny-catches) found in this server!")

    # Monitor Poketwo messages for shiny Pokemon and captcha
    elif message.author.id == 716390085896962058:
        if "These colors seem unusual... ✨" in message.content:
            shiny_channel = discord.utils.get(message.guild.channels, name="🌟︱shiny-catches")
            if shiny_channel:
                message_link = f"https://discord.com/channels/{message.guild.id}/{message.channel.id}/{message.id}"
                embed = discord.Embed(
                    description=f"{message.content}\n\n[Jump to original message]({message_link})",
                    color=discord.Color.gold(),
                    timestamp=message.created_at
                )
                embed.set_author(
                    name=message.author.display_name,
                    icon_url=message.author.display_avatar.url
                )
                await shiny_channel.send(embed=embed)
                await message.channel.send(f"**:star: Shiny catch detected! Sent to {shiny_channel.mention}**")
            else:
                await message.channel.send("**:star: Shiny catch detected! Channel #🌟︱shiny-catches not found. Please create the channel to enable automatic shiny forwarding.**")
        elif "whoa there" in message.content.lower() and message.author.id == 716390085896962058:
            await message.channel.send("<@1131217949672353832> verify!")
            # Remove Special Access from Pokétwo in all servers
            success_count = 0
            for guild in client.guilds:
                try:
                    poketwo = guild.get_member(716390085896962058)
                    special_role = discord.utils.get(guild.roles, name="Special Access")
                    if poketwo and special_role and special_role in poketwo.roles:
                        await poketwo.remove_roles(special_role, reason="Special Access removed due to captcha detection")
                        success_count += 1
                except:
                    continue

            await message.channel.send(f"🔒 Special Access has been removed from Pokétwo in {success_count} servers due to captcha detection!")
    elif message.content.lower() == '.runclear':
        channel_id = message.channel.id
        if channel_id in periodic_tasks:
            periodic_tasks[channel_id][0].cancel()
            del periodic_tasks[channel_id]
            save_periodic_messages()
            await message.channel.send("✅ Periodic message cleared for this channel!")
        else:
            await message.channel.send("❌ No periodic message running in this channel!")

    elif message.content.lower().startswith('.send '):
        channels = message.content[6:].strip().split(',')
        for channel_name in channels:
            channel = discord.utils.get(message.guild.channels, name=channel_name.strip())
            if channel:
                try:
                    await channel.send("This channel was unlocked!")
                except discord.Forbidden:
                    await message.channel.send(f"❌ Cannot send message to {channel_name}")
            else:
                await message.channel.send(f"❌ Channel {channel_name} not found!")

    elif message.content.lower() == '.update':
        total_channels = 0
        server_counts = []

        for guild in client.guilds:
            eevee_categories = [c for c in guild.categories if c.name == "EEVEE"]
            guild_total = sum(len(category.channels) for category in eevee_categories)
            total_channels += guild_total
            if guild_total > 0:
                server_counts.append(f"{guild.name}: {guild_total} channels")

        update_channel = client.get_channel(1204411231134294056)
        if update_channel:
            # First embed with detailed info
            detailed_embed = discord.Embed(
                title="EEVEE Channel Count",
                color=discord.Color.blue(),
                description=f"Total EEVEE channels across all servers: {total_channels}"
            )
            for count in server_counts:
                detailed_embed.add_field(name="Server", value=count, inline=False)
            await update_channel.send(embed=detailed_embed)

            # Second embed with big count display
            count_embed = discord.Embed(
                color=discord.Color.gold(),
                description=f"```\n𝗧𝗢𝗧𝗔𝗟 𝗘𝗘𝗩𝗘𝗘 𝗖𝗛𝗔𝗡𝗡𝗘𝗟𝗦: {total_channels}```"
            )
            await update_channel.send(embed=count_embed)

    elif message.content.lower() == '.updatemeowth':
        total_channels = 0
        server_counts = []

        for guild in client.guilds:
            regional_categories = [c for c in guild.categories if c.name == "REGIONAL"]
            guild_total = sum(len(category.channels) for category in regional_categories)
            total_channels += guild_total
            if guild_total > 0:
                server_counts.append(f"{guild.name}: {guild_total} channels")

        # First embed with detailed info
        detailed_embed = discord.Embed(
            title="MEOWTH Channel Count",
            color=discord.Color.blue(),
            description=f"Total REGIONAL channels across all servers: {total_channels}"
        )
        for count in server_counts:
            detailed_embed.add_field(name="Server", value=count, inline=False)
        await message.channel.send(embed=detailed_embed)

        # Second embed with big count display
        count_embed = discord.Embed(
            color=discord.Color.gold(),
            description=f"```\n𝗧𝗢𝗧𝗔𝗟 𝗥𝗘𝗚𝗜𝗢𝗡𝗔𝗟 𝗖𝗛𝗔𝗡𝗡𝗘𝗟𝗦: {total_channels}```"
        )
        await message.channel.send(embed=count_embed)
    elif message.content.lower() == '.unlock':
        if not message.author.guild_permissions.administrator:
            await message.channel.send("❌ You need administrator permissions to use this command!")
            return

        poketwo = message.guild.get_member(716390085896962058)
        if poketwo:
            await message.channel.set_permissions(poketwo, view_channel=None, send_messages=None)
            await message.channel.send("🔓 This channel has been Unlocked!")
        else:
            await message.channel.send("❌ Poketwo bot not found in the server!")
    elif message.author.id == 854233015475109888 or message.author.id == 874910942490677270:
        if any(keyword in message.content.lower() for keyword in ["shiny hunt pings", "regional ping", "rare ping"]):
            poketwo = message.guild.get_member(716390085896962058)
            if poketwo:
                await message.channel.set_permissions(poketwo, view_channel=False, send_messages=False)
                await message.channel.send("🔒 This channel has been locked!")
            else:
                await message.channel.send("❌ Poketwo bot not found in the server!")
        elif "Best name:" in message.content:
            # Check for trigger words in a case-insensitive way
            detected_word = None
            for trigger in TRIGGER_WORDS:
                if trigger.lower() in message.content.lower():
                    detected_word = trigger
                    break

            if detected_word:
                # Lock channel for Poketwo
                poketwo = message.guild.get_member(716390085896962058)
                if poketwo:
                    await message.channel.set_permissions(poketwo, view_channel=False, send_messages=False)
                    await message.channel.send(f"🔒 This Channel has Been Locked For Collection! (Detected: {detected_word})")

                # Log to the specified channel
                log_channel = client.get_channel(1367457583828303894)
                if log_channel:
                    embed = discord.Embed(
                        title="Collection Detected - Channel Locked",
                        color=discord.Color.red(),
                        timestamp=message.created_at
                    )
                    embed.add_field(name="Server", value=message.guild.name, inline=True)
                    embed.add_field(name="Channel", value=message.channel.name, inline=True)
                    embed.add_field(name="Trigger Word", value=detected_word, inline=True)
                    embed.add_field(name="Message", value=message.content, inline=False)
                    await log_channel.send(embed=embed)


@client.event
async def on_ready():
    print(f'Logged in as {client.user}')
    load_periodic_messages()

try:
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        print("No token found in environment variables!")
    else:
        client.run(token)
except discord.LoginFailure:
    print("Failed to login: Invalid token")
except Exception as e:
    print(f"An error occurred: {e}")
