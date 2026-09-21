import json
import spotipy
from spotipy.oauth2 import SpotifyOAuth

with open("config.json", "r", encoding="utf-8") as f:
    cfg = json.load(f)["spotify"]

print("Opening browser to authorize Spotify...")
auth_manager = SpotifyOAuth(
    client_id=cfg["client_id"],
    client_secret=cfg["client_secret"],
    redirect_uri="http://127.0.0.1:5057/",
    scope="user-read-currently-playing user-read-playback-state user-modify-playback-state",
    cache_path=".spotify_cache"
)

# This triggers the login popup
spotipy.Spotify(auth_manager=auth_manager).current_playback()
print("Success! .spotify_cache file created. You can now use the dashboard.")