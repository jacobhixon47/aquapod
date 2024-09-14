# Aquapod 🪼

Aquapod is a Discord bot built in Python that allows users to play and manage a queue of podcasts or music from YouTube links. The bot can extract playlists, load videos into the queue, and provide persistent controls to pause, skip, and stop playback.

## Features

-   Play YouTube playlists or individual videos
-   Persistent queue management with control buttons for pause, resume, skip, and stop
-   Asynchronous playlist extraction and queuing
-   Multiple guild (server) support with separate queues for each guild
-   Ability to set a dedicated channel for queue and control operations
-   Commands restricted to DJ role or Admins

## Technologies Used

🐍[Python 3.8+](https://www.python.org/downloads/release/python-380/) - _Core programming language_

🖊️[Poetry](https://python-poetry.org/) - _Dependency and environment management_

👾[discord.py](https://github.com/Rapptz/discord.py) - _Library to interact with the Discord API_

📩[yt-dlp](https://github.com/yt-dlp/yt-dlp) - _For extracting YouTube video information_

Ⓜ️[FFmpeg](https://ffmpeg.org/documentation.html) - _Audio processing for playback_

## Requirements

-   Python 3.8+
-   `yt-dlp` for extracting media information from YouTube
-   `discord.py` for interfacing with Discord
-   `poetry` for dependency management
-   FFMPEG installed on the system for audio playback

## Installation

1. Clone the repository:

    ```bash
    git clone https://github.com/jacobhixon47/aquapod.git
    cd aquapod
    ```

2. Install dependencies using Poetry:

    ```bash
    poetry install
    ```

3. Create a `.env` file in the root directory - use the `.env.template` file for reference.  
   Be sure to add your Discord bot token:

    ```bash
    DISCORD_BOT_TOKEN=your_token_here
    SHOULD_SYNC=false   # Set to true if you want the bot to sync commands on start.
                        # Note: This is labor-intensive and can delay the bot startup,
                        # which is why it should be set to false by default.
    ```

4. Ensure `FFmpeg` is installed and available on your system.

## Running the Bot

1. Run the bot using Poetry from the root directory:

    ```bash
    poetry run python aquapod/main.py
    ```

    Or by entering the subdirectory:

    ```bash
    cd aquapod && poetry run python main.py
    ```

2. The bot will start and automatically sync commands if `SHOULD_SYNC` is set to `true` in the `.env` file.

## Commands

### `/play [YouTube URL]`

Loads a YouTube playlist or individual video into the queue and starts playing immediately if nothing is currently playing.

### `/pause`

Pauses the current playback.

### `/resume`

Resumes playback if paused.

### `/skip`

Skips the current track and moves to the next one in the queue.

### `/stop`

Stops the playback, clears the queue, and disconnects the bot from the voice channel.

### `/clear_queue`

Clears the current queue of tracks.

### `/refresh`

Deletes and recreates the persistent queue message in the assigned channel.

### `/set_channel [channel]`

Sets a specific channel for queue messages and control buttons. Deletes the old queue message and moves operations to the new channel.

## Usage Notes

-   The bot requires the user have the `DJ` role or administrator privileges to use the commands.  
    _Note: You can change this in the `is_dj_or_admin()` function on line ~132:_  
    `return user.guild_permissions.administrator or discord.utils.get(user.roles, name="DJ") is not None`

-   The bot will look for a channel named `#aquapod-controller` by default and create a persistent queue message there. You can change the channel using the `/set_channel` command.
-   The bot logs its activity to `discord.log` in the root directory for debugging purposes.

## Contributing

Feel free to open issues or submit pull requests for improvements or bug fixes!

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
