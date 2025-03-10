# Import necessary Python standard libraries
import sys
import os
import json
import webbrowser
import vlc
import threading
from datetime import datetime, timedelta
import shutil
import time
import random  # Added for shuffle functionality

# Import PyQt6 modules for GUI creation
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                            QLabel, QPushButton, QListWidget, QLineEdit, QSlider, QTableWidget, 
                            QTableWidgetItem, QHeaderView, QSplitter, QDialog, QDialogButtonBox, 
                            QFormLayout, QMessageBox, QMenuBar, QAbstractItemView, QProgressDialog, 
                            QProgressBar, QMenu)
from PyQt6.QtGui import QIcon, QPixmap, QFont, QAction
from PyQt6.QtCore import Qt, QSize, QTimer, pyqtSignal, QUrl, QMetaObject, Q_ARG, pyqtSlot, QThread

# Import external libraries for web requests and YouTube downloading
import requests
import yt_dlp

# Try to import Spotify-related libraries, exit if not installed
try:
    import spotipy
    from spotipy.oauth2 import SpotifyOAuth
except ImportError:
    print("Spotipy not installed. Please install it using: pip install spotipy")
    sys.exit(1)

# In-memory cache for stream URLs and Spotify data
STREAM_CACHE = {}
SPOTIFY_CACHE = {}
CACHE_FILE = "stream_cache.json"
SPOTIFY_CACHE_FILE = "spotify_cache.json"
CACHE_EXPIRY_DAYS = 7  # Cache entries expire after 7 days
DOWNLOAD_FOLDER = "Downloaded"

# Load stream cache from file if it exists
def load_stream_cache():
    global STREAM_CACHE
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r') as f:
                cached_data = json.load(f)
                now = datetime.now()
                STREAM_CACHE = {
                    key: value for key, value in cached_data.items()
                    if datetime.fromisoformat(value['timestamp']) + timedelta(days=CACHE_EXPIRY_DAYS) > now
                }
        except Exception as e:
            print(f"Error loading stream cache: {str(e)}")
            STREAM_CACHE = {}

# Save stream cache to file
def save_stream_cache():
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump(STREAM_CACHE, f)
    except Exception as e:
        print(f"Error saving stream cache: {str(e)}")

# Load Spotify cache from file if it exists
def load_spotify_cache():
    global SPOTIFY_CACHE
    if os.path.exists(SPOTIFY_CACHE_FILE):
        try:
            with open(SPOTIFY_CACHE_FILE, 'r') as f:
                cached_data = json.load(f)
                now = datetime.now()
                SPOTIFY_CACHE = {
                    key: value for key, value in cached_data.items()
                    if datetime.fromisoformat(value['timestamp']) + timedelta(days=CACHE_EXPIRY_DAYS) > now
                }
        except Exception as e:
            print(f"Error loading Spotify cache: {str(e)}")
            SPOTIFY_CACHE = {}

# Save Spotify cache to file
def save_spotify_cache():
    try:
        with open(SPOTIFY_CACHE_FILE, 'w') as f:
            json.dump(SPOTIFY_CACHE, f)
    except Exception as e:
        print(f"Error saving Spotify cache: {str(e)}")

# Ensure download folder exists
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

# Define a dialog for Spotify authentication
class SpotifyAuthDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Spotify Login")
        self.resize(400, 200)
        
        layout = QFormLayout(self)
        self.client_id_input = QLineEdit()
        self.client_secret_input = QLineEdit()
        self.client_secret_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.redirect_uri_input = QLineEdit("http://localhost:8888/callback")
        
        layout.addRow("Client ID:", self.client_id_input)
        layout.addRow("Client Secret:", self.client_secret_input)
        layout.addRow("Redirect URI:", self.redirect_uri_input)
        
        note_label = QLabel("Get your credentials from the Spotify Developer Dashboard")
        note_label.setStyleSheet("color: #b3b3b3; font-size: 10px;")
        layout.addRow(note_label)
        
        dashboard_button = QPushButton("Open Spotify Developer Dashboard")
        dashboard_button.clicked.connect(lambda: webbrowser.open("https://developer.spotify.com/dashboard/"))
        layout.addRow(dashboard_button)
        
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addRow(button_box)
    
    def get_credentials(self):
        return {
            "client_id": self.client_id_input.text(),
            "client_secret": self.client_secret_input.text(),
            "redirect_uri": self.redirect_uri_input.text()
        }

# Define a dialog to show the queue
class QueueDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Current Queue")
        self.resize(400, 300)
        
        layout = QVBoxLayout(self)
        
        self.queue_list = QListWidget()
        self.queue_list.setStyleSheet("""
            QListWidget { border: 1px solid #333; border-radius: 5px; background-color: #1a1a1a; }
            QListWidget::item { padding: 5px; color: #ffffff; }
            QListWidget::item:selected { background-color: #2a2a2a; color: #1DB954; }
        """)
        
        layout.addWidget(self.queue_list)
        
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def update_queue(self, queue):
        self.queue_list.clear()
        for i, track in enumerate(queue, 1):
            title = track["title"]
            artist = track["artist"]
            self.queue_list.addItem(f"{i}. {title} - {artist}")

# Define a dialog to show download progress
class DownloadProgressDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Downloading Tracks")
        self.setMinimumSize(300, 100)
        
        layout = QVBoxLayout(self)
        
        self.current_track_label = QLabel("Preparing to download...")
        self.current_track_label.setStyleSheet("color: #ffffff;")
        layout.addWidget(self.current_track_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #333;
                border-radius: 5px;
                background-color: #2a2a2a;
                text-align: center;
                color: #ffffff;
            }
            QProgressBar::chunk {
                background-color: #1DB954;
                border-radius: 5px;
            }
        """)
        layout.addWidget(self.progress_bar)
        
        self.setStyleSheet("background-color: #1a1a1a;")
        self.move(100, 100)  # Set a default position to ensure visibility

    def update_progress(self, current_track, progress):
        self.current_track_label.setText(f"Downloading: {current_track}")
        self.progress_bar.setValue(progress)

# Define a worker thread for downloading tracks
class DownloadWorker(QThread):
    progress_updated = pyqtSignal(str, int)  # Signal for progress updates (track name, percentage)
    download_finished = pyqtSignal(str, bool)  # Signal for download completion (track name, success)

    def __init__(self, title, artist, download_folder):
        super().__init__()
        self.title = title
        self.artist = artist
        self.download_folder = download_folder
        self.vlc_instance = None
        self.vlc_player = None
        self.cancelled = False

    def run(self):
        try:
            # Sanitize filename
            invalid_chars = '<>:"/\\|?*'
            title = self.title
            artist = self.artist
            for char in invalid_chars:
                title = title.replace(char, '')
                artist = artist.replace(char, '')
            output_file = os.path.join(self.download_folder, f"{title} - {artist}.mp3")

            # Fetch stream URL
            stream_url = self.fetch_youtube_stream(title, artist)
            if not stream_url or self.cancelled:
                self.download_finished.emit(f"{title} - {artist}", False)
                return

            # Initialize VLC instance
            self.vlc_instance = vlc.Instance('--no-video', '--network-caching=1000')
            self.vlc_player = self.vlc_instance.media_player_new()

            # Set up media with stream output for MP3 transcoding
            sout = f'#transcode{{acodec=mp3,ab=192,channels=2}}:std{{access=file,mux=mp3,dst="{output_file}"}}'
            media = self.vlc_instance.media_new(stream_url, f"sout={sout}")
            self.vlc_player.set_media(media)

            # Start downloading
            self.vlc_player.play()
            start_time = time.time()

            # Monitor progress
            while self.vlc_player.get_state() not in [vlc.State.Ended, vlc.State.Error] and not self.cancelled:
                duration = self.vlc_player.get_length()
                position = self.vlc_player.get_time()
                if duration > 0:
                    progress = min(99, int((position / duration) * 100))
                else:
                    elapsed = time.time() - start_time
                    estimated_duration = 300  # 5-minute estimate
                    progress = min(99, int((elapsed / estimated_duration) * 100))
                self.progress_updated.emit(f"{title} - {artist}", progress)
                time.sleep(1)

            # Check final state
            if self.vlc_player.get_state() == vlc.State.Ended and os.path.exists(output_file):
                self.progress_updated.emit(f"{title} - {artist}", 100)
                self.download_finished.emit(f"{title} - {artist}", True)
            else:
                self.download_finished.emit(f"{title} - {artist}", False)

        except Exception as e:
            print(f"Download error for {self.title} - {self.artist}: {str(e)}")
            self.download_finished.emit(f"{self.title} - {self.artist}", False)

        finally:
            # Clean up VLC resources
            if self.vlc_player:
                self.vlc_player.stop()
                self.vlc_player.release()
            if self.vlc_instance:
                self.vlc_instance.release()

    def fetch_youtube_stream(self, title, artist):
        cache_key = f"{title.lower()} - {artist.lower()}"
        if cache_key in STREAM_CACHE:
            return STREAM_CACHE[cache_key]['url']
        
        query = f"{title} {artist} official audio"
        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'noplaylist': True,
            'no_progress': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(f"ytsearch:{query}", download=False)
                stream_url = info['entries'][0]['url']
                STREAM_CACHE[cache_key] = {
                    'url': stream_url,
                    'timestamp': datetime.now().isoformat()
                }
                save_stream_cache()
                return stream_url
            except Exception as e:
                print(f"Error fetching YouTube stream: {str(e)}")
                return None

    def cancel(self):
        self.cancelled = True
        if self.vlc_player:
            self.vlc_player.stop()

# Define the main application window
class SpotifyMusicPlayer(QMainWindow):
    def __init__(self):
        super().__init__()
        # Set VLC plugin path relative to the executable
        if getattr(sys, 'frozen', False):  # Check if running as PyInstaller bundle
            base_path = os.path.dirname(sys.executable)
            vlc_plugin_path = os.path.join(base_path, 'vlc', 'plugins')
            os.environ['VLC_PLUGIN_PATH'] = vlc_plugin_path
        self.initialize_vlc()
    auth_complete = pyqtSignal()
    search_complete = pyqtSignal(list, int)  # Signal for search results and total fetched
    loading_started = pyqtSignal(str, str)  # Signal for loading state with title and image URL

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pythify")
        self.setMinimumSize(1000, 600)
        
        # Load caches at startup
        load_stream_cache()
        load_spotify_cache()
        
        # Initialize core attributes
        self.sp = None
        self.user_profile = None
        self.initialize_vlc()  # Initialize VLC safely
        self.current_track = None
        self.track_queue = []
        self.loading_thread = None
        self.cancel_loading = False
        self.current_stream_url = None
        self.is_playing = False
        self.is_local_track = False  # Flag to track if current track is local
        self.current_track_index = -1
        self.queue_dialog = None
        self.current_playlist_tracks = []  # Store the current playlist tracks
        self.search_thread = None  # For async search
        self.current_search_query = ""  # To track the current search query
        self.all_search_results = []  # Store all search results
        self.current_page = 1  # Track current page (1 to 10)
        self.max_pages = 10  # Maximum number of pages
        self.download_progress_dialog = None  # For download progress
        self.download_queue = []  # Queue for tracks to download
        self.current_download_worker = None  # Current download thread
        self.is_looping = False  # Added for loop functionality
        self.is_shuffling = False  # Added for shuffle functionality
        self.current_library_selection = None  # Track current library selection
        self.current_playlist_selection = None  # Track current playlist selection

        # Set up event manager for VLC to detect end of media
        self.event_manager = self.vlc_player.event_manager()
        self.event_manager.event_attach(vlc.EventType.MediaPlayerEndReached, self.on_vlc_event)
        
        # Create menu bar with authentication option
        menubar = self.menuBar()
        auth_menu = menubar.addMenu("Account")
        self.auth_action = QAction("Login to Spotify", self)
        self.auth_action.triggered.connect(self.authenticate_spotify)
        auth_menu.addAction(self.auth_action)
        
        # Set up the central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Sidebar setup
        self.sidebar = QWidget()
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(10, 10, 10, 10)
        
        library_label = QLabel("Library")
        library_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        library_label.setStyleSheet("color: #ffffff;")
        self.library_list = QListWidget()
        library_items = ["Liked Music", "Albums", "Artists", "Downloaded"]
        for item in library_items:
            self.library_list.addItem(item)
        self.library_list.setStyleSheet("""
            QListWidget { border: none; background-color: #1a1a1a; color: #ffffff; }
            QListWidget::item { padding: 4px; border-radius: 4px; color: #ffffff; }
            QListWidget::item:selected { background-color: #2a2a2a; color: #1DB954; }
        """)
        
        playlists_label = QLabel("Playlists")
        playlists_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        playlists_label.setStyleSheet("color: #ffffff;")
        playlists_label.setContentsMargins(0, 15, 0, 0)
        self.playlist_list = QListWidget()
        self.playlist_list.addItem("Loading playlists...")
        self.playlist_list.itemClicked.connect(self.on_playlist_item_clicked)
        self.playlist_list.setMinimumHeight(400)
        self.playlist_list.setWordWrap(True)
        self.playlist_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.playlist_list.setStyleSheet("""
            QListWidget { border: none; background-color: #1a1a1a; color: #ffffff; }
            QListWidget::item { padding: 4px; border-radius: 4px; color: #ffffff; }
            QListWidget::item:selected { background-color: #2a2a2a; color: #1DB954; }
        """)
        
        sidebar_layout.addWidget(library_label)
        sidebar_layout.addWidget(self.library_list)
        sidebar_layout.addWidget(playlists_label)
        sidebar_layout.addWidget(self.playlist_list)
        sidebar_layout.addStretch()
        
        # Content area setup
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        
        self.user_bar = QWidget()
        user_layout = QHBoxLayout(self.user_bar)
        user_layout.setContentsMargins(10, 10, 10, 10)
        
        self.user_label = QLabel("Not logged in")
        self.user_label.setStyleSheet("color: #b3b3b3;")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search Music")
        self.search_input.setFixedHeight(30)
        self.search_input.setMaxLength(32767)
        self.search_input.returnPressed.connect(self.start_search)
        self.search_input.setStyleSheet("""
            QLineEdit { border: 1px solid #333; border-radius: 15px; padding: 5px 10px; color: #ffffff; background-color: #2a2a2a; }
        """)
        
        user_layout.addWidget(self.user_label)
        user_layout.addStretch()
        user_layout.addWidget(self.search_input)
        
        self.content_table = QTableWidget(0, 5)  # Added one column for play button
        self.content_table.setHorizontalHeaderLabels(["Title", "Artist", "Album", "Duration", ""])
        self.content_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.content_table.verticalHeader().setVisible(False)
        self.content_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.content_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)  # Enable multi-selection
        self.content_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # Adjust play button column
        self.content_table.setStyleSheet("""
            QTableWidget { border: none; gridline-color: #333; color: #ffffff; background-color: #1a1a1a; }
            QTableWidget::item { padding: 5px; color: #ffffff; }
            QHeaderView::section { background-color: #2a2a2a; border: none; padding: 5px; font-weight: bold; color: #ffffff; }
        """)
        self.content_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.content_table.customContextMenuRequested.connect(self.show_context_menu)
        
        # Pagination buttons
        self.page_layout = QHBoxLayout()
        self.page_buttons = []
        for i in range(1, self.max_pages + 1):
            button = QPushButton(str(i))
            button.setFixedSize(30, 30)  # Smaller buttons
            button.setStyleSheet("""
                QPushButton { 
                    background-color: transparent; 
                    border: 1px solid #1DB954; 
                    border-radius: 15px; 
                    padding: 2px; 
                    color: #1DB954; 
                    font-size: 12px;
                }
                QPushButton:hover { background-color: #333; }
                QPushButton:checked { background-color: #1DB954; color: #ffffff; }
            """)
            button.setCheckable(True)
            button.clicked.connect(lambda checked, page=i: self.change_page(page))
            self.page_buttons.append(button)
            self.page_layout.addWidget(button)
        self.page_layout.addStretch()
        self.page_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Ensure pagination buttons are at the bottom and initially hidden
        self.page_widget = QWidget()
        self.page_widget.setLayout(self.page_layout)
        self.page_widget.setVisible(False)  # Hide by default
        
        # Ensure content table stretches and pagination stays at bottom
        content_layout.addWidget(self.user_bar)
        content_layout.addWidget(self.content_table, 1)  # Stretch factor to fill space
        content_layout.addWidget(self.page_widget)
        
        # Playback controls setup
        control_bar = QWidget()
        control_bar.setFixedHeight(90)
        control_bar.setStyleSheet("background-color: #2a2a2a;")
        control_layout = QHBoxLayout(control_bar)
        
        self.album_art = QLabel()
        self.album_art.setFixedSize(80, 80)
        self.album_art.setStyleSheet("background-color: #333;")
        
        playback_controls = QWidget()
        playback_layout = QVBoxLayout(playback_controls)
        
        buttons_widget = QWidget()
        buttons_layout = QHBoxLayout(buttons_widget)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        
        # Shuffle button with label
        self.shuffle_button = QPushButton("")
        self.shuffle_button.setCheckable(True)
        self.shuffle_button.clicked.connect(self.toggle_shuffle)
        self.shuffle_button.setStyleSheet("""
            QPushButton { 
                background-color: transparent; 
                border: 1px solid #ffffff; 
                border-radius: 5px; 
                padding: 2px 5px; 
                font-size: 12px; 
                color: #ffffff; 
                min-width: 20px; 
            }
            QPushButton:hover { background-color: #333; }
            QPushButton:checked { background-color: #1DB954; color: #ffffff; }
        """)
        shuffle_label = QLabel("Shuffle")
        shuffle_label.setStyleSheet("color: #ffffff; font-size: 12px;")
        
        self.prev_button = QPushButton("◀◀")
        self.play_button = QPushButton("▶")
        self.next_button = QPushButton("▶▶")
        
        # Loop button with label
        self.loop_button = QPushButton("")
        self.loop_button.setCheckable(True)
        self.loop_button.clicked.connect(self.toggle_loop)
        self.loop_button.setStyleSheet("""
            QPushButton { 
                background-color: transparent; 
                border: 1px solid #ffffff; 
                border-radius: 5px; 
                padding: 2px 5px; 
                font-size: 12px; 
                color: #ffffff; 
                min-width: 20px; 
            }
            QPushButton:hover { background-color: #333; }
            QPushButton:checked { background-color: #1DB954; color: #ffffff; }
        """)
        loop_label = QLabel("Loop")
        loop_label.setStyleSheet("color: #ffffff; font-size: 12px;")
        
        self.queue_button = QPushButton("Queue")
        
        self.prev_button.clicked.connect(self.play_previous)
        self.play_button.clicked.connect(self.toggle_playback)
        self.next_button.clicked.connect(self.play_next)
        self.queue_button.clicked.connect(self.show_queue_dialog)
        
        self.prev_button.setStyleSheet("""
            QPushButton { background-color: transparent; border: none; border-radius: 15px; padding: 5px; font-size: 16px; color: #ffffff; }
            QPushButton:hover { background-color: #333; }
        """)
        self.play_button.setStyleSheet("""
            QPushButton { background-color: transparent; border: none; border-radius: 15px; padding: 5px; font-size: 16px; color: #ffffff; }
            QPushButton:hover { background-color: #333; }
        """)
        self.next_button.setStyleSheet("""
            QPushButton { background-color: transparent; border: none; border-radius: 15px; padding: 5px; font-size: 16px; color: #ffffff; }
            QPushButton:hover { background-color: #333; }
        """)
        self.queue_button.setStyleSheet("""
            QPushButton { background-color: transparent; border: none; border-radius: 15px; padding: 5px; font-size: 16px; color: #ffffff; }
            QPushButton:hover { background-color: #333; }
        """)
        
        buttons_layout.addStretch()
        buttons_layout.addWidget(self.shuffle_button)
        buttons_layout.addWidget(shuffle_label)
        buttons_layout.addWidget(self.prev_button)
        buttons_layout.addWidget(self.play_button)
        buttons_layout.addWidget(self.next_button)
        buttons_layout.addWidget(self.loop_button)
        buttons_layout.addWidget(loop_label)
        buttons_layout.addWidget(self.queue_button)
        buttons_layout.addStretch()
        
        slider_widget = QWidget()
        slider_layout = QHBoxLayout(slider_widget)
        slider_layout.setContentsMargins(0, 0, 0, 0)
        
        self.track_position_slider = QSlider(Qt.Orientation.Horizontal)
        self.track_position_slider.setRange(0, 0)
        self.track_position_slider.setEnabled(False)
        self.track_position_slider.sliderPressed.connect(self.slider_pressed)
        self.track_position_slider.sliderMoved.connect(self.slider_moved)
        self.track_position_slider.sliderReleased.connect(self.slider_released)
        self.track_position_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 6px;
                background: #555;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: #1DB954;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #1DB954;
                border: 2px solid #2a2a2a;
                width: 16px;
                height: 16px;
                margin: -5px 0;
                border-radius: 8px;
            }
            QSlider::handle:horizontal:hover {
                background: #179645;
            }
        """)
        slider_layout.addWidget(self.track_position_slider)
        
        playback_layout.addWidget(buttons_widget)
        playback_layout.addWidget(slider_widget)
        
        song_info = QWidget()
        song_layout = QVBoxLayout(song_info)
        song_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        
        self.song_title = QLabel("Not Playing")
        self.song_title.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        self.song_title.setStyleSheet("color: #ffffff;")
        self.artist_name = QLabel("")
        self.artist_name.setFont(QFont("Arial", 9))
        self.artist_name.setStyleSheet("color: #b3b3b3;")
        
        song_layout.addWidget(self.song_title)
        song_layout.addWidget(self.artist_name)
        
        volume_widget = QWidget()
        volume_layout = QHBoxLayout(volume_widget)
        
        volume_icon = QLabel("🔊")
        volume_icon.setStyleSheet("color: #ffffff;")
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setFixedWidth(100)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(50)
        self.volume_slider.valueChanged.connect(self.set_volume)
        self.volume_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 6px;
                background: #555;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: #1DB954;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #1DB954;
                border: 2px solid #2a2a2a;
                width: 16px;
                height: 16px;
                margin: -5px 0;
                border-radius: 8px;
            }
            QSlider::handle:horizontal:hover {
                background: #179645;
            }
        """)
        
        volume_layout.addWidget(volume_icon)
        volume_layout.addWidget(self.volume_slider)
        
        control_layout.addWidget(self.album_art)
        control_layout.addWidget(song_info)
        control_layout.addWidget(playback_controls, 1)
        control_layout.addWidget(volume_widget)
        
        # Add sidebar and content to splitter
        splitter.addWidget(self.sidebar)
        splitter.addWidget(content_widget)
        splitter.setSizes([300, 700])  # Set initial sizes for sidebar and content
        
        main_layout.addWidget(splitter)
        main_layout.addWidget(control_bar)
        
        self.auth_complete.connect(self.on_authentication_complete)
        self.search_complete.connect(self.on_search_complete)  # Connect search signal
        self.loading_started.connect(self.on_loading_started)  # Connect loading signal
        self.check_saved_credentials()
        
        self.library_list.itemClicked.connect(self.on_library_item_clicked)
        
        self.playback_timer = QTimer()
        self.playback_timer.timeout.connect(self.update_playback_progress)
        self.playback_timer.start(1000)

    def initialize_vlc(self):
        self.vlc_instance = vlc.Instance('--no-video', '--network-caching=1000')
        self.vlc_player = self.vlc_instance.media_player_new()
        """Initialize or reinitialize VLC instance and player."""
        if hasattr(self, 'vlc_player') and self.vlc_player:
            self.vlc_player.stop()
            self.vlc_player.release()
        if hasattr(self, 'vlc_instance') and self.vlc_instance:
            self.vlc_instance.release()
        
        self.vlc_instance = vlc.Instance('--no-video', '--network-caching=1000')
        self.vlc_player = self.vlc_instance.media_player_new()

    def fetch_youtube_stream(self, title, artist):
        cache_key = f"{title.lower()} - {artist.lower()}"
        if cache_key in STREAM_CACHE:
            print(f"Using cached stream URL for {title} - {artist}")
            # Test the cached URL
            try:
                response = requests.head(STREAM_CACHE[cache_key]['url'], timeout=5)
                if response.status_code == 403:
                    print(f"Cached URL for {title} - {artist} returned 403, refreshing...")
                    del STREAM_CACHE[cache_key]
                    save_stream_cache()
                else:
                    return STREAM_CACHE[cache_key]['url']
            except requests.RequestException as e:
                print(f"Error checking cached URL for {title} - {artist}: {str(e)}")
                del STREAM_CACHE[cache_key]
                save_stream_cache()
        
        query = f"{title} {artist} official audio"
        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'noplaylist': True,
            'no_progress': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                if self.cancel_loading:
                    return None
                info = ydl.extract_info(f"ytsearch:{query}", download=False)
                if self.cancel_loading:
                    return None
                stream_url = info['entries'][0]['url']
                STREAM_CACHE[cache_key] = {
                    'url': stream_url,
                    'timestamp': datetime.now().isoformat()
                }
                save_stream_cache()
                return stream_url
            except Exception as e:
                print(f"Error fetching YouTube stream: {str(e)}")
                return None

    def load_track_async(self, track_info):
        self.cancel_loading = True
        if self.loading_thread and self.loading_thread.is_alive():
            self.loading_thread.join(timeout=1)
        self.cancel_loading = False
        self.vlc_player.stop()
        self.loading_started.emit(track_info["title"], track_info.get("image_url", ""))
        self.loading_thread = threading.Thread(target=self._load_track, args=(track_info,))
        self.loading_thread.daemon = True
        self.loading_thread.start()

    def _load_track(self, track_info):
        title = track_info["title"]
        artist = track_info["artist"]
        image_url = track_info.get("image_url", "")
        stream_url = self.fetch_youtube_stream(title, artist)
        if stream_url and not self.cancel_loading:
            QMetaObject.invokeMethod(
                self,
                "play_track",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(str, stream_url),
                Q_ARG(str, title),
                Q_ARG(str, artist),
                Q_ARG(str, image_url)
            )
        else:
            QMetaObject.invokeMethod(
                self,
                "loading_failed",
                Qt.ConnectionType.QueuedConnection
            )

    @pyqtSlot(str, str, str, str)
    def play_track(self, stream_url, title, artist, image_url):
        self.vlc_player.stop()
        self.current_stream_url = stream_url  # Set stream URL for streamed tracks
        self.is_local_track = False  # Mark as streamed
        media = self.vlc_instance.media_new(stream_url)
        media.get_mrl()
        self.vlc_player.set_media(media)
        if self.vlc_player.play() == -1:  # Check if play fails
            print(f"Failed to play {title} - {artist}. Reinitializing VLC.")
            self.initialize_vlc()
            media = self.vlc_instance.media_new(stream_url)
            self.vlc_player.set_media(media)
            self.vlc_player.play()
        self.song_title.setText(title)
        self.artist_name.setText(artist)
        self.current_track = {"title": title, "artist": artist, "image_url": image_url}
        
        # Update queue dynamically based on current context
        self.update_queue_from_context()
        if self.current_track not in self.track_queue:
            self.track_queue.append(self.current_track)
        self.current_track_index = self.track_queue.index(self.current_track)
            
        self.load_thumbnail(image_url)
        self.set_volume(self.volume_slider.value())
        self.play_button.setText("⏸")
        self.is_playing = True
        self.duration_timer = QTimer()
        self.duration_timer.timeout.connect(self.update_duration)
        self.duration_timer.start(500)
        self.update_queue_display()

    @pyqtSlot(str, str)
    def on_loading_started(self, title, image_url):
        self.song_title.setText(f"Loading: {title}")
        self.artist_name.setText("")
        self.load_thumbnail(image_url)

    def loading_failed(self):
        self.song_title.setText("Loading Failed")
        self.artist_name.setText("")
        self.album_art.setStyleSheet("background-color: #333;")
        self.is_playing = False
        self.play_button.setText("▶")
        self.track_position_slider.setValue(0)
        self.track_position_slider.setEnabled(False)
        if self.track_queue:
            self.track_queue.pop(self.current_track_index)
            self.current_track_index = max(0, min(self.current_track_index, len(self.track_queue) - 1))
            if self.track_queue:
                self.load_track_async(self.track_queue[self.current_track_index])
            else:
                self.reset_playback()
        self.update_queue_display()

    def load_thumbnail(self, url):
        if not url:
            self.album_art.setStyleSheet("background-color: #333;")
            return
        try:
            response = requests.get(url)
            pixmap = QPixmap()
            pixmap.loadFromData(response.content)
            self.album_art.setPixmap(pixmap.scaled(80, 80, Qt.AspectRatioMode.KeepAspectRatio))
        except Exception as e:
            print(f"Error loading thumbnail: {str(e)}")
            self.album_art.setStyleSheet("background-color: #333;")

    def play_from_button(self, row):
        title = self.content_table.item(row, 0).text()
        artist = self.content_table.item(row, 1).text()
        image_url = ""
        if self.sp:
            try:
                results = self.sp.search(q=f"{title} {artist}", type="track", limit=1)
                if results["tracks"]["items"]:
                    image_url = results["tracks"]["items"][0]["album"]["images"][0]["url"]
            except Exception as e:
                print(f"Error fetching Spotify metadata: {str(e)}")

        track_info = {"title": title, "artist": artist, "image_url": image_url}
        
        # Update queue with all tracks from current context
        self.update_queue_from_context()
        self.current_track = track_info
        self.current_track_index = row  # Set index to the clicked row
        self.load_track_async(track_info)
        self.update_queue_display()

    def update_queue_from_context(self):
        """Dynamically update the queue based on the current table content."""
        self.track_queue.clear()
        for row in range(self.content_table.rowCount()):
            title = self.content_table.item(row, 0).text()
            artist = self.content_table.item(row, 1).text()
            image_url = ""
            if self.current_playlist_tracks and row < len(self.current_playlist_tracks):
                track = self.current_playlist_tracks[row]["track"]
                image_url = track["album"]["images"][0]["url"] if track["album"]["images"] else ""
            track_info = {"title": title, "artist": artist, "image_url": image_url}
            self.track_queue.append(track_info)

    def update_duration(self):
        duration = self.vlc_player.get_length()
        if duration > 0:
            self.track_position_slider.setRange(0, duration)
            self.track_position_slider.setEnabled(True)
            if hasattr(self, 'duration_timer'):
                self.duration_timer.stop()
        else:
            is_seekable = self.vlc_player.is_seekable()
            if not is_seekable:
                self.track_position_slider.setEnabled(False)
                if hasattr(self, 'duration_timer'):
                    self.duration_timer.stop()

    def update_playback_progress(self):
        try:
            if not self.vlc_player or not self.vlc_player.get_media():
                return
            
            duration = self.vlc_player.get_length()
            if duration <= 0:
                return

            if not self.track_position_slider.isSliderDown():
                position = self.vlc_player.get_time()
                self.track_position_slider.setValue(position)

            if self.vlc_player.is_playing():
                self.play_button.setText("⏸")
            else:
                self.play_button.setText("▶")
        except Exception as e:
            print(f"Error in update_playback_progress: {str(e)}")
            self.initialize_vlc()  # Reinitialize VLC on error

    def slider_pressed(self):
        """Handle when the slider is pressed (start of drag or click)."""
        pass  # Placeholder for future use

    def slider_moved(self, position):
        """Handle slider movement during dragging."""
        if not self.vlc_player.get_media():
            return
        if self.is_local_track or (self.current_stream_url and self.vlc_player.is_seekable()):
            self.vlc_player.set_time(position)

    def slider_released(self):
        """Handle when the slider is released after dragging or clicking."""
        if not self.vlc_player.get_media():
            return
        position = self.track_position_slider.value()
        was_playing = self.is_playing
        if self.is_local_track or (self.current_stream_url and self.vlc_player.is_seekable()):
            self.vlc_player.set_time(position)
            if not was_playing:
                self.vlc_player.pause()  # Maintain paused state if it was paused

    def set_volume(self, value):
        try:
            self.vlc_player.audio_set_volume(value)
        except Exception as e:
            print(f"Error setting volume: {str(e)}")

    def toggle_playback(self):
        if self.vlc_player.get_media():
            if self.vlc_player.is_playing():
                self.vlc_player.pause()
                self.play_button.setText("▶")
                self.is_playing = False
            else:
                self.vlc_player.play()
                self.play_button.setText("⏸")
                self.is_playing = True
        elif self.track_queue:
            self.current_track_index = 0
            self.play_track_from_queue(self.track_queue[0])

    def play_previous(self):
        if self.current_track_index > 0:
            self.current_track_index -= 1
            self.play_track_from_queue(self.track_queue[self.current_track_index])
        self.update_queue_display()

    def play_next(self):
        if self.current_track_index < len(self.track_queue) - 1:
            self.current_track_index += 1
            if self.is_shuffling and len(self.track_queue) > 2:
                self.shuffle_queue()
            self.play_track_from_queue(self.track_queue[self.current_track_index])
        else:
            self.reset_playback()
        self.update_queue_display()

    def play_track_from_queue(self, track_info):
        """Play a track from the queue, handling both local and streamed tracks."""
        title = track_info["title"]
        artist = track_info["artist"]
        image_url = track_info.get("image_url", "")
        
        # Check if the track is a downloaded file
        local_file = os.path.join(DOWNLOAD_FOLDER, f"{title} - {artist}.mp3")
        if os.path.exists(local_file):
            self.vlc_player.stop()
            self.current_stream_url = None
            self.is_local_track = True
            media = self.vlc_instance.media_new(local_file)
            self.vlc_player.set_media(media)
            self.vlc_player.play()
            self.song_title.setText(title)
            self.artist_name.setText(artist)
            self.current_track = track_info
            self.album_art.setStyleSheet("background-color: #333;")
        else:
            self.load_track_async(track_info)  # Streamed track
        
        self.set_volume(self.volume_slider.value())
        self.play_button.setText("⏸")
        self.is_playing = True
        self.duration_timer = QTimer()
        self.duration_timer.timeout.connect(self.update_duration)
        self.duration_timer.start(500)
        self.update_queue_display()

    def shuffle_queue(self):
        """Shuffle the queue efficiently, preserving the current track."""
        if len(self.track_queue) <= 2:
            return
        current_track = self.track_queue[self.current_track_index]
        remaining_tracks = [t for i, t in enumerate(self.track_queue) if i != self.current_track_index]
        random.shuffle(remaining_tracks)
        self.track_queue = [current_track] + remaining_tracks
        self.current_track_index = 0

    def reset_playback(self):
        self.vlc_player.stop()
        self.song_title.setText("Not Playing")
        self.artist_name.setText("")
        self.album_art.setStyleSheet("background-color: #333;")
        self.play_button.setText("▶")
        self.track_position_slider.setValue(0)
        self.track_position_slider.setEnabled(False)
        self.is_playing = False
        self.current_track_index = -1 if not self.track_queue else 0
        self.is_local_track = False
        self.current_stream_url = None
        self.update_queue_display()

    def show_queue_dialog(self):
        if not self.queue_dialog:
            self.queue_dialog = QueueDialog(self)
        self.queue_dialog.update_queue(self.track_queue)
        self.queue_dialog.exec()

    def on_vlc_event(self, event):
        if event.type == vlc.EventType.MediaPlayerEndReached:
            QMetaObject.invokeMethod(self, "on_song_ended", Qt.ConnectionType.QueuedConnection)

    @pyqtSlot()
    def on_song_ended(self):
        try:
            if self.is_looping and self.current_track_index >= 0 and self.track_queue:
                self.play_track_from_queue(self.track_queue[self.current_track_index])
            elif self.current_track_index >= 0 and self.track_queue:
                self.current_track_index += 1
                if self.current_track_index < len(self.track_queue):
                    if self.is_shuffling and len(self.track_queue) > 2:
                        self.shuffle_queue()
                    self.play_track_from_queue(self.track_queue[self.current_track_index])
                else:
                    self.reset_playback()
            else:
                self.reset_playback()
            self.update_queue_display()
        except Exception as e:
            print(f"Error in on_song_ended: {str(e)}")
            QMessageBox.critical(self, "Playback Error", f"Failed to play next song: {str(e)}")

    def toggle_loop(self):
        self.is_looping = self.loop_button.isChecked()
        print(f"Looping: {self.is_looping}")

    def toggle_shuffle(self):
        self.is_shuffling = self.shuffle_button.isChecked()
        if self.is_shuffling and len(self.track_queue) > 1:
            self.shuffle_queue()
            self.update_queue_display()
        print(f"Shuffling: {self.is_shuffling}")

    def play_local_track(self, row, file_path):
        title = self.content_table.item(row, 0).text()
        artist = self.content_table.item(row, 1).text()
        
        track_info = {
            "title": title,
            "artist": artist,
            "image_url": ""  # No image available for local files
        }
        
        # Update queue with all downloaded tracks
        self.update_queue_from_context()
        self.current_track = track_info
        self.current_track_index = row  # Set index to the clicked row
        
        self.vlc_player.stop()
        self.current_stream_url = None  # Clear stream URL for local tracks
        self.is_local_track = True  # Mark as local
        media = self.vlc_instance.media_new(file_path)
        self.vlc_player.set_media(media)
        self.vlc_player.play()
        
        self.song_title.setText(title)
        self.artist_name.setText(artist)
        self.current_track = track_info
        self.album_art.setStyleSheet("background-color: #333;")  # No album art for local files
        self.set_volume(self.volume_slider.value())
        self.play_button.setText("⏸")
        self.is_playing = True
        
        self.duration_timer = QTimer()
        self.duration_timer.timeout.connect(self.update_duration)
        self.duration_timer.start(500)
        self.update_queue_display()

    def on_library_item_clicked(self, item):
        if not self.sp and item.text() != "Downloaded":  # Allow "Downloaded" to work without Spotify login
            return
        self.playlist_list.clearSelection()  # Clear playlist selection
        self.current_library_selection = item.text()
        self.current_playlist_selection = None
        self.page_widget.setVisible(False)  # Hide pagination buttons for library views
        text = item.text()
        if text == "Liked Music":
            self.load_liked_music()
        elif text == "Albums":
            self.load_top_albums()
        elif text == "Artists":
            self.load_top_artists()
        elif text == "Downloaded":
            self.load_downloaded_tracks()
    
    def on_playlist_item_clicked(self, item):
        if not self.sp:
            return
        self.library_list.clearSelection()  # Clear library selection
        self.current_playlist_selection = item.text()
        self.current_library_selection = None
        self.page_widget.setVisible(False)  # Hide pagination buttons for playlist views
        playlist_name = item.text()
        self.load_playlist_tracks(playlist_name)
    
    def authenticate_spotify(self):
        if self.sp:
            self.sp = None
            self.user_profile = None
            self.auth_action.setText("Login to Spotify")
            self.user_label.setText("Not logged in")
            self.playlist_list.clear()
            self.playlist_list.addItem("Login to view playlists")
            self.content_table.setRowCount(0)
            self.page_widget.setVisible(False)  # Hide pagination buttons on logout
            if os.path.exists("spotify_credentials.json"):
                os.remove("spotify_credentials.json")
            global SPOTIFY_CACHE
            SPOTIFY_CACHE = {}
            save_spotify_cache()
            return
        
        auth_dialog = SpotifyAuthDialog(self)
        if auth_dialog.exec():
            credentials = auth_dialog.get_credentials()
            try:
                scope = "user-library-read playlist-read-private user-top-read playlist-read-collaborative"
                self.sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
                    client_id=credentials["client_id"],
                    client_secret=credentials["client_secret"],
                    redirect_uri=credentials["redirect_uri"],
                    scope=scope,
                    open_browser=True
                ))
                with open("spotify_credentials.json", "w") as f:
                    json.dump(credentials, f)
                self.auth_complete.emit()
            except Exception as e:
                QMessageBox.critical(self, "Authentication Error", f"Failed to authenticate: {str(e)}")
    
    def check_saved_credentials(self):
        if os.path.exists("spotify_credentials.json"):
            try:
                with open("spotify_credentials.json", "r") as f:
                    credentials = json.load(f)
                scope = "user-library-read playlist-read-private user-top-read playlist-read-collaborative"
                self.sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
                    client_id=credentials["client_id"],
                    client_secret=credentials["client_secret"],
                    redirect_uri=credentials["redirect_uri"],
                    scope=scope,
                    open_browser=True
                ))
                self.auth_complete.emit()
            except Exception as e:
                print(f"Error loading saved credentials: {str(e)}")
    
    def on_authentication_complete(self):
        self.auth_action.setText("Logout from Spotify")
        try:
            self.user_profile = self.sp.current_user()
            self.user_label.setText(f"Logged in as: {self.user_profile['display_name']}")
            self.load_playlists()
            self.load_liked_music()
        except Exception as e:
            QMessageBox.warning(self, "API Error", f"Error retrieving Spotify data: {str(e)}")
    
    def load_playlists(self):
        if not self.sp:
            return
        cache_key = f"playlists_{self.user_profile['id']}"
        if cache_key in SPOTIFY_CACHE:
            print(f"Loading playlists from cache for user {self.user_profile['id']}")
            playlists = SPOTIFY_CACHE[cache_key]['data']
            self.playlist_list.clear()
            for playlist in playlists:
                self.playlist_list.addItem(playlist["name"])
            return

        try:
            self.playlist_list.clear()
            offset = 0
            limit = 50
            all_playlists = []
            while True:
                playlists = self.sp.current_user_playlists(limit=limit, offset=offset)
                all_playlists.extend(playlists["items"])
                for playlist in playlists["items"]:
                    self.playlist_list.addItem(playlist["name"])
                if len(playlists["items"]) < limit:
                    break
                offset += limit
            SPOTIFY_CACHE[cache_key] = {
                'data': all_playlists,
                'timestamp': datetime.now().isoformat()
            }
            save_spotify_cache()
        except Exception as e:
            print(f"Error loading playlists: {str(e)}")
    
    def load_liked_music(self):
        if not self.sp:
            return
        cache_key = f"liked_music_{self.user_profile['id']}"
        if cache_key in SPOTIFY_CACHE:
            print(f"Loading liked music from cache for user {self.user_profile['id']}")
            tracks = SPOTIFY_CACHE[cache_key]['data']
            self.current_playlist_tracks = tracks
            self.display_tracks(tracks, self.content_table)
            return

        try:
            tracks = []
            offset = 0
            limit = 50
            while True:
                results = self.sp.current_user_saved_tracks(limit=limit, offset=offset)
                tracks.extend(results["items"])
                if len(results["items"]) < limit:
                    break
                offset += limit
            self.current_playlist_tracks = tracks
            self.display_tracks(tracks, self.content_table)
            SPOTIFY_CACHE[cache_key] = {
                'data': tracks,
                'timestamp': datetime.now().isoformat()
            }
            save_spotify_cache()
        except Exception as e:
            print(f"Error loading liked music: {str(e)}")
    
    def load_top_artists(self):
        if not self.sp:
            return
        cache_key = f"top_artists_{self.user_profile['id']}"
        if cache_key in SPOTIFY_CACHE:
            print(f"Loading top artists from cache for user {self.user_profile['id']}")
            artists = SPOTIFY_CACHE[cache_key]['data']
            self.content_table.setHorizontalHeaderLabels(["Artist", "Genres", "Popularity", ""])
            self.content_table.setColumnCount(4)
            self.content_table.setRowCount(0)
            for i, artist in enumerate(artists):
                self.content_table.insertRow(i)
                self.content_table.setItem(i, 0, QTableWidgetItem(artist["name"]))
                self.content_table.setItem(i, 1, QTableWidgetItem(", ".join(artist["genres"][:3])))
                self.content_table.setItem(i, 2, QTableWidgetItem(str(artist["popularity"])))
            self.current_playlist_tracks = []
            return

        try:
            artists = []
            offset = 0
            limit = 20
            while True:
                results = self.sp.current_user_top_artists(limit=limit, offset=offset)
                artists.extend(results["items"])
                if len(results["items"]) < limit:
                    break
                offset += limit
            self.content_table.setHorizontalHeaderLabels(["Artist", "Genres", "Popularity", ""])
            self.content_table.setColumnCount(4)
            self.content_table.setRowCount(0)
            for i, artist in enumerate(artists):
                self.content_table.insertRow(i)
                self.content_table.setItem(i, 0, QTableWidgetItem(artist["name"]))
                self.content_table.setItem(i, 1, QTableWidgetItem(", ".join(artist["genres"][:3])))
                self.content_table.setItem(i, 2, QTableWidgetItem(str(artist["popularity"])))
            self.current_playlist_tracks = []
            SPOTIFY_CACHE[cache_key] = {
                'data': artists,
                'timestamp': datetime.now().isoformat()
            }
            save_spotify_cache()
        except Exception as e:
            print(f"Error loading top artists: {str(e)}")
    
    def load_top_albums(self):
        if not self.sp:
            return
        cache_key = f"top_albums_{self.user_profile['id']}"
        if cache_key in SPOTIFY_CACHE:
            print(f"Loading top albums from cache for user {self.user_profile['id']}")
            albums = SPOTIFY_CACHE[cache_key]['data']
            self.content_table.setHorizontalHeaderLabels(["Album", "Artist", "Release Date", "Tracks"])
            self.content_table.setColumnCount(4)
            self.content_table.setRowCount(0)
            for i, item in enumerate(albums):
                album = item["album"]
                self.content_table.insertRow(i)
                self.content_table.setItem(i, 0, QTableWidgetItem(album["name"]))
                self.content_table.setItem(i, 1, QTableWidgetItem(", ".join([artist["name"] for artist in album["artists"]])))
                self.content_table.setItem(i, 2, QTableWidgetItem(album["release_date"]))
                self.content_table.setItem(i, 3, QTableWidgetItem(str(album["total_tracks"])))
            self.current_playlist_tracks = []
            return

        try:
            albums = []
            offset = 0
            limit = 20
            while True:
                results = self.sp.current_user_saved_albums(limit=limit, offset=offset)
                albums.extend(results["items"])
                if len(results["items"]) < limit:
                    break
                offset += limit
            self.content_table.setHorizontalHeaderLabels(["Album", "Artist", "Release Date", "Tracks"])
            self.content_table.setColumnCount(4)
            self.content_table.setRowCount(0)
            for i, item in enumerate(albums):
                album = item["album"]
                self.content_table.insertRow(i)
                self.content_table.setItem(i, 0, QTableWidgetItem(album["name"]))
                self.content_table.setItem(i, 1, QTableWidgetItem(", ".join([artist["name"] for artist in album["artists"]])))
                self.content_table.setItem(i, 2, QTableWidgetItem(album["release_date"]))
                self.content_table.setItem(i, 3, QTableWidgetItem(str(album["total_tracks"])))
            self.current_playlist_tracks = []
            SPOTIFY_CACHE[cache_key] = {
                'data': albums,
                'timestamp': datetime.now().isoformat()
            }
            save_spotify_cache()
        except Exception as e:
            print(f"Error loading albums: {str(e)}")
    
    def load_playlist_tracks(self, playlist_name):
        if not self.sp:
            return
        cache_key = f"playlist_{self.user_profile['id']}_{playlist_name}"
        if cache_key in SPOTIFY_CACHE:
            print(f"Loading playlist tracks from cache: {playlist_name}")
            tracks = SPOTIFY_CACHE[cache_key]['data']
            self.current_playlist_tracks = tracks
            self.display_tracks(tracks, self.content_table)
            return

        try:
            offset = 0
            limit = 50
            playlist_id = None
            while True:
                playlists = self.sp.current_user_playlists(limit=limit, offset=offset)
                for playlist in playlists["items"]:
                    if playlist["name"] == playlist_name:
                        playlist_id = playlist["id"]
                        break
                if playlist_id or len(playlists["items"]) < limit:
                    break
                offset += limit
            
            if not playlist_id:
                return
                
            tracks = []
            offset = 0
            limit = 100
            while True:
                results = self.sp.playlist_tracks(playlist_id, limit=limit, offset=offset)
                tracks.extend(results["items"])
                if len(results["items"]) < limit:
                    break
                offset += limit
            self.current_playlist_tracks = tracks
            self.display_tracks(tracks, self.content_table)
            SPOTIFY_CACHE[cache_key] = {
                'data': tracks,
                'timestamp': datetime.now().isoformat()
            }
            save_spotify_cache()
        except Exception as e:
            print(f"Error loading playlist tracks: {str(e)}")

    def load_downloaded_tracks(self):
        self.content_table.setHorizontalHeaderLabels(["Title", "Artist", "Album", "Duration", ""])
        self.content_table.setColumnCount(5)
        self.content_table.setRowCount(0)
        
        if not os.path.exists(DOWNLOAD_FOLDER):
            self.content_table.insertRow(0)
            self.content_table.setItem(0, 0, QTableWidgetItem("No downloaded tracks found"))
            self.content_table.setItem(0, 1, QTableWidgetItem(""))
            self.content_table.setItem(0, 2, QTableWidgetItem(""))
            self.content_table.setItem(0, 3, QTableWidgetItem(""))
            return

        downloaded_files = [f for f in os.listdir(DOWNLOAD_FOLDER) if f.endswith('.mp3')]
        self.current_playlist_tracks = []  # Clear current playlist tracks since these are local files
        
        for i, filename in enumerate(downloaded_files):
            try:
                name_without_ext = os.path.splitext(filename)[0]
                if " - " in name_without_ext:
                    title, artist = name_without_ext.split(" - ", 1)
                else:
                    title = name_without_ext
                    artist = "Unknown"
            except Exception:
                title = filename
                artist = "Unknown"

            self.content_table.insertRow(i)
            self.content_table.setItem(i, 0, QTableWidgetItem(title))
            self.content_table.setItem(i, 1, QTableWidgetItem(artist))
            self.content_table.setItem(i, 2, QTableWidgetItem("Downloaded"))
            self.content_table.setItem(i, 3, QTableWidgetItem("N/A"))
            
            play_button = QPushButton("▶")
            play_button.setStyleSheet("""
                QPushButton { background-color: transparent; border: none; font-size: 14px; color: #1DB954; }
                QPushButton:hover { background-color: #333; border-radius: 5px; }
            """)
            full_path = os.path.join(DOWNLOAD_FOLDER, filename)
            play_button.clicked.connect(lambda checked, row=i, path=full_path: self.play_local_track(row, path))
            self.content_table.setCellWidget(i, 4, play_button)

    def display_tracks(self, tracks, table):
        table.setHorizontalHeaderLabels(["Title", "Artist", "Album", "Duration", ""])
        table.setColumnCount(5)
        table.setRowCount(0)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        for i, item in enumerate(tracks):
            track = item["track"] if "track" in item else item
            if track:
                table.insertRow(i)
                table.setItem(i, 0, QTableWidgetItem(track["name"]))
                table.setItem(i, 1, QTableWidgetItem(", ".join([artist["name"] for artist in track["artists"]])))
                table.setItem(i, 2, QTableWidgetItem(track["album"]["name"]))
                duration_ms = track["duration_ms"]
                minutes = duration_ms // 60000
                seconds = (duration_ms % 60000) // 1000
                table.setItem(i, 3, QTableWidgetItem(f"{minutes}:{seconds:02d}"))
                play_button = QPushButton("▶")
                play_button.setStyleSheet("""
                    QPushButton { background-color: transparent; border: none; font-size: 14px; color: #1DB954; }
                    QPushButton:hover { background-color: #333; border-radius: 5px; }
                """)
                play_button.clicked.connect(lambda checked, row=i: self.play_from_button(row))
                table.setCellWidget(i, 4, play_button)

    def start_search(self):
        query = self.search_input.text().strip()
        if not query:
            QMessageBox.warning(self, "Search Error", "Please enter a search query.")
            return
        self.current_search_query = query
        self.current_page = 1
        self.all_search_results = []
        self.library_list.clearSelection()  # Clear sidebar selections
        self.playlist_list.clearSelection()
        self.current_library_selection = None
        self.current_playlist_selection = None
        if self.search_thread and self.search_thread.is_alive():
            self.search_thread.join(timeout=1)
        self.search_thread = threading.Thread(target=self._perform_search, args=(query, 0))
        self.search_thread.daemon = True
        self.search_thread.start()

    def _perform_search(self, query, offset):
        if self.sp:
            try:
                limit = 50
                total_fetched = 0
                all_tracks = []
                max_results = self.max_pages * limit

                while total_fetched < max_results:
                    results = self.sp.search(q=query, type="track", limit=limit, offset=offset)
                    tracks = results["tracks"]["items"]
                    all_tracks.extend(tracks)
                    total_fetched += len(tracks)
                    offset += limit
                    if len(tracks) < limit:
                        break

                self.all_search_results = all_tracks[:max_results]
                if not self.all_search_results:
                    QMetaObject.invokeMethod(
                        self,
                        "show_search_message",
                        Qt.ConnectionType.QueuedConnection,
                        Q_ARG(str, "No tracks found for your query.")
                    )
                    return
                self.search_complete.emit(self.all_search_results, total_fetched)
                QMetaObject.invokeMethod(
                    self,
                    "show_page_buttons",
                    Qt.ConnectionType.QueuedConnection
                )
            except Exception as e:
                print(f"Error searching Spotify: {str(e)}")
                QMetaObject.invokeMethod(
                    self,
                    "show_search_message",
                    Qt.ConnectionType.QueuedConnection,
                    Q_ARG(str, f"Error searching: {str(e)}")
                )
        else:
            track_info = {"title": query, "artist": "Unknown", "image_url": ""}
            QMetaObject.invokeMethod(
                self,
                "play_track_from_search",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(dict, track_info)
            )

    @pyqtSlot(str)
    def show_search_message(self, message):
        QMessageBox.information(self, "Search Results", message)

    @pyqtSlot(list, int)
    def on_search_complete(self, tracks, total_fetched):
        self.current_playlist_tracks = []
        self.current_page = 1
        for i, button in enumerate(self.page_buttons, 1):
            button.setChecked(i == self.current_page)
        self.display_current_page()

    @pyqtSlot()
    def show_page_buttons(self):
        self.page_widget.setVisible(True)

    def display_current_page(self):
        start_idx = (self.current_page - 1) * 50
        end_idx = min(start_idx + 50, len(self.all_search_results))
        page_tracks = self.all_search_results[start_idx:end_idx]
        self.content_table.setRowCount(0)
        self.display_tracks(page_tracks, self.content_table)

    def change_page(self, page):
        if 1 <= page <= self.max_pages and page != self.current_page:
            self.current_page = page
            for i, button in enumerate(self.page_buttons, 1):
                button.setChecked(i == page)
            self.display_current_page()

    @pyqtSlot(dict)
    def play_track_from_search(self, track_info):
        self.track_queue = [track_info]
        self.current_track = track_info
        self.current_track_index = 0
        self.current_playlist_tracks = []
        self.content_table.setRowCount(0)
        self.content_table.insertRow(0)
        self.content_table.setItem(0, 0, QTableWidgetItem(track_info["title"]))
        self.content_table.setItem(0, 1, QTableWidgetItem(track_info["artist"]))
        self.content_table.setItem(0, 2, QTableWidgetItem("N/A"))
        self.content_table.setItem(0, 3, QTableWidgetItem("N/A"))
        play_button = QPushButton("▶")
        play_button.setStyleSheet("""
            QPushButton { background-color: transparent; border: none; font-size: 14px; color: #1DB954; }
            QPushButton:hover { background-color: #333; border-radius: 5px; }
        """)
        play_button.clicked.connect(lambda checked: self.play_from_button(0))
        self.content_table.setCellWidget(0, 4, play_button)
        self.load_track_async(track_info)
        self.update_queue_display()

    def update_queue_display(self):
        if self.queue_dialog and self.queue_dialog.isVisible():
            self.queue_dialog.update_queue(self.track_queue)

    def download_track(self, title, artist):
        self.start_download_worker([(title, artist)])

    def download_selected_tracks(self, selected_rows):
        if not selected_rows:
            QMessageBox.warning(self, "Download Error", "No tracks selected.")
            return

        tracks_to_download = []
        for row in selected_rows:
            title = self.content_table.item(row, 0).text()
            artist = self.content_table.item(row, 1).text()
            tracks_to_download.append((title, artist))

        self.start_download_worker(tracks_to_download)

    def delete_track(self, row):
        title = self.content_table.item(row, 0).text()
        artist = self.content_table.item(row, 1).text()
        file_path = os.path.join(DOWNLOAD_FOLDER, f"{title} - {artist}.mp3")
        
        reply = QMessageBox.warning(
            self,
            "Delete Track",
            f"Are you sure you want to delete '{title} - {artist}'?\nThis action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    self.content_table.removeRow(row)
                    if self.content_table.rowCount() == 0:
                        self.content_table.insertRow(0)
                        self.content_table.setItem(0, 0, QTableWidgetItem("No downloaded tracks found"))
                        self.content_table.setItem(0, 1, QTableWidgetItem(""))
                        self.content_table.setItem(0, 2, QTableWidgetItem(""))
                        self.content_table.setItem(0, 3, QTableWidgetItem(""))
                else:
                    QMessageBox.warning(self, "Delete Error", "File not found on disk.")
                    self.load_downloaded_tracks()
            except Exception as e:
                QMessageBox.critical(self, "Delete Error", f"Failed to delete file: {str(e)}")
            if self.current_track and self.current_track["title"] == title and self.current_track["artist"] == artist:
                self.reset_playback()

    def start_download_worker(self, tracks_to_download):
        if not hasattr(self, 'download_queue'):
            self.download_queue = []
            self.current_download_worker = None

        self.download_queue.extend(tracks_to_download)
        self.total_downloads = len(self.download_queue)

        if not self.download_progress_dialog:
            self.download_progress_dialog = DownloadProgressDialog(self)

        self.download_progress_dialog.show()
        self.download_progress_dialog.raise_()

        if not self.current_download_worker or not self.current_download_worker.isRunning():
            self.download_next()

    def download_next(self):
        if not self.download_queue:
            if self.download_progress_dialog:
                self.download_progress_dialog.close()
                self.download_progress_dialog = None
            QMessageBox.information(self, "Download Complete", f"Downloaded {self.total_downloads} tracks to {DOWNLOAD_FOLDER}")
            self.download_queue = []
            self.total_downloads = 0
            return

        title, artist = self.download_queue.pop(0)
        self.current_download_worker = DownloadWorker(title, artist, DOWNLOAD_FOLDER)
        self.current_download_worker.progress_updated.connect(self.update_download_progress_slot)
        self.current_download_worker.download_finished.connect(self.on_download_finished)
        self.current_download_worker.start()
        self.download_progress_dialog.update_progress(f"{title} - {artist}", 0)

    @pyqtSlot(str, int)
    def update_download_progress_slot(self, track_name, progress):
        if self.download_progress_dialog:
            self.download_progress_dialog.update_progress(track_name, progress)
        print(f"Downloading {track_name}: {progress}%")

    @pyqtSlot(str, bool)
    def on_download_finished(self, track_name, success):
        if success:
            print(f"Successfully downloaded {track_name}")
            if self.current_library_selection == "Downloaded":
                self.load_downloaded_tracks()  # Refresh downloaded tracks view
        else:
            print(f"Failed to download {track_name}")
            QMessageBox.warning(self, "Download Failed", f"Failed to download {track_name}")

        self.current_download_worker = None
        self.download_next()

    def show_context_menu(self, position):
        indexes = self.content_table.selectedIndexes()
        if not indexes:
            return
        
        row = indexes[0].row()
        menu = QMenu(self)
        
        # Determine if the current view is "Downloaded"
        is_downloaded_section = self.current_library_selection == "Downloaded"

        if is_downloaded_section:
            delete_action = QAction("Delete Track", self)
            delete_action.triggered.connect(lambda: self.delete_track(row))
            menu.addAction(delete_action)
        else:
            single_download_action = QAction("Download Track", self)
            single_download_action.triggered.connect(lambda: self.download_track(
                self.content_table.item(row, 0).text(),
                self.content_table.item(row, 1).text()
            ))
            menu.addAction(single_download_action)

            if len(indexes) > 1:
                batch_download_action = QAction("Download Selected Tracks", self)
                batch_download_action.triggered.connect(lambda: self.download_selected_tracks(
                    sorted(set(index.row() for index in indexes))
                ))
                menu.addAction(batch_download_action)

        menu.exec(self.content_table.viewport().mapToGlobal(position))

    def closeEvent(self, event):
        if hasattr(self, 'current_download_worker') and self.current_download_worker and self.current_download_worker.isRunning():
            self.current_download_worker.cancel()
            self.current_download_worker.wait()
        self.vlc_player.stop()
        self.vlc_player.release()
        self.vlc_instance.release()
        super().closeEvent(event)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    app.setStyleSheet("""
        QMainWindow, QWidget { background-color: #1a1a1a; color: #ffffff; }
        QMenuBar { background-color: #2a2a2a; color: #ffffff; }
        QMenu { background-color: #2a2a2a; color: #ffffff; }
        QMenu::item:selected { background-color: #333; color: #1DB954; }
        QLabel { color: #ffffff; }
        QListWidget { border: none; background-color: #1a1a1a; color: #ffffff; }
        QListWidget::item { padding: 4px; border-radius: 4px; color: #ffffff; }
        QListWidget::item:selected { background-color: #2a2a2a; color: #1DB954; }
        QPushButton { background-color: transparent; border: none; border-radius: 15px; padding: 5px; font-size: 16px; color: #ffffff; }
        QPushButton:hover { background-color: #333; }
        QLineEdit { border: 1px solid #333; border-radius: 15px; padding: 5px 10px; color: #ffffff; background-color: #2a2a2a; }
        QTableWidget { border: none; gridline-color: #333; color: #ffffff; background-color: #1a1a1a; }
        QTableWidget::item { padding: 5px; color: #ffffff; }
        QHeaderView::section { background-color: #2a2a2a; border: none; padding: 5px; font-weight: bold; color: #ffffff; }
        QSlider { background-color: transparent; }
        QSlider::handle { background-color: #1DB954; border-radius: 7px; width: 14px; height: 14px; }
        QSlider::groove:horizontal { height: 4px; background-color: #555; border-radius: 2px; }
        QSlider::sub-page:horizontal { background-color: #1DB954; border-radius: 2px; }
        QSplitter::handle { background-color: #333; }
        QScrollBar:vertical { border: none; background: #2a2a2a; width: 10px; margin: 0px 0px 0px 0px; border-radius: 5px; }
        QScrollBar::handle:vertical { background: #1DB954; min-height: 20px; border-radius: 5px; }
        QScrollBar::handle:vertical:hover { background: #179645; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; background: none; }
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
        QScrollBar:horizontal { border: none; background: #2a2a2a; height: 0px; margin: 0px 0px 0px 0px; }
        QMessageBox { background-color: #1a1a1a; color: #ffffff; }
        QMessageBox QLabel { color: #ffffff; }
        QMessageBox QPushButton { background-color: #2a2a2a; color: #ffffff; border: 1px solid #333; border-radius: 5px; }
        QMessageBox QPushButton:hover { background-color: #333; }
        QProgressBar { border: 1px solid #333; border-radius: 5px; background-color: #2a2a2a; text-align: center; color: #ffffff; }
        QProgressBar::chunk { background-color: #1DB954; border-radius: 5px; }
    """)
    
    window = SpotifyMusicPlayer()
    window.show()
    sys.exit(app.exec())