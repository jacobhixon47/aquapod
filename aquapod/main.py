import os
import logging
import asyncio
from dotenv import load_dotenv
import yt_dlp
import pprint

import discord
from discord import app_commands
from discord.ext import commands

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials


# get tokens from .env
load_dotenv()

SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')
DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')

# Set up Spotify client
spotify = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials(
    client_id=SPOTIFY_CLIENT_ID,
    client_secret=SPOTIFY_CLIENT_SECRET
))

# # logging setup
# logging.basicConfig(level=logging.info)

intents = discord.Intents.default()
intents.message_content = True

# setup discord bot 
class PodBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!', intents=intents)
        self.pod_queue = []
        self.current_pod = None

    async def setup_hook(self):
        await self.tree.sync()

bot = PodBot()

# error handling and logging
# @bot.event
# async def on_command_error(ctx, error):
#     if isinstance(error, commands.CommandInvokeError):
#         await ctx.send(f"An error occurred: {error.original}")
#     logging.error(f"An error occurred: {error}", exc_info=True)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')

async def is_dj_or_admin(interaction: discord.Interaction) -> bool:
    return interaction.user.guild_permissions.administrator or discord.utils.get(interaction.user.roles, name="DJ") is not None

@bot.tree.command()
@app_commands.describe(query="Search for a pod or provide a link")
async def play(interaction: discord.Interaction, query: str):
    if not await is_dj_or_admin(interaction):
        await interaction.response.send_message("You need to be a DJ or admin to use this command.")
        return

    if interaction.user.voice is None:
        await interaction.response.send_message("You need to be in a voice channel to play podcasts.")
        return

    voice_channel = interaction.user.voice.channel
    if not interaction.guild.voice_client:
        await voice_channel.connect()
    elif interaction.guild.voice_client.channel != voice_channel:
        await interaction.guild.voice_client.move_to(voice_channel)

    results = spotify.search(q=query, type='episode', limit=5)

    if not results['episodes']['items']:
        await interaction.response.send_message("No podcast found.")
        return

    episode = results['episodes']['items'][0]
    pod_info = {
        'name': episode['name'],
        'url': episode['external_urls']['spotify'],
        'duration': episode['duration_ms'] / 1000  # Convert to seconds
    }
    pprint.pp(pod_info, indent=2, width=50)

    if bot.current_pod:
        bot.pod_queue.append(pod_info)
        await interaction.response.send_message(f"Added to queue: {pod_info['name']}")
    else:
        bot.current_pod = pod_info
        await play_podcast(interaction)

async def play_podcast(interaction: discord.Interaction):
    if not bot.current_pod:
        return

    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(bot.current_pod['url'], download=False)
        url = info['url']

    voice_client = interaction.guild.voice_client
    voice_client.play(discord.FFmpegPCMAudio(url), after=lambda e: bot.loop.create_task(play_next(interaction)))
    await interaction.followup.send(f"Now playing: {bot.current_pod['name']}")

async def play_next(interaction: discord.Interaction):
    if bot.pod_queue:
        bot.current_pod = bot.pod_queue.pop(0)
        await play_podcast(interaction)
    else:
        bot.current_pod = None

@play.autocomplete('query')
async def play_autocomplete(interaction: discord.Interaction, current: str):
    if not current:
        return []
    results = spotify.search(q=current, type='episode', limit=5)
    return [
        app_commands.Choice(name=episode['name'], value=episode['name'])
        for episode in results['episodes']['items']
    ]

@bot.tree.command()
async def pause(interaction: discord.Interaction):
    if not await is_dj_or_admin(interaction):
        await interaction.response.send_message("You need to be a DJ or admin to use this command.")
        return
    if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
        interaction.guild.voice_client.pause()
        await interaction.response.send_message("Paused the podcast.")
    else:
        await interaction.response.send_message("No podcast is currently playing.")

@bot.tree.command()
async def resume(interaction: discord.Interaction):
    if not await is_dj_or_admin(interaction):
        await interaction.response.send_message("You need to be a DJ or admin to use this command.")
        return
    if interaction.guild.voice_client and interaction.guild.voice_client.is_paused():
        interaction.guild.voice_client.resume()
        await interaction.response.send_message("Resumed the podcast.")
    else:
        await interaction.response.send_message("No podcast is paused.")

@bot.tree.command()
async def stop(interaction: discord.Interaction):
    if not await is_dj_or_admin(interaction):
        await interaction.response.send_message("You need to be a DJ or admin to use this command.")
        return
    if interaction.guild.voice_client:
        interaction.guild.voice_client.stop()
        await interaction.guild.voice_client.disconnect()
        bot.current_pod = None
        bot.pod_queue.clear()
        await interaction.response.send_message("Stopped the podcast and cleared the queue.")
    else:
        await interaction.response.send_message("No podcast is currently playing.")

@bot.tree.command()
async def skip(interaction: discord.Interaction):
    if not await is_dj_or_admin(interaction):
        await interaction.response.send_message("You need to be a DJ or admin to use this command.")
        return
    if interaction.guild.voice_client and (interaction.guild.voice_client.is_playing() or interaction.guild.voice_client.is_paused()):
        interaction.guild.voice_client.stop()
        await interaction.response.send_message("Skipped the current podcast.")
        await play_next(interaction)
    else:
        await interaction.response.send_message("No podcast is currently playing.")

@bot.tree.command()
async def clear_queue(interaction: discord.Interaction):
    if not await is_dj_or_admin(interaction):
        await interaction.response.send_message("You need to be a DJ or admin to use this command.")
        return
    bot.pod_queue.clear()
    await interaction.response.send_message("Cleared the podcast queue.")

bot.run(DISCORD_BOT_TOKEN)