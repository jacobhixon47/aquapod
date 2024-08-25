import os
import logging
from dotenv import load_dotenv
import yt_dlp
import pprint

import discord
from discord import app_commands
from discord.ext import commands

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

# logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('discord')
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

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

    print(f"Received query: {query}")

    try:
        if 'open.spotify.com' in query:
            # Handle Spotify URL
            if '/episode/' in query:
                episode_id = query.split('/episode/')[-1].split('?')[0]
            elif '/show/' in query:
                show_id = query.split('/show/')[-1].split('?')[0]
                # Get the latest episode of the show
                show = spotify.show(show_id)
                episode_id = show['episodes']['items'][0]['id']
            else:
                await interaction.response.send_message("Invalid Spotify link. Please provide an episode or show link.")
                return
            
            episode = spotify.episode(episode_id)
        else:
            results = spotify.search(q=query, type='episode', limit=1)
            
            print(f"Spotify search results: {results}")

            if not results['episodes']['items']:
                await interaction.response.send_message("No podcast found.")
                return
            episode = results['episodes']['items'][0]

        pod_info = {
            'name': episode['name'],
            'url': episode['external_urls']['spotify'],
            'duration': episode['duration_ms'] / 1000  # Convert to seconds
        }

        pprint.pp(f"Pod info: \n{pod_info}", indent=2, width=50)

        if bot.current_pod:
            bot.pod_queue.append(pod_info)
            await interaction.response.send_message(f"Added to queue: {pod_info['name']}")
        else:
            bot.current_pod = pod_info
            await play_podcast(interaction)
    except Exception as e:
        await interaction.response.send_message(f"An error occurred: {str(e)}")
        print(f"Error in play command: {e}")

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
    if len(current) < 2:
        return []
    try:
        results = spotify.search(q=current, type='episode', limit=5)
        choices = [
            app_commands.Choice(name=episode['name'][:100], value=episode['name'][:100])
            for episode in results['episodes']['items']
        ]
        print(f"Autocomplete results for '{current}': {choices}")
        return choices
    except Exception as e:
        print(f"Autocomplete error: {e}")
        return []


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