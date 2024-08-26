import os
import logging
from dotenv import load_dotenv
import yt_dlp

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

intents = discord.Intents.default()
intents.message_content = True

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
        self.pod_queue = []
        self.current_pod = None
        self.queue_message = None
        self.assigned_channel_id = None  # This will be set via command or loaded from .env

    async def setup_hook(self):
        await self.tree.sync()

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

    # @discord.ui.button(label='Skip', style=discord.ButtonStyle.primary, emoji='⏭️')
    # async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
    #     if not await is_dj_or_admin(interaction):
    #         await interaction.response.send_message("You need to be a DJ or admin to use this button.", ephemeral=True)
    #         return
    #     await skip_action(interaction)

    @discord.ui.button(label='Stop', style=discord.ButtonStyle.danger, emoji='⏹️')
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await is_dj_or_admin(interaction):
            await interaction.response.send_message("You need to be a DJ or admin to use this button.", ephemeral=True)
            return
        await stop_action(interaction)

@bot.event
async def on_ready():
    await bot.tree.sync() # sync /commands
    print(f'{bcolors.OKBLUE}Logged in as {bot.user}')
    # Load initial channel from .env if available
    channel_id = os.getenv('ASSIGNED_CHANNEL_ID')
    if channel_id:
        bot.assigned_channel_id = int(channel_id)

async def is_dj_or_admin(interaction: discord.Interaction) -> bool:
    if not hasattr(interaction, 'user'):
        # If interaction doesn't have user attribute, try to get the user from the member attribute
        user = getattr(interaction, 'member', None)
        if user is None:
            # If we can't get the user, assume they don't have permission
            return False
    else:
        user = interaction.user

    # Now use the user object for permission checking
    return user.guild_permissions.administrator or discord.utils.get(user.roles, name="DJ") is not None

def update_queue_message_content() -> str:
    """Generates the content for the persistent queue message."""
    now_playing = f"**Now Playing:** {bot.current_pod['name'] if bot.current_pod else 'Nothing'}"
    
    queue_content = "\n\n**Queue:**\n"
    if not bot.pod_queue:
        queue_content += "The queue is currently empty."
    else:
        for idx, pod in enumerate(bot.pod_queue, start=1):
            queue_content += f"{idx}. {pod['name']}\n"

    return now_playing + queue_content

async def update_queue_message(interaction: discord.Interaction):
    """Updates the persistent queue message or sends a new one if not exists."""
    if bot.assigned_channel_id:
        channel = bot.get_channel(bot.assigned_channel_id)
        if bot.queue_message:
            await bot.queue_message.edit(content=update_queue_message_content(), view=ControlButtons())
        else:
            bot.queue_message = await channel.send(content=update_queue_message_content(), view=ControlButtons())
    else:
        await interaction.response.send_message("No channel is set for the bot. Use the /set_channel command to set one.", ephemeral=True)

async def play_podcast(interaction: discord.Interaction):
    if not bot.current_pod:
        return

    is_live = bot.current_pod.get('is_live', False)
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': True,
        'noplaylist': True,  # Ensure it processes as a single video
        'cachedir': False
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(bot.current_pod['url'], download=False)
        url = info.get('url')

    if not url:
        await interaction.followup.send("Failed to play the current track.", ephemeral=True)
        return

    voice_client = interaction.guild.voice_client

    if is_live:
        voice_client.play(discord.FFmpegPCMAudio(url), after=lambda e: bot.loop.create_task(play_next(interaction)))
        await interaction.followup.send(f"Now playing (live): {bot.current_pod['name']}", ephemeral=True)
        print(f"{bcolors.OKCYAN}Now playing (live): {bcolors.OKMAGENTA}{bot.current_pod['name']}{bcolors.DEFAULT}")
    else:
        voice_client.play(discord.FFmpegPCMAudio(url), after=lambda e: bot.loop.create_task(play_next(interaction)))
        await interaction.followup.send(f"Now playing: {bcolors.OKMAGENTA}{bot.current_pod['name']}", ephemeral=True)
        print(f"{bcolors.OKCYAN}Now playing: {bot.current_pod['name']}{bcolors.DEFAULT}")
    
    # Update the queue message to show the new "Now Playing" status
    await update_queue_message(interaction)


async def play_next(interaction: discord.Interaction):
    if bot.pod_queue:
        bot.current_pod = bot.pod_queue.pop(0)
        await play_podcast(interaction)
        print(f"{bcolors.OKCYAN}Playing next track...")
    else:
        bot.current_pod = None
    await update_queue_message(interaction)

async def pause_action(interaction: discord.Interaction):
    if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
        interaction.guild.voice_client.pause()
        await interaction.response.send_message("Paused the playback.", ephemeral=True)
        print(f"{bcolors.OKGREEN} Track paused.{bcolors.DEFAULT}")
    else:
        await interaction.response.send_message("No audio is currently playing.", ephemeral=True)

async def resume_action(interaction: discord.Interaction):
    if interaction.guild.voice_client and interaction.guild.voice_client.is_paused():
        interaction.guild.voice_client.resume()
        await interaction.response.send_message("Resumed the playback.", ephemeral=True)
        print(f"{bcolors.OKGREEN} Track resumed.{bcolors.DEFAULT}")
    else:
        await interaction.response.send_message("No audio is paused.", ephemeral=True)

async def skip_action(interaction: discord.Interaction):
    if interaction.guild.voice_client and (interaction.guild.voice_client.is_playing() or interaction.guild.voice_client.is_paused()):
        interaction.guild.voice_client.stop()
        await interaction.response.send_message("Skipped the current track.", ephemeral=True)
        print(f"{bcolors.OKGREEN} Track skipped.{bcolors.DEFAULT}")
        await play_next(interaction)
    else:
        await interaction.response.send_message("No audio is currently playing.", ephemeral=True)

async def stop_action(interaction: discord.Interaction):
    if interaction.guild.voice_client:
        interaction.guild.voice_client.stop()
        await interaction.guild.voice_client.disconnect()
        bot.current_pod = None
        bot.pod_queue.clear()
        await interaction.response.send_message("Stopped the playback and cleared the queue.", ephemeral=True)
        print(f"{bcolors.OKGREEN} Playback stopped and queue cleared.{bcolors.DEFAULT}")
    else:
        await interaction.response.send_message("No audio is currently playing.", ephemeral=True)

@bot.tree.command()
@app_commands.describe(query="Provide a YouTube link")
async def play(interaction: discord.Interaction, query: str):
    if not await is_dj_or_admin(interaction):
        await interaction.response.send_message("You need to be a DJ or admin to use this command.", ephemeral=True)
        return

    if interaction.user.voice is None:
        await interaction.response.send_message("You need to be in a voice channel to play music.", ephemeral=True)
        return

    voice_channel = interaction.user.voice.channel
    if not interaction.guild.voice_client:
        await voice_channel.connect()
    elif interaction.guild.voice_client.channel != voice_channel:
        await interaction.guild.voice_client.move_to(voice_channel)

    await interaction.response.defer(ephemeral=True)

    print(f"{bcolors.OKCYAN}Received query: {bcolors.OKMAGENTA}{query}{bcolors.DEFAULT}")

    try:
        if 'youtube.com' in query or 'youtu.be' in query:
            ydl_opts = {
                'quiet': True,
                'format': 'bestaudio/best',
                'noplaylist': True,  # Ensure it processes as a single video
                'cachedir': False
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(query, download=False)

            is_live = info.get('is_live', False)
            video_url = info.get('url')
            video_title = info.get('title', query)  # Fetch the title or use the query if not found

            if not video_url:
                await interaction.followup.send("Failed to extract video URL. Please check the link.", ephemeral=True)
                print(f"{bcolors.OKWARNING}Failed to extract video URL. Invalid link.{bcolors.DEFAULT}")
                return

            pod_info = {
                'name': video_title,
                'url': video_url,
                'is_live': is_live
            }

            if bot.current_pod:
                bot.pod_queue.append(pod_info)
                await interaction.followup.send(f"Added to queue: {pod_info['name']}", ephemeral=True)
                print(f"{bcolors.OKCYAN}Added to queue: {bcolors.OKMAGENTA}{pod_info['name']}{bcolors.DEFAULT}")
            else:
                bot.current_pod = pod_info
                await play_podcast(interaction)

        else:
            await interaction.followup.send("Invalid URL. Please provide a valid YouTube link.", ephemeral=True)
            return

        await update_queue_message(interaction)

    except Exception as e:
        await interaction.followup.send(f"An error occurred: {str(e)}", ephemeral=True)
        print(f"{bcolors.FAIL}Error in play command: {e}{bcolors.DEFAULT}")

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
    bot.pod_queue.clear()
    await interaction.response.send_message("Cleared the queue.", ephemeral=True)
    await update_queue_message(interaction)

@bot.tree.command()
async def refresh(interaction: discord.Interaction):
    """Command to delete and recreate the persistent queue message."""
    if not await is_dj_or_admin(interaction):
        await interaction.response.send_message("You need to be a DJ or admin to use this command.", ephemeral=True)
        return
    
    if bot.queue_message:
        try:
            await bot.queue_message.delete()
        except Exception as e:
            print(f"{bcolors.FAIL}Error deleting queue message: {e}{bcolors.DEFAULT}")
    
    bot.queue_message = None
    await update_queue_message(interaction)
    await interaction.response.send_message("The persistent queue message has been refreshed.", ephemeral=True)
    print(f"{bcolors.OKBLUE}Queue message refreshed.{bcolors.DEFAULT}")

@bot.tree.command()
@app_commands.describe(channel="The channel to set for bot operations")
async def set_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not await is_dj_or_admin(interaction):
        await interaction.response.send_message("You need to be a DJ or admin to use this command.", ephemeral=True)
        return

    # Clear messages in the old channel
    if bot.queue_message:
        try:
            await bot.queue_message.delete()
        except:
            pass  # In case the message was already deleted

    bot.assigned_channel_id = channel.id
    await interaction.response.send_message(f"The bot channel has been set to {channel.mention}.", ephemeral=True)
    print(f"{bcolors.OKBLUE}The bot channel has been set to {bcolors.OKMAGENTA}{channel.mention}.{bcolors.DEFAULT}")
    
    # Update queue message in the new channel
    bot.queue_message = None
    await update_queue_message(interaction)

bot.run(DISCORD_BOT_TOKEN)
