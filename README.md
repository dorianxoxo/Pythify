# Pythify - A Lightweight Spotify Desktop Client

## Overview
Pythify is a Python-based music streaming and downloading application with Spotify authentication, YouTube audio extraction, and VLC-powered playback. It features a user-friendly PyQt6 GUI, allowing users to search, play, and download music tracks.

⚠ **Note:** This project is still under development. It is known to have bugs and may crash unexpectedly.

🚨 **VLC Error Notice:** If you encounter any errors related to VLC, ensure that you have installed the 64-bit version from the official website: [Download VLC (64-bit)](https://www.videolan.org/vlc/)

⚠ **Albums Section Notice:** The albums section is currently not working and will be fixed in a future update.

⚠ **Legal Disclaimer:** This application is intended for personal and legal use only. The developer is not responsible for any misuse of the software, including but not limited to copyright infringement or illegal downloading of copyrighted content. Users are responsible for ensuring compliance with applicable laws in their country.

## Features
- **Spotify Integration**: Authenticate and access your Spotify library, playlists, and liked songs.
- **YouTube Streaming**: Search and play music from YouTube.
- **Music Downloads**: Download tracks and store them locally.
- **Shuffle and Loop**: Toggle shuffle or loop functionality.


## Installation
### Requirements
- Python 3.8+
- Required Python packages:
  ```sh
  pip install PyQt6 requests yt_dlp spotipy vlc
  ```
- VLC media player installed on your system.

## How to Sign In to Spotify
1. Open the application.
2. Click on the **Account** menu and select **Login to Spotify**.
3. Enter your Spotify **Client ID**, **Client Secret**, and **Redirect URI** (default: `http://localhost:8888/callback`).
4. Click **OK** and follow the authentication flow.
5. Once authenticated, your Spotify username will appear at the top.

## How It Works
### Searching for Music
1. Enter a song title or artist in the search bar and press **Enter**.
2. Search results will appear in the table.
3. Click the play button next to a song to start playback.

### Managing Playback
- **Play/Pause**: Click the play button.
- **Skip/Previous**: Use the next and previous buttons.
- **Adjust Volume**: Use the volume slider.
- **Shuffle & Loop**: Toggle shuffle or loop modes.

### Downloading Songs
1. Right-click on a song in the table.
2. Select **Download Track**.
3. The download progress will be shown in a dialog.

### Viewing Downloaded Tracks
1. Click **Library** > **Downloaded** in the sidebar.
2. All downloaded tracks will be displayed.
3. Click a track to play it locally.

## Contributing
Feel free to submit pull requests and report issues on GitHub.

## License
This project is licensed under the MIT License.

