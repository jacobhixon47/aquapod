import os
import logging
import threading
import keyboard
from dotenv import load_dotenv
import yt_dlp
import asyncio
from concurrent.futures import ThreadPoolExecutor

import discord
from discord import app_commands
from discord.ext import commands

# logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('discord')
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

# get tokens from .env
load_dotenv()

DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
SHOULD_SYNC = os.getenv('SHOULD_SYNC', 'false').lower() == 'true'

intents = discord.Intents.default()
intents.message_content = True

executor = ThreadPoolExecutor()

# Colors for terminal messages
class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    OKMAGENTA = '\033[95m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    DEFAULT = '\033[99m'

# Setup Discord bot 
class PodBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!', intents=intents)
        self.guild_data = {}  # Dictionary to hold data for each guild

    def get_guild_data(self, guild_id):
        """Retrieve or initialize data for a specific guild."""
        if guild_id not in self.guild_data:
            self.guild_data[guild_id] = {
                'pod_queue': [],
                'current_pod': None,
                'queue_message': None,
                'assigned_channel_id': None
            }
        return self.guild_data[guild_id]

    async def setup_hook(self):
        if SHOULD_SYNC:
            await self.tree.sync()  # Sync commands on setup; adjust if needed

bot = PodBot()

class ControlButtons(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label='Pause', style=discord.ButtonStyle.primary, emoji='⏸️')
    async def pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await is_dj_or_admin(interaction):
            await interaction.response.send_message("You need to be a DJ or admin to use this button.", ephemeral=True)
            return
        await pause_action(interaction)

    @discord.ui.button(label='Resume', style=discord.ButtonStyle.primary, emoji='▶️')
    async def resume_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await is_dj_or_admin(interaction):
            await interaction.response.send_message("You need to be a DJ or admin to use this button.", ephemeral=True)
            return
        await resume_action(interaction)

    @discord.ui.button(label='Skip', style=discord.ButtonStyle.primary, emoji='⏭️')
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await is_dj_or_admin(interaction):
            await interaction.response.send_message("You need to be a DJ or admin to use this button.", ephemeral=True)
            return
        await skip_action(interaction)

    @discord.ui.button(label='Stop', style=discord.ButtonStyle.danger, emoji='⏹️')
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await is_dj_or_admin(interaction):
            await interaction.response.send_message("You need to be a DJ or admin to use this button.", ephemeral=True)
            return
        await stop_action(interaction)

@bot.event
async def on_ready():
    print(f'{bcolors.OKBLUE}Logged in as {bot.user}')
    await find_controller_channel()

async def find_controller_channel():
    for guild in bot.guilds:
        guild_data = bot.get_guild_data(guild.id)
        channel = discord.utils.get(guild.text_channels, name="aquapod-controller")

        if channel:
            guild_data['assigned_channel_id'] = channel.id
            print(f"{bcolors.OKBLUE}Found #aquapod-controller channel in guild {guild.name}. ID: {channel.id}{bcolors.DEFAULT}")

            # Delete all messages in the channel
            async for message in channel.history(limit=None):
                try:
                    await message.delete()
                except Exception as e:
                    print(f"{bcolors.WARNING}Failed to delete message in guild {guild.name}: {e}{bcolors.DEFAULT}")

            # Create a new persistent queue message for this channel
            guild_data['queue_message'] = await channel.send(content=update_queue_message_content(guild.id), view=ControlButtons())
        else:
            print(f"{bcolors.WARNING}Could not find #aquapod-controller channel in guild {guild.name}.{bcolors.DEFAULT}")

async def is_dj_or_admin(interaction: discord.Interaction) -> bool:
    user = interaction.user if hasattr(interaction, 'user') else getattr(interaction, 'member', None)
    if user is None:
        return False
    return user.guild_permissions.administrator or discord.utils.get(user.roles, name="DJ") is not None

def update_queue_message_content(guild_id) -> str:
    """Generates the content for the persistent queue message for a specific guild."""
    guild_data = bot.get_guild_data(guild_id)
    now_playing = f"**Now Playing:** {guild_data['current_pod']['name'] if guild_data['current_pod'] else 'Nothing'}"

    queue_content = "\n\n**Queue (next 5):**\n"
    if not guild_data['pod_queue']:
        queue_content += "The queue is currently empty."
    else:
        # Show only the next 5 songs
        for idx, pod in enumerate(guild_data['pod_queue'][:5], start=1):
            queue_content += f"{idx}. {pod['name']}\n"
        if len(guild_data['pod_queue']) > 5:
            queue_content += f"...and {len(guild_data['pod_queue']) - 5} more."

    return now_playing + queue_content

async def update_queue_message(interaction: discord.Interaction):
    """Updates the persistent queue message or sends a new one if it does not exist."""
    guild_data = bot.get_guild_data(interaction.guild.id)
    
    if guild_data['assigned_channel_id']:
        channel = bot.get_channel(guild_data['assigned_channel_id'])
        if guild_data['queue_message']:
            await guild_data['queue_message'].edit(content=update_queue_message_content(interaction.guild.id), view=ControlButtons())
        else:
            guild_data['queue_message'] = await channel.send(content=update_queue_message_content(interaction.guild.id), view=ControlButtons())
    else:
        await interaction.response.send_message("No channel is set for the bot. Use the /set_channel command to set one.", ephemeral=True)

async def play_podcast(interaction: discord.Interaction):
    guild_data = bot.get_guild_data(interaction.guild.id)

    if not guild_data['current_pod']:
        await interaction.followup.send("Nothing is currently set to play.", ephemeral=True)
        return

    try:
        print(f"{bcolors.OKCYAN}Attempting to play: {guild_data['current_pod']['name']}{bcolors.DEFAULT}")
        is_live = guild_data['current_pod'].get('is_live', False)
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': True,
            'noplaylist': True,
            'cachedir': False
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(guild_data['current_pod']['url'], download=False)
            url = info.get('url')

        if not url:
            await interaction.followup.send("Failed to play the current track.", ephemeral=True)
            await play_next(interaction)
            return

        voice_client = interaction.guild.voice_client
        voice_client.play(discord.FFmpegPCMAudio(url), after=lambda e: bot.loop.create_task(play_next(interaction)))
        
    except Exception as e:
        print(f"{bcolors.FAIL}Error in play_podcast: {e}{bcolors.DEFAULT}")
        await interaction.followup.send(f"An error occurred while trying to play the track.", ephemeral=True)
        
        if len(guild_data['pod_queue']) > 0:
            await play_next(interaction)
        else:
            guild_data['current_pod'] = None

    await update_queue_message(interaction)

async def play_next(interaction: discord.Interaction):
    guild_data = bot.get_guild_data(interaction.guild.id)

    if len(guild_data['pod_queue']) > 0:
        guild_data['current_pod'] = guild_data['pod_queue'].pop(0)
        await play_podcast(interaction)
    else:
        guild_data['current_pod'] = None
        await interaction.followup.send("No more tracks in queue.", ephemeral=True)
    
    await update_queue_message(interaction)

async def pause_action(interaction: discord.Interaction):
    if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
        interaction.guild.voice_client.pause()
        await interaction.response.send_message("Paused the playback.", ephemeral=True)
    else:
        await interaction.response.send_message("No audio is currently playing.", ephemeral=True)

async def resume_action(interaction: discord.Interaction):
    if interaction.guild.voice_client and interaction.guild.voice_client.is_paused():
        interaction.guild.voice_client.resume()
        await interaction.response.send_message("Resumed the playback.", ephemeral=True)
    else:
        await interaction.response.send_message("No audio is paused.", ephemeral=True)

async def skip_action(interaction: discord.Interaction):
    if interaction.guild.voice_client and (interaction.guild.voice_client.is_playing() or interaction.guild.voice_client.is_paused()):
        interaction.guild.voice_client.stop()
        await interaction.response.send_message("Skipped the current track.", ephemeral=True)
    else:
        await interaction.response.send_message("No audio is currently playing.", ephemeral=True)

async def stop_action(interaction: discord.Interaction):
    guild_data = bot.get_guild_data(interaction.guild.id)

    if interaction.guild.voice_client:
        interaction.guild.voice_client.stop()
        await interaction.guild.voice_client.disconnect()
        guild_data['current_pod'] = None
        guild_data['pod_queue'].clear()
        await interaction.response.send_message("Stopped the playback and cleared the queue.", ephemeral=True)
    else:
        await interaction.response.send_message("No audio is currently playing.", ephemeral=True)

async def extract_playlist_videos_async(query: str):
    """Extracts the video URLs from a playlist and processes them one at a time."""
    ydl_opts = {
        'quiet': True,
        'extract_flat': True,  # Extract metadata without downloading or fetching full details
        'cachedir': False,
        'ignoreerrors': True,  # Skip problematic videos in the playlist
        'retries': 5,
        'socket_timeout': 15
    }

    loop = asyncio.get_event_loop()
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        # Extract flat playlist metadata (only URLs)
        logger.info(f"Started extracting playlist: {query}")
        playlist_info = await loop.run_in_executor(executor, ydl.extract_info, query, False)

    return playlist_info

async def extract_video_info_async(video_url: str):
    """Extracts details for an individual video."""
    ydl_opts = {
        'quiet': True,
        'format': 'bestaudio/best',
        'cachedir': False,
        'ignoreerrors': True,
        'retries': 5,
        'socket_timeout': 15
    }

    loop = asyncio.get_event_loop()
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        # Extract details for a single video
        logger.info(f"Extracting video: {video_url}")
        return await loop.run_in_executor(executor, ydl.extract_info, video_url, False)

@bot.tree.command()
@app_commands.describe(query="Provide a YouTube link (video or playlist)")
async def play(interaction: discord.Interaction, query: str):
    if not await is_dj_or_admin(interaction):
        await interaction.response.send_message("You need to be a DJ or admin to use this command.", ephemeral=True)
        return

    if interaction.user.voice is None:
        await interaction.response.send_message("You need to be in a voice channel to play music.", ephemeral=True)
        return
    
    guild_data = bot.get_guild_data(interaction.guild.id)

    voice_channel = interaction.user.voice.channel
    if not interaction.guild.voice_client:
        await voice_channel.connect()
    elif interaction.guild.voice_client.channel != voice_channel:
        await interaction.guild.voice_client.move_to(voice_channel)

    await interaction.response.defer(ephemeral=True)

    logger.info(f"Received query: {query}")

    try:
        # First, extract the list of video URLs (without full details)
        playlist_info = await extract_playlist_videos_async(query)

        if 'entries' in playlist_info:  # It's a playlist
            playlist_title = playlist_info.get('title', 'Unknown Playlist')
            await interaction.followup.send(f"Loading playlist: {playlist_title}...", ephemeral=True)

            first_song = None

            # Process each video individually by extracting full details
            for idx, entry in enumerate(playlist_info['entries']):
                if entry is None or not entry.get('url'):
                    logger.warning(f"Video at position {idx+1} in the playlist is unavailable and will be skipped.")
                    continue

                video_url = entry['url']
                video_info = await extract_video_info_async(video_url)  # Fetch full video details
                video_title = video_info.get('title', 'Unknown Title')

                pod_info = {
                    'name': video_title,
                    'url': video_info.get('url'),
                    'is_live': video_info.get('is_live', False)
                }

                guild_data['pod_queue'].append(pod_info)

                # Log each song added to the queue
                logger.info(f"Added {video_title} to the queue")

                # Update the queue message after each addition
                await update_queue_message(interaction)

                # Play the first song immediately if nothing is currently playing
                if idx == 0 and not guild_data['current_pod']:
                    guild_data['current_pod'] = pod_info
                    first_song = pod_info
                    await play_podcast(interaction)

            if first_song:
                await interaction.followup.send(f"Now playing: {first_song['name']}", ephemeral=True)
            else:
                await interaction.followup.send(f"Playlist {playlist_title} has been loaded into the queue.", ephemeral=True)

        else:  # Single video
            video_info = await extract_video_info_async(query)
            video_title = video_info.get('title', query)
            is_live = video_info.get('is_live', False)

            if not video_info.get('url'):
                await interaction.followup.send("Failed to extract video URL. Please check the link.", ephemeral=True)
                return

            pod_info = {
                'name': video_title,
                'url': video_info.get('url'),
                'is_live': is_live
            }

            if guild_data['current_pod']:
                guild_data['pod_queue'].append(pod_info)
                await interaction.followup.send(f"Added to queue: {pod_info['name']}", ephemeral=True)
            else:
                guild_data['current_pod'] = pod_info
                await play_podcast(interaction)

        await update_queue_message(interaction)

    except Exception as e:
        await interaction.followup.send(f"An error occurred - Check the bot logs.", ephemeral=True)
        logger.error(f"Error in play command: {e}")

@bot.tree.command()
async def pause(interaction: discord.Interaction):
    if not await is_dj_or_admin(interaction):
        await interaction.response.send_message("You need to be a DJ or admin to use this command.", ephemeral=True)
        return
    await pause_action(interaction)

@bot.tree.command()
async def resume(interaction: discord.Interaction):
    if not await is_dj_or_admin(interaction):
        await interaction.response.send_message("You need to be a DJ or admin to use this command.", ephemeral=True)
        return
    await resume_action(interaction)

@bot.tree.command()
async def stop(interaction: discord.Interaction):
    if not await is_dj_or_admin(interaction):
        await interaction.response.send_message("You need to be a DJ or admin to use this command.", ephemeral=True)
        return
    await stop_action(interaction)

@bot.tree.command()
async def skip(interaction: discord.Interaction):
    if not await is_dj_or_admin(interaction):
        await interaction.response.send_message("You need to be a DJ or admin to use this command.", ephemeral=True)
        return
    await skip_action(interaction)

@bot.tree.command()
async def clear_queue(interaction: discord.Interaction):
    if not await is_dj_or_admin(interaction):
        await interaction.response.send_message("You need to be a DJ or admin to use this command.", ephemeral=True)
        return
    guild_data = bot.get_guild_data(interaction.guild.id)
    guild_data['pod_queue'].clear()
    await interaction.response.send_message("Cleared the queue.", ephemeral=True)
    await update_queue_message(interaction)

@bot.tree.command()
async def refresh(interaction: discord.Interaction):
    """Command to delete and recreate the persistent queue message."""
    if not await is_dj_or_admin(interaction):
        await interaction.response.send_message("You need to be a DJ or admin to use this command.", ephemeral=True)
        return
    
    guild_data = bot.get_guild_data(interaction.guild.id)

    if guild_data['queue_message']:
        try:
            await guild_data['queue_message'].delete()
        except Exception as e:
            print(f"{bcolors.FAIL}Error deleting queue message: {e}{bcolors.DEFAULT}")
    
    guild_data['queue_message'] = None
    await update_queue_message(interaction)
    await interaction.response.send_message("The persistent queue message has been refreshed.", ephemeral=True)

@bot.tree.command()
@app_commands.describe(channel="The channel to set for bot operations")
async def set_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not await is_dj_or_admin(interaction):
        await interaction.response.send_message("You need to be a DJ or admin to use this command.", ephemeral=True)
        return

    guild_data = bot.get_guild_data(interaction.guild.id)

    # Clear messages in the old channel
    if guild_data['queue_message']:
        try:
            await guild_data['queue_message'].delete()
        except:
            pass  # In case the message was already deleted

    guild_data['assigned_channel_id'] = channel.id
    await interaction.response.send_message(f"The bot channel has been set to {channel.mention}.", ephemeral=True)
    
    # Update queue message in the new channel
    guild_data['queue_message'] = None
    await update_queue_message(interaction)

bot.run(DISCORD_BOT_TOKEN)

# def run_bot():
    # bot.run(DISCORD_BOT_TOKEN)
# def reload_bot():
#     print(f"{bcolors.OKBLUE}Reloading bot...{bcolors.DEFAULT}")
#     bot.close()
#     threading.Thread(target=run_bot).start()

# # Start the bot in a separate thread
# bot_thread = threading.Thread(target=run_bot)
# bot_thread.start()

# # Set up keyboard listener
# keyboard.add_hotkey('r', reload_bot)

# # Keep the main thread alive
# keyboard.wait('esc')  # Press 'esc' to exit the script entirely
