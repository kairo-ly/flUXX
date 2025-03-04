import discord
from discord.ext import commands
import yt_dlp
from discord.ui import Button, View
import asyncio
import json
from datetime import datetime
from datetime import timedelta
from datetime import datetime, timedelta
from discord.ext import tasks
import os
from discord import Embed, Color
import random
import psutil  # For system stats
import time
import pytz
import requests
import zoneinfo
from flask import Flask
import threading
from discord import app_commands
from dotenv import load_dotenv
import discord
import nacl
 

# Create a Flask web server
app = Flask(__name__)


@app.route('/')
def home():
    return "Bot is online!"


# Function to run Flask in a separate thread
def run_web():
    app.run(host="0.0.0.0", port=3000)


# Start the Flask web server
threading.Thread(target=run_web).start()

# Initialize bot
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="?", intents=intents)

# Embed color preference
EMBED_COLOR = 0x02a390

# Track voice clients and queues
voice_clients = {}
queues = {}


@bot.command()
async def join(ctx):
    """Bot joins the user's voice channel and auto-defens itself."""

    if not ctx.author.voice:

        return await ctx.send("❌ You need to be in a voice channel!")

    channel = ctx.author.voice.channel

    voice_client = await channel.connect(self_deaf=True)  # Auto-deafen bot

    voice_clients[ctx.guild.id] = voice_client

    queues[ctx.guild.id] = []  # Initialize queue for the server

    await ctx.send(f"🔊 Joined `{channel.name}` and deafened myself.")


@bot.command()
async def play(ctx, *, query: str = None):
    """Play a song or add it to the queue."""
    if not ctx.author.voice:
        return await ctx.send("❌ You need to be in a voice channel!")

    if ctx.guild.id not in voice_clients:
        return await ctx.send(
            "❌ I'm not connected to a voice channel! Use `!join` first.")

    if not query:
        return await ctx.send("❌ Please provide a song name or URL!")

    # Send Searching Message
    searching_embed = discord.Embed(title="🔍 Searching...",
                                    description=f"Looking for `{query}`...",
                                    color=EMBED_COLOR)
    searching_message = await ctx.send(embed=searching_embed)

    # Search & extract URL
    ydl_opts = {
        "format": "bestaudio",
        "quiet": True,  # Suppresses logs
        "no_warnings": True,  # Hides warnings
        "logger": None,  # Disables logging output
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(f"ytsearch:{query}", download=False)
        if not info["entries"]:
            await searching_message.delete()
            return await ctx.send("❌ No results found!")

        song = info["entries"][0]
        url = song["url"]
        title = song["title"]
        duration = int(song["duration"])  # Convert to integer
        thumbnail = song.get("thumbnail", None)  # Get thumbnail if available

    # Convert duration from seconds to MM:SS format
    minutes, seconds = divmod(duration, 60)
    duration_str = f"{minutes}:{seconds:02d}"

    # Delete searching message
    await searching_message.delete()

    # If queue is empty and bot is idle, play immediately
    if not voice_clients[ctx.guild.id].is_playing() and not queues.get(
            ctx.guild.id):
        queues[ctx.guild.id] = [(title, url, ctx.author, duration_str,
                                 thumbnail)]
        await play_next(ctx)
    else:
        queues.setdefault(ctx.guild.id, []).append(
            (title, url, ctx.author, duration_str, thumbnail))

        # Create "Added to Queue" Embed
        embed = discord.Embed(title="🎵 Added to Queue",
                              description=f"[{title}]({url})",
                              color=EMBED_COLOR)
        embed.add_field(name="Duration ⏳", value=duration_str, inline=True)
        embed.add_field(name="Requested By 👤",
                        value=ctx.author.mention,
                        inline=True)
        if thumbnail:
            embed.set_thumbnail(url=thumbnail)

        embed.set_footer(text="Made By Vihan • " + discord.utils.format_dt(
            datetime.utcnow(), "R"))  # Timestamp + Watermark
        await ctx.send(embed=embed)


async def play_next(ctx):
    """Plays the next song in the queue."""
    if queues[ctx.guild.id]:  # Check if queue is not empty
        title, url, requester, duration_str, thumbnail = queues[
            ctx.guild.id].pop(0)  # Get the next song
        voice_client = voice_clients[ctx.guild.id]
        voice_client.stop()  # Stop current song if playing

        # FFmpeg options for smooth playback
        ffmpeg_options = {"options": "-vn"}

        # Play the audio with error handling
        try:
            source = await discord.FFmpegOpusAudio.from_probe(
                url, **ffmpeg_options)
            voice_client.play(source,
                              after=lambda e: asyncio.run_coroutine_threadsafe(
                                  play_next(ctx), bot.loop))
        except Exception as e:
            await ctx.send(f"❌ Error playing {title}: {str(e)}")
            await play_next(ctx)  # Skip to next song if there's an error

        # Send "Now Playing" Embed with Buttons
        embed = discord.Embed(title="🎵 Now Playing",
                              description=f"[{title}]({url})",
                              color=EMBED_COLOR)
        embed.add_field(name="Duration ⏳", value=duration_str, inline=True)
        embed.add_field(name="Requested By 👤",
                        value=requester.mention,
                        inline=True)
        if thumbnail:
            embed.set_thumbnail(url=thumbnail)

        embed.set_footer(text="Made By Vihan • ")
        view = MusicControls(ctx.guild.id, ctx)
        await ctx.send(embed=embed, view=view)


@bot.command()
async def queue(ctx):
    """Shows the current queue."""
    if ctx.guild.id not in queues or not queues[ctx.guild.id]:
        return await ctx.send("❌ The queue is empty!")

    queue_list = "\n".join([
        f"**{i+1}.** {song[0]}" for i, song in enumerate(queues[ctx.guild.id])
    ])
    embed = discord.Embed(title="🎶 Music Queue",
                          description=queue_list,
                          color=EMBED_COLOR)
    await ctx.send(embed=embed)


@bot.command()
async def leave(ctx):
    """Bot leaves the voice channel."""
    if ctx.guild.id in voice_clients:
        await voice_clients[ctx.guild.id].disconnect()
        del voice_clients[ctx.guild.id]
        await ctx.send("👋 Disconnected from voice channel.")
    else:
        await ctx.send("❌ I'm not in a voice channel!")


# Music Controls with Buttons
# Music Controls with Buttons
class MusicControls(View):

    def __init__(self, guild_id, ctx):
        super().__init__()
        self.guild_id = guild_id
        self.ctx = ctx

    @discord.ui.button(label="⏸ Pause", style=discord.ButtonStyle.primary)
    async def pause(self, interaction: discord.Interaction, button: Button):
        if self.guild_id in voice_clients and voice_clients[
                self.guild_id].is_playing():
            voice_clients[self.guild_id].pause()
            await interaction.response.send_message("⏸ Music Paused!",
                                                    ephemeral=True)
        else:
            await interaction.response.send_message("❌ No music is playing!",
                                                    ephemeral=True)

    @discord.ui.button(label="▶ Resume", style=discord.ButtonStyle.success)
    async def resume(self, interaction: discord.Interaction, button: Button):
        if self.guild_id in voice_clients and voice_clients[
                self.guild_id].is_paused():
            voice_clients[self.guild_id].resume()
            await interaction.response.send_message("▶ Music Resumed!",
                                                    ephemeral=True)
        else:
            await interaction.response.send_message("❌ No music is paused!",
                                                    ephemeral=True)

    @discord.ui.button(label="⏭ Skip", style=discord.ButtonStyle.secondary)
    async def skip(self, interaction: discord.Interaction, button: Button):
        if self.guild_id in voice_clients and voice_clients[
                self.guild_id].is_playing():
            voice_clients[self.guild_id].stop()
            await interaction.response.send_message(
                "⏭ Skipped to the next song!", ephemeral=True)
        else:
            await interaction.response.send_message("❌ No music is playing!",
                                                    ephemeral=True)

    @discord.ui.button(label="⏹ Stop", style=discord.ButtonStyle.danger)
    async def stop(self, interaction: discord.Interaction, button: Button):
        if self.guild_id in voice_clients:
            voice_clients[self.guild_id].stop()
            queues[self.guild_id] = []  # Clear queue
            await interaction.response.send_message(
                "⏹ Music Stopped and Queue Cleared!", ephemeral=True)
        else:
            await interaction.response.send_message("❌ No music is playing!",
                                                    ephemeral=True)

    @discord.ui.button(label="📜 Queue", style=discord.ButtonStyle.blurple)
    async def show_queue(self, interaction: discord.Interaction,
                         button: Button):
        """Displays the current queue when clicked."""
        if self.guild_id not in queues or not queues[self.guild_id]:
            return await interaction.response.send_message(
                "❌ The queue is empty!", ephemeral=True)

        queue_list = "\n".join([
            f"**{i+1}.** {song[0]}"
            for i, song in enumerate(queues[self.guild_id])
        ])
        embed = discord.Embed(title="🎶 Music Queue",
                              description=queue_list,
                              color=EMBED_COLOR)
        await interaction.response.send_message(embed=embed, ephemeral=True)


# music buttons emergency cmds


@bot.command(name="stop")
async def stop(ctx):
    """Stop the music player."""
    voice_client = ctx.message.guild.voice_client
    if voice_client.is_playing():
        await voice_client.stop()
        embed = discord.Embed(title="Music Stopped",
                              description="The music player has been stopped.",
                              color=0x02a390)
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(title="No Music Playing",
                              description="There is no music playing to stop.",
                              color=0x02a390)
        await ctx.send(embed=embed)


@bot.command(name="resume")
async def resume(ctx):
    """Resume the music player."""
    voice_client = ctx.message.guild.voice_client
    if voice_client.is_paused():
        await voice_client.resume()
        embed = discord.Embed(title="Music Resumed",
                              description="The music player has been resumed.",
                              color=0x02a390)
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(title="Music Not Paused",
                              description="The music player is not paused.",
                              color=0x02a390)
        await ctx.send(embed=embed)


@bot.command(name="skip")
async def skip(ctx):
    """Skip the current song."""
    voice_client = ctx.message.guild.voice_client
    if voice_client.is_playing():
        await voice_client.stop()
        embed = discord.Embed(title="Song Skipped",
                              description="The current song has been skipped.",
                              color=0x02a390)
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(title="No Song Playing",
                              description="There is no song playing to skip.",
                              color=0x02a390)
        await ctx.send(embed=embed)


@bot.command(name="pause")
async def pause(ctx):
    """Pause the music player."""
    voice_client = ctx.message.guild.voice_client
    if voice_client.is_playing():
        await voice_client.pause()
        embed = discord.Embed(title="Music Paused",
                              description="The music player has been paused.",
                              color=0x02a390)
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(
            title="Music Not Playing",
            description="There is no music playing to pause.",
            color=0x02a390)
        await ctx.send(embed=embed)


#moderation

#error handler


@bot.event
async def on_command_error(ctx, error):
    embed = discord.Embed(title="⚠ Error", color=0x02a390)

    if isinstance(error, commands.MissingPermissions):
        embed.description = "You don't have the required permissions to use this command."
    elif isinstance(error, commands.MissingRequiredArgument):
        embed.description = "You're missing a required argument. Please check the command's usage."
    elif isinstance(error, commands.CommandNotFound):
        embed.description = "Command not found. Please check the command's name and try again."
    elif isinstance(error, commands.CommandInvokeError):
        embed.description = "An error occurred while invoking the command. Please try again later."
    else:
        embed.description = str(error)

    error_message = await ctx.send(embed=embed)
    await asyncio.sleep(3)
    await error_message.delete()


# purge messgaes


@bot.command(name="purge")
@commands.has_permissions(manage_messages=True)
async def purge(ctx, amount: int):
    await ctx.channel.purge(limit=amount + 1)

    embed = discord.Embed(title=" ✅ Purge Successful",
                          description=f"Purged {amount} messages!",
                          color=0x02a390)

    await ctx.send(embed=embed, delete_after=3)


@bot.command(name="pb")
@commands.has_permissions(manage_messages=True)
async def purgebot(ctx):

    def is_bot(message):
        return message.author.bot

    await ctx.channel.purge(check=is_bot)
    embed = discord.Embed(title=" ✅ Purge Successful",
                          description="Purged all bot messages!",
                          color=0x02a390)

    await ctx.send(embed=embed, delete_after=3)


@bot.command(name="purgeembeds")
@commands.has_permissions(manage_messages=True)
async def purgeembeds(ctx, amount: int):

    def has_embed(message):
        return len(message.embeds) > 0

    await ctx.channel.purge(limit=amount + 1, check=has_embed)

    embed = discord.Embed(title=" ✅ Purge Successful",
                          description=f"Purged {amount} messages with embeds!",
                          color=0x02a390)

    await ctx.send(embed=embed, delete_after=3)


# kick command


@bot.command(name="kick")
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason=None):
    await member.kick(reason=reason)

    embed = discord.Embed(
        title=" Member Kicked",
        description=f"{member.mention} has been kicked from the server.",
        color=0x02a390)
    embed.set_thumbnail(url=member.avatar.url)
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.add_field(name="Action By", value=ctx.author.mention, inline=False)
    embed.set_footer(text="Made by Vihan")
    await ctx.send(embed=embed)


@bot.command(name="ban")
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason="No reason provided"):
    await member.ban(reason=reason)

    embed = discord.Embed(title="🔨 Member Banned", color=EMBED_COLOR)
    embed.set_thumbnail(url=member.avatar.url)
    embed.add_field(name="👤 User", value=member.mention, inline=True)
    embed.add_field(name="📜 Reason", value=reason, inline=True)
    embed.set_footer(text="To unban, use ?unban <user_id> | Made by Vihan")

    await ctx.send(embed=embed)


@bot.command(name="unban")
@commands.has_permissions(ban_members=True)
async def unban(ctx, *, member_id: int):  # Convert input to integer directly
    try:
        # ✅ Check if user is banned before unbanning
        ban_entry = await ctx.guild.fetch_ban(discord.Object(member_id))
        user = ban_entry.user  # Get the banned user object

        await ctx.guild.unban(user)  # Unban the user

        embed = discord.Embed(title="✅ Member Unbanned", color=EMBED_COLOR)
        embed.set_thumbnail(url=user.display_avatar.url)  # Correct avatar URL
        embed.add_field(name="👤 Unbanned User",
                        value=f"{user.name}#{user.discriminator} ({user.id})",
                        inline=True)
        embed.add_field(name="🚫 Action By",
                        value=ctx.author.mention,
                        inline=True)
        embed.set_footer(text="Made by Vihan")

        await ctx.send(embed=embed)

    except discord.NotFound:
        await ctx.send("❌ This user is **not in the ban list**.")
    except discord.Forbidden:
        await ctx.send("❌ I **don't have permission** to unban this user.")
    except Exception as e:
        await ctx.send(f"❌ An error occurred: `{e}`")


# Member info command


@bot.command(name="mi")
async def memberinfo(ctx, member: discord.Member = None):
    if member is None:
        member = ctx.author

    embed = discord.Embed(
        title=f"{member.name}'s Info",
        description=f"Here's some information about {member.name}",
        color=0x02a390)

    embed.add_field(name="Username", value=member.name, inline=False)

    embed.add_field(name="Discriminator",
                    value=member.discriminator,
                    inline=False)

    embed.add_field(name="ID", value=member.id, inline=False)

    embed.add_field(name="Status", value=member.status, inline=False)

    embed.add_field(name="Joined Server", value=member.joined_at, inline=False)

    embed.add_field(name="Account Created",
                    value=member.created_at,
                    inline=False)

    embed.set_thumbnail(url=member.avatar.url)

    await ctx.send(embed=embed)


# Help command
bot.remove_command("help")

DEFAULT_PREFIX = "?"

# Category commands dictionary
COMMAND_CATEGORIES = {
    "Music": [
        "?play <song> - Play a song", "?pause - Pause the current song",
        "?resume - Resume the paused song",
        "?stop - Stop the music and clear queue",
        "?queue - Show the current song queue",
        "?volume <1-100> - Adjust volume"
    ],
    "Fun": [
        "?flip - Flip a coin",
        "?rps <rock/paper/scissors> - Play Rock Paper Scissors",
        "?guess <number> - Guess a number",
        "?trivia - Answer a trivia question"
    ],
    "Economy": [
        "?daily - Claim daily coins", "?coins - Check your balance",
        "?bet <amount> - Bet coins to win or lose"
    ],
    "Moderation": [
        "?ban <user> - Ban a user", "?kick <user> - Kick a user",
        "?mute <user> - Mute a user", "?unmute <user> - Unmute a user",
        "?warn <user> - Warn a user"
    ]
}


class HelpView(discord.ui.View):

    def __init__(self, ctx):
        super().__init__(timeout=60)  # Auto timeout after 60s
        self.ctx = ctx

    async def interaction_check(self,
                                interaction: discord.Interaction) -> bool:
        return interaction.user == self.ctx.author  # Restrict to command user only

    @discord.ui.button(label="🎵 Music",
                       style=discord.ButtonStyle.primary,
                       custom_id="music")
    async def music_button(self, interaction: discord.Interaction,
                           button: discord.ui.Button):
        await self.show_category(interaction, "Music")

    @discord.ui.button(label="🎮 Fun",
                       style=discord.ButtonStyle.success,
                       custom_id="fun")
    async def fun_button(self, interaction: discord.Interaction,
                         button: discord.ui.Button):
        await self.show_category(interaction, "Fun")

    @discord.ui.button(label="💰 Economy",
                       style=discord.ButtonStyle.blurple,
                       custom_id="economy")
    async def economy_button(self, interaction: discord.Interaction,
                             button: discord.ui.Button):
        await self.show_category(interaction, "Economy")

    @discord.ui.button(label="🛠 Moderation",
                       style=discord.ButtonStyle.danger,
                       custom_id="moderation")
    async def moderation_button(self, interaction: discord.Interaction,
                                button: discord.ui.Button):
        await self.show_category(interaction, "Moderation")

    async def show_category(self, interaction, category):
        commands_list = "\n".join(COMMAND_CATEGORIES[category])

        embed = discord.Embed(title=f"{category} Commands",
                              description=commands_list,
                              color=EMBED_COLOR)
        embed.set_footer(text="Use '?' before each command.")

        await interaction.response.edit_message(embed=embed, view=self)


@bot.command()
async def help(ctx):
    """Displays the bot's interactive help panel."""
    try:
        embed = discord.Embed(
            title="🤖 Help Panel",
            description="*Select a category below to view available commands:*",
            color=EMBED_COLOR)
        embed.add_field(name="🎵 Music",
                        value="Play and manage songs",
                        inline=False)
        embed.add_field(name="🎮 Fun",
                        value="Games and entertainment",
                        inline=False)
        embed.add_field(name="💰 Economy",
                        value="Earn and spend coins",
                        inline=False)
        embed.add_field(name="🛠 Moderation",
                        value="Manage your server",
                        inline=False)
        embed.set_footer(text="Made By Vihan")

        view = HelpView(ctx)
        await ctx.send(embed=embed, view=view)

    except Exception as e:
        print(f"Error in help command: {e}")
        error_embed = discord.Embed(
            title="⚠️ Error",
            description="An error occurred while processing your request.",
            color=0xFF0000)
        await ctx.send(embed=error_embed)


# member count command


@bot.command(name="mc")
async def membercount(ctx):
    member_count = ctx.guild.member_count
    online_count = sum(1 for member in ctx.guild.members
                       if member.status != discord.Status.offline)
    offline_count = sum(1 for member in ctx.guild.members
                        if member.status == discord.Status.offline)
    bot_count = sum(1 for member in ctx.guild.members if member.bot)
    embed = discord.Embed(
        title=f"Member Count: {ctx.guild.name}",
        description=
        f"There are currently {member_count} members in this server.",
        color=0x02a390)
    embed.add_field(name="Online Members", value=online_count, inline=False)
    embed.add_field(name="Offline Members", value=offline_count, inline=False)
    embed.add_field(name="Bots", value=bot_count, inline=False)
    await ctx.send(embed=embed)


# mute and unmute commands


@bot.command()
@commands.has_permissions(moderate_members=True)
async def timeout(ctx,
                  member: discord.Member,
                  time: str = None,
                  *,
                  reason="No reason provided"):
    """Timeouts a member for a specific duration (e.g., 10m, 1h, 2d)."""
    if not time:
        return await ctx.send(
            "❌ Please specify a duration! Example: `?timeout @user 10m`")
    time_units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    try:
        unit = time[-1]  # Last character of input (s/m/h/d)
        duration = int(time[:-1]) * time_units[unit]  # Convert to seconds
    except (ValueError, KeyError):
        return await ctx.send(
            "❌ Invalid time format! Use `10s`, `5m`, `2h`, `1d`.")
    if duration > 2419200:  # Discord max timeout is 28 days
        return await ctx.send("❌ The maximum timeout duration is **28 days**.")
    await member.timeout(timedelta(seconds=duration), reason=reason)
    embed = discord.Embed(title="⏳ Member Timed Out", color=EMBED_COLOR)
    embed.add_field(name="🔹 User", value=member.mention, inline=True)
    embed.add_field(name="⏳ Duration", value=time, inline=True)
    embed.add_field(name="📜 Reason", value=reason, inline=False)
    embed.set_footer(text="Use ?untimeout to remove the timeout.")
    await ctx.send(embed=embed)


@bot.command()
@commands.has_permissions(moderate_members=True)
async def untimeout(ctx, member: discord.Member):
    """Removes timeout from a user."""
    await member.timeout(None)
    embed = discord.Embed(title="✅ Timeout Removed", color=EMBED_COLOR)
    embed.add_field(name="🔹 User", value=member.mention, inline=True)
    embed.set_footer(text="User can now speak again.")
    await ctx.send(embed=embed)


# **Error Handling**


@timeout.error
@untimeout.error
async def timeout_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send(
            "❌ You need **Moderate Members** permission to use this command!")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(
            "❌ Missing arguments! Example usage: `?timeout @user 10m`")
    else:
        print(f"Error: {error}")
        await ctx.send("⚠ An unexpected error occurred!")


# member avatar


@bot.command(name="av")
async def avatar(ctx, member: discord.Member = None):
    if member is None:
        member = ctx.author

    embed = discord.Embed(
        title=f"{member.name}'s Avatar",
        description=f"[Download Avatar]({member.avatar.url})",
        color=0x02a390)
    embed.set_image(url=member.avatar.url)

    await ctx.send(embed=embed)


# terms and policy


@bot.command(name="t&p")
async def terms(ctx):
    embed = discord.Embed(
        title="Terms of Service and Privacy Policy",
        description=
        "Please read our terms of service and privacy policy carefully.",
        color=0x02a390)
    embed.add_field(
        name="Terms of Service",
        value=
        "These Terms of Service (\"Terms\") govern your use of our Discord bot (\"Bot\") and the services it provides.",
        inline=False)
    embed.add_field(
        name="Acceptance",
        value=
        "By using the Bot, you agree to be bound by these Terms. If you do not agree to these Terms, please do not use the Bot.",
        inline=False)
    embed.add_field(
        name="Use of the Bot",
        value=
        "You must use the Bot in compliance with these Terms and all applicable laws. You must not use the Bot to harass, abuse, or intimidate any person.",
        inline=False)
    embed.add_field(
        name="Intellectual Property",
        value=
        "The Bot and its underlying software and technology are protected by intellectual property laws. You must not attempt to reverse engineer, decompile, or disassemble the Bot.",
        inline=False)
    embed.add_field(
        name="Disclaimer of Warranties",
        value=
        "The Bot is provided \"as is\" and \"as available\" without warranties of any kind. We do not warrant that the Bot will be uninterrupted, error-free, or free from viruses or other malicious code.",
        inline=False)
    embed.add_field(
        name="Limitation of Liability",
        value=
        "We will not be liable for any damages or losses arising from your use of the Bot.",
        inline=False)
    embed.add_field(
        name="Termination",
        value=
        "We may terminate your access to the Bot at any time, without notice, for any reason.",
        inline=False)
    embed.add_field(
        name="Privacy Policy",
        value=
        "This Privacy Policy explains how we collect, use, and protect your personal data when you use our Discord bot.",
        inline=False)
    embed.add_field(
        name="Data Collection",
        value=
        "We collect data from you when you interact with the Bot, including your Discord username and any messages you send to the Bot.",
        inline=False)
    embed.add_field(
        name="Data Use",
        value=
        "We use the data we collect to provide the Bot's services, improve the Bot's performance, and respond to your inquiries.",
        inline=False)
    embed.add_field(
        name="Data Protection",
        value=
        "We take reasonable steps to protect your data from unauthorized access, disclosure, or destruction.",
        inline=False)
    embed.add_field(
        name="Data Retention",
        value=
        "We retain your data for as long as necessary to provide the Bot's services and to comply with applicable laws.",
        inline=False)
    embed.add_field(
        name="Your Rights",
        value=
        "You have the right to access, correct, or delete your data. You may also object to our processing of your data or request that we restrict our processing of your data.",
        inline=False)
    await ctx.send(embed=embed)


# server info


@bot.command(name="si")
async def serverinfo(ctx):
    embed = discord.Embed(
        title=f"{ctx.guild.name} Server Info",
        description=f"Here's some information about {ctx.guild.name}",
        color=0x02a390)

    if ctx.guild.icon:
        embed.set_thumbnail(url=ctx.guild.icon.url)

    embed.add_field(name="Server Name", value=ctx.guild.name, inline=False)

    embed.add_field(name="Server ID", value=ctx.guild.id, inline=False)

    embed.add_field(name="Server Owner", value=ctx.guild.owner, inline=False)

    embed.add_field(name="Member Count",
                    value=ctx.guild.member_count,
                    inline=False)

    embed.add_field(name="Role Count",
                    value=len(ctx.guild.roles),
                    inline=False)

    embed.add_field(name="Channel Count",
                    value=len(ctx.guild.channels),
                    inline=False)

    embed.add_field(name="Server Creation Date",
                    value=ctx.guild.created_at,
                    inline=False)

    await ctx.send(embed=embed)


# create role assign role and roleicon cmd


@bot.command(name="createrole")
@commands.has_permissions(manage_roles=True)
async def create_role(ctx, role_name: str, color: discord.Color):
    await ctx.guild.create_role(name=role_name, color=color)

    embed = discord.Embed(
        title="Role Created",
        description=f"The {role_name} role has been created.",
        color=0x02a390)

    await ctx.send(embed=embed)


@bot.command(name="assignrole")
@commands.has_permissions(manage_roles=True)
async def assignrole(ctx, member: discord.Member, role: discord.Role):
    await member.add_roles(role)
    embed = discord.Embed(
        title="Role Assigned",
        description=
        f"{member.mention} has been assigned the {role.mention} role.",
        color=0x02a390)
    await ctx.send(embed=embed)


@bot.command(name="roleicon")
@commands.has_permissions(manage_roles=True)
async def add_role_icon(ctx, role: discord.Role, icon_url: str):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(icon_url) as response:
                icon_bytes = await response.read()
        await role.edit(icon=icon_bytes)
        embed = discord.Embed(
            title="Role Icon Added",
            description=f"The icon has been added to the {role.name} role.",
            color=0x02a390)
        await ctx.send(embed=embed)
    except Exception as e:
        embed = discord.Embed(title="Error",
                              description=str(e),
                              color=0x02a390)
        await ctx.send(embed=embed)


# custom prefix


@bot.event
async def on_ready():
    global prefixes
    with open('prefixes.json', 'r') as f:
        prefixes = json.load(f)


@bot.command(name='sprefix')
@commands.has_permissions(administrator=True)
async def setprefix(ctx, prefix: str):
    with open('prefixes.json', 'r') as f:
        prefixes = json.load(f)
    prefixes[str(ctx.guild.id)] = prefix
    with open('prefixes.json', 'w') as f:
        json.dump(prefixes, f)
    embed = discord.Embed(
        title="Prefix Updated",
        description=
        f"The prefix for this server has been updated to `{prefix}`",
        color=0x02a390)
    await ctx.send(embed=embed)


def get_prefix(bot, message):
    with open('prefixes.json', 'r') as f:
        prefixes = json.load(f)
    return prefixes.get(str(message.guild.id), '?')


bot.command_prefix = get_prefix


@bot.event
async def on_message(message):
    await bot.process_commands(message)


# tag cmd X afk


class AFKView(discord.ui.View):

    def __init__(self, user):
        super().__init__(timeout=None)
        self.user = user

    async def interaction_check(self,
                                interaction: discord.Interaction) -> bool:
        return interaction.user == self.user

    async def handle_afk(self, interaction: discord.Interaction,
                         afk_type: str):
        embed = discord.Embed(
            title="✅ AFK Enabled",
            description=f"{self.user.mention} is now **{afk_type} AFK**! 💤",
            color=EMBED_COLOR)
        embed.set_footer(
            text="You will be removed from AFK when you send a message.")
        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="🌍 Global AFK", style=discord.ButtonStyle.blurple)
    async def global_afk(self, interaction: discord.Interaction,
                         button: discord.ui.Button):
        await self.handle_afk(interaction, "Global")

    @discord.ui.button(label="🏠 Server AFK", style=discord.ButtonStyle.green)
    async def server_afk(self, interaction: discord.Interaction,
                         button: discord.ui.Button):
        await self.handle_afk(interaction, "Server")


@bot.command()
async def afk(ctx):
    embed = discord.Embed(title="🛌 Set AFK Status",
                          description="Choose AFK type below:",
                          color=EMBED_COLOR)
    view = AFKView(ctx.author)
    await ctx.send(embed=embed, view=view)


# Example Fix: Bot Mention Response
@bot.event
async def on_message(message):
    if bot.user in message.mentions:
        embed = discord.Embed(
            title="Hello! 🤖",
            description=
            "I am Fluxx, a powerful Discord bot! Use ?help to see my commands.",
            color=EMBED_COLOR)
        embed.set_footer(text="Made by Vihan")
        await message.channel.send(embed=embed)

    await bot.process_commands(message)


@bot.command()
async def test(ctx):
    await ctx.send("Hello!")


# FUN GAMES

# File to store user coin data
COINS_FILE = "coins.json"


def load_coins():
    """Loads coin data from a file."""
    try:
        with open(COINS_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save_coins(data):
    """Saves coin data to a file."""
    with open(COINS_FILE, "w") as f:
        json.dump(data, f, indent=4)


coins = load_coins()


@bot.command()
async def daily(ctx):
    """Gives daily coins with a 12-hour cooldown and increasing streak rewards."""
    user_id = str(ctx.author.id)
    now = datetime.now(datetime.timezone.utc)

    user_data = coins.get(user_id, {
        "last_claim": None,
        "streak": 0,
        "coins": 0
    })

    last_claim = user_data.get("last_claim")
    if last_claim:
        last_claim = datetime.fromisoformat(last_claim)
        if now - last_claim < timedelta(hours=12):
            embed = discord.Embed(
                title="❌ Daily Reward",
                description=
                "You have already claimed your daily reward! Try again later.",
                color=EMBED_COLOR)
            return await ctx.send(embed=embed)

    if last_claim and now - last_claim < timedelta(days=1):
        user_data["streak"] += 1
    else:
        user_data["streak"] = 1

    reward = 100 + (user_data["streak"] * 20)
    user_data["coins"] += reward
    user_data["last_claim"] = now.isoformat()
    coins[user_id] = user_data
    save_coins(coins)

    embed = discord.Embed(
        title="💰 Daily Reward",
        description=
        f"You received *{reward} coins*! Streak: {user_data['streak']} days.",
        color=EMBED_COLOR)
    await ctx.send(embed=embed)


@bot.command()
async def coins(ctx):
    """Check your coin balance."""
    user_id = str(ctx.author.id)
    user_data = coins.get(user_id, {"coins": 0})
    embed = discord.Embed(
        title="💰 Coin Balance",
        description=f"You have *{user_data['coins']} coins*!",
        color=EMBED_COLOR)
    await ctx.send(embed=embed)


@bot.command()
async def flip(ctx):
    """Flip a coin!"""
    result = random.choice(["Heads", "Tails"])
    embed = discord.Embed(title="🪙 Coin Flip",
                          description=f"You flipped *{result}*!",
                          color=EMBED_COLOR)
    await ctx.send(embed=embed)


@bot.command()
async def rps(ctx, choice: str):
    """Play Rock Paper Scissors."""
    options = ["rock", "paper", "scissors"]
    bot_choice = random.choice(options)
    choice = choice.lower()
    if choice not in options:
        embed = discord.Embed(title="❌ Invalid Choice",
                              description="Choose rock, paper, or scissors!",
                              color=EMBED_COLOR)
        return await ctx.send(embed=embed)

    outcome = "You Win!" if (choice == "rock" and bot_choice == "scissors") or \
        (choice == "paper" and bot_choice == "rock") or \
        (choice == "scissors" and bot_choice == "paper") else "You Lose!" if choice != bot_choice else "It's a Draw!"

    embed = discord.Embed(
        title="🎮 Rock Paper Scissors",
        description=f"You chose *{choice}, I chose **{bot_choice}*. {outcome}",
        color=EMBED_COLOR)
    await ctx.send(embed=embed)


@bot.command()
async def guess(ctx, number: int):
    """Guess a number between 1 and 10."""
    correct = random.randint(1, 10)
    embed = discord.Embed(title="🎯 Number Guess", color=EMBED_COLOR)
    if number == correct:
        embed.description = f"🎉 Congrats {ctx.author.mention}, you guessed it right! *{correct}*"
    else:
        embed.description = f"❌ Wrong! The correct number was *{correct}*."
    await ctx.send(embed=embed)


@bot.command()
async def trivia(ctx):
    """Random trivia question."""
    questions = {
        "What is the capital of France?": "Paris",
        "Who wrote 'Harry Potter'?": "J.K. Rowling",
        "What is 2 + 2?": "4"
    }
    question, answer = random.choice(list(questions.items()))
    embed = discord.Embed(title="🧠 Trivia Time!",
                          description=question,
                          color=EMBED_COLOR)
    await ctx.send(embed=embed)

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel

    try:
        response = await bot.wait_for("message", check=check, timeout=10.0)
        if response.content.lower() == answer.lower():
            result_embed = discord.Embed(title="✅ Correct!",
                                         description="You got it right!",
                                         color=EMBED_COLOR)
        else:
            result_embed = discord.Embed(
                title="❌ Wrong!",
                description=f"The correct answer was *{answer}*.",
                color=EMBED_COLOR)
    except asyncio.TimeoutError:
        result_embed = discord.Embed(
            title="⏳ Time's Up!",
            description=f"The correct answer was *{answer}*.",
            color=EMBED_COLOR)

    await ctx.send(embed=result_embed)


@bot.command()
@commands.has_permissions(manage_channels=True)
async def lock(ctx, role: discord.Role = None):
    """Locks the channel, allowing only a specific role to send messages (if provided)."""
    if role:
        await ctx.channel.set_permissions(ctx.guild.default_role,
                                          send_messages=False)
        await ctx.channel.set_permissions(role, send_messages=True)
        role_text = f"Only {role.mention} can send messages."
    else:
        await ctx.channel.set_permissions(ctx.guild.default_role,
                                          send_messages=False)
        role_text = "No one can send messages except admins."

    embed = discord.Embed(
        title="🔒 Channel Locked",
        description=f"{ctx.channel.mention} has been locked!\n{role_text}",
        color=0x02A390)
    await ctx.send(embed=embed)


@bot.command()
@commands.has_permissions(manage_channels=True)
async def unlock(ctx):
    """Unlocks the channel, allowing everyone to send messages again."""
    await ctx.channel.set_permissions(ctx.guild.default_role,
                                      send_messages=True)

    embed = discord.Embed(
        title="🔓 Channel Unlocked",
        description=
        f"{ctx.channel.mention} has been unlocked! Everyone can send messages again.",
        color=0x02A390)
    await ctx.send(embed=embed)


# slow mode system

# Global dictionary to track message counts per channel over the past minute
channel_message_counts = {}

# Global flag for enabling/disabling slow mode system
slowmode_enabled = False


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Increase message count for the channel
    channel_id = message.channel.id
    channel_message_counts[channel_id] = channel_message_counts.get(
        channel_id, 0) + 1
    await bot.process_commands(message)


async def adjust_slowmode():
    await bot.wait_until_ready()
    threshold = 10  # Example threshold: 10 messages per minute
    global slowmode_enabled
    while not bot.is_closed():
        if slowmode_enabled:
            for channel_id, count in list(channel_message_counts.items()):
                channel = bot.get_channel(channel_id)
                if channel and isinstance(channel, discord.TextChannel):
                    try:
                        if count >= threshold:
                            await channel.edit(slowmode_delay=3)
                        else:
                            await channel.edit(slowmode_delay=1)
                    except Exception as e:
                        print(
                            f"Error updating slow mode in {channel.name}: {e}")
            # Clear counts for the next interval
            channel_message_counts.clear()
        await asyncio.sleep(60)


@bot.command()
@commands.has_permissions(manage_channels=True)
async def enable(ctx):
    """Enable the slow mode system."""
    global slowmode_enabled
    slowmode_enabled = True
    embed = discord.Embed(
        title="✅ Slow Mode System Enabled",
        description=
        "The slow mode system is now active and will adjust slow mode based on channel activity.",
        color=EMBED_COLOR)
    embed.set_footer(
        text="Slow mode will update every minute based on message activity.")
    await ctx.send(embed=embed)


@bot.command()
@commands.has_permissions(manage_channels=True)
async def disable(ctx):
    """Disable the slow mode system."""
    global slowmode_enabled
    slowmode_enabled = False
    embed = discord.Embed(
        title="❌ Slow Mode System Disabled",
        description=
        "The slow mode system is now inactive and will no longer adjust slow mode settings.",
        color=EMBED_COLOR)
    embed.set_footer(
        text="You can re-enable the system with ?enable when needed.")
    await ctx.send(embed=embed)


@bot.command()
async def slowmode_status(ctx):
    """Check if the slow mode system is enabled."""
    global slowmode_enabled
    if slowmode_enabled:
        embed = discord.Embed(
            title="✅ Slow Mode System Status",
            description="The slow mode system is currently **enabled**.",
            color=0x02a390)
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(
            title="✅ Slow Mode System Status",
            description="The slow mode system is currently **disabled**.",
            color=0x02a390)
        await ctx.send(embed=embed)


# reminders


# Reminder System
@bot.command()
async def remind(ctx, time_str: str, *, message: str):
    """Set a reminder. Usage: ?remind <time> <message>"""
    try:
        time_units = {"s": 1, "m": 60, "h": 3600}
        unit = time_str[-1]  # Last character of input (s/m/h)
        if unit not in time_units:
            raise ValueError(
                "Invalid time unit! Use 's', 'm', or 'h' (e.g., 10s, 5m, 1h).")

        time_amount = int(time_str[:-1])  # Extract numeric part
        wait_time = time_amount * time_units[unit]  # Convert to seconds

        embed = discord.Embed(
            title="⏳ Reminder Set",
            description=f"**{message}**\nI will remind you in `{time_str}`.",
            color=EMBED_COLOR)
        await ctx.send(embed=embed)

        await asyncio.sleep(wait_time)  # Wait for the given time

        reminder_embed = discord.Embed(
            title="🔔 Reminder!",
            description=
            f"{ctx.author.mention}, you asked to be reminded:\n**{message}**",
            color=EMBED_COLOR)
        await ctx.send(embed=reminder_embed)

    except Exception as e:
        error_embed = discord.Embed(
            title="⚠️ Error",
            description="Invalid time format! Use `5s`, `10m`, or `1h`.",
            color=0xFF0000)
        await ctx.send(embed=error_embed)


# Bot System Stats Command
start_time = time.time()


@bot.command()
async def stats(ctx):
    """Show bot system stats (CPU, RAM, and Uptime)."""
    cpu_usage = psutil.cpu_percent()
    ram_usage = psutil.virtual_memory().percent
    uptime_seconds = int(time.time() - start_time)
    uptime = f"{uptime_seconds // 3600}h {uptime_seconds % 3600 // 60}m {uptime_seconds % 60}s"

    embed = discord.Embed(title="📊 Bot System Stats", color=EMBED_COLOR)
    embed.add_field(name="🖥 CPU Usage", value=f"{cpu_usage}%", inline=True)
    embed.add_field(name="💾 RAM Usage", value=f"{ram_usage}%", inline=True)
    embed.add_field(name="⏳ Uptime", value=uptime, inline=True)
    embed.set_footer(text="Made By Vihan")

    await ctx.send(embed=embed)


# weather

# Replace with your OpenWeatherMap API key
WEATHER_API_KEY = "66456a302337aacf9258c8d8f64dd29c"


@bot.command()
async def weather(ctx, *, location: str):
    """Shows weather for yesterday, today, and tomorrow."""
    try:
        # Get current date
        utc = pytz.UTC
        today = datetime.now(utc).date()
        yesterday = today - timedelta(days=1)
        tomorrow = today + timedelta(days=1)

        # OpenWeatherMap API endpoint
        url = f"http://api.openweathermap.org/data/2.5/forecast?q={location}&units=metric&appid={WEATHER_API_KEY}"

        # Fetch weather data
        response = requests.get(url)
        data = response.json()

        if data.get("cod") != "200":
            return await ctx.send("❌ Invalid location or data unavailable!")

        # Extract required details
        city = data["city"]["name"]
        country = data["city"]["country"]

        # Find weather for specific days
        weather_data = {}
        for forecast in data["list"]:
            date = datetime.fromtimestamp(forecast["dt"], tz=pytz.UTC).date()

            if date in [yesterday, today, tomorrow
                        ] and date not in weather_data:
                weather_data[date] = {
                    "temp": forecast["main"]["temp"],
                    "desc": forecast["weather"][0]["description"].title(),
                    "icon": forecast["weather"][0]["icon"]
                }

        # Create an embed
        embed = discord.Embed(title=f"🌍 Weather in {city}, {country}",
                              color=EMBED_COLOR)
        for date, details in weather_data.items():
            icon_url = f"http://openweathermap.org/img/wn/{details['icon']}.png"
            embed.add_field(
                name=f"📅 {date.strftime('%A, %d %B')}",
                value=f"🌡 **{details['temp']}°C**\n☁ {details['desc']}",
                inline=False)
            embed.set_thumbnail(url=icon_url)
            embed.set_footer(text="Made By Vihan")
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send("⚠ Error fetching weather data!")
        print(f"Weather command error:{e}")


# spamtag
spam_tasks = {}


@bot.command()
async def spamtag(ctx, member: discord.Member):
    """Start spamming a user with pings until stopped."""
    if ctx.guild.id in spam_tasks:
        embed = discord.Embed(
            title="❌ Error",
            description=
            "A spam session is already running! Use ?spamstop to stop it first.",
            color=0xFF0000)
        return await ctx.send(embed=embed)

    embed = discord.Embed(
        title="🚀 Spam Started!",
        description=f"Now spamming {member.mention}! Use ?spamstop to stop.",
        color=EMBED_COLOR)
    await ctx.send(embed=embed)

    async def spam_task():
        while True:
            spam_embed = discord.Embed(title="🤖 Spam Ping!",
                                       description=f"{member.mention}",
                                       color=EMBED_COLOR)
            await ctx.send(embed=spam_embed)
            await asyncio.sleep(0.01)  # Delay between pings

    spam_tasks[ctx.guild.id] = bot.loop.create_task(
        spam_task())  # Start the task


@bot.command()
async def spamstop(ctx):
    """Stops the spam."""
    if ctx.guild.id not in spam_tasks:
        embed = discord.Embed(title="❌ Error",
                              description="No active spam session to stop!",
                              color=0xFF0000)
        return await ctx.send(embed=embed)

    spam_tasks[ctx.guild.id].cancel()  # Stop the task
    del spam_tasks[ctx.guild.id]  # Remove from tracking

    embed = discord.Embed(
        title="✅ Spam Stopped!",
        description="Spamming has been stopped successfully!",
        color=0x02a390)
    await ctx.send(embed=embed)


#welcomer

WELCOME_DATA_FILE = "welcome_data.json"
BANNER_URL = "https://i.imgur.com/your_banner_image.png"  # Replace with your banner image URL


# Load welcome data
def load_welcome_data():
    try:
        with open(WELCOME_DATA_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


# Save welcome data
def save_welcome_data(data):
    with open(WELCOME_DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)


@bot.event
async def on_ready():
    print(f"{bot.user} is online and ready!")
    try:
        synced = await bot.tree.sync()  # Sync slash commands
        print(f"🔄 Synced {len(synced)} slash commands.")
    except Exception as e:
        print(f"⚠ Error syncing commands: {e}")


# Slash Command: Set Welcome Channel
@bot.tree.command(name="setwelcome",
                  description="Set a welcome channel for new members")
@app_commands.checks.has_permissions(administrator=True)
async def set_welcome(interaction: discord.Interaction,
                      channel: discord.TextChannel):
    welcome_data = load_welcome_data()
    welcome_data[str(interaction.guild.id)] = channel.id
    save_welcome_data(welcome_data)

    embed = discord.Embed(
        title="✅ Welcome Channel Set!",
        description=f"Welcome messages will be sent in {channel.mention}.",
        color=discord.Color.green())
    await interaction.response.send_message(embed=embed, ephemeral=True)


# Slash Command: Disable Welcome Message
@bot.tree.command(name="disablewelcome",
                  description="Disable the welcome message")
@app_commands.checks.has_permissions(administrator=True)
async def disable_welcome(interaction: discord.Interaction):
    welcome_data = load_welcome_data()
    if str(interaction.guild.id) in welcome_data:
        del welcome_data[str(interaction.guild.id)]
        save_welcome_data(welcome_data)
        await interaction.response.send_message("❌ Welcome messages disabled.",
                                                ephemeral=True)
    else:
        await interaction.response.send_message(
            "⚠ No welcome channel was set.", ephemeral=True)


# Event: Welcome Message When a Member Joins
@bot.event
async def on_member_join(member):
    welcome_data = load_welcome_data()
    channel_id = welcome_data.get(str(member.guild.id))

    if channel_id:
        channel = member.guild.get_channel(channel_id)
        if channel:
            embed = discord.Embed(
                title="🎉 Welcome!",
                description=
                f"Hey {member.mention}, welcome to **{member.guild.name}**! 🎊\nWe’re glad to have you here. Make sure to read the rules and have fun!",
                color=discord.Color.green())
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text="Welcome to the Server", icon_url=BANNER_URL)
            await channel.send(embed=embed)


@bot.event
async def on_ready():
    print(f"✅ Bot is online as {bot.user}")


# Setup hook for async tasks
async def setup_hook():
    bot.loop.create_task(
        adjust_slowmode())  # Make sure adjust_slowmode() exists


bot.setup_hook = setup_hook


# Main function
async def main():
    async with bot:
        token = os.getenv(
            "DISCORD_TOKEN")  # Fetch token securely from Replit secrets
        if not token:
            print(
                "❌ ERROR: No token found! Make sure to add DISCORD_TOKEN in Replit Secrets."
            )
            return
        await bot.start(token)


# Run the bot
asyncio.run(main())


while True:
    pass
