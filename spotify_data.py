import spotipy
from spotipy.oauth2 import SpotifyOAuth
import os

def get_spotify(cfg):
    # Lock the cache to the exact folder where this script lives
    cache_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".spotify_cache")
    
    auth_manager = SpotifyOAuth(
        client_id=cfg["client_id"],
        client_secret=cfg["client_secret"],
        redirect_uri="http://127.0.0.1:5057/",
        scope="user-read-currently-playing user-read-playback-state user-modify-playback-state",
        cache_path=cache_file,
        open_browser=False
    )
    return spotipy.Spotify(auth_manager=auth_manager)

def get_now_playing(cfg):
    try:
        sp = get_spotify(cfg)
        playback = sp.current_playback()
        
        if not playback or not playback.get('item'):
            return {"is_playing": False}
            
        item = playback['item']
        return {
            "is_playing": playback['is_playing'],
            "title": item['name'],
            "artist": ", ".join(a['name'] for a in item['artists']),
            "image": item['album']['images'][0]['url'] if item['album']['images'] else None,
            "url": item['external_urls']['spotify']
        }
    except Exception as e:
        return {"error": str(e)}

def toggle_playback(cfg, action):
    try:
        sp = get_spotify(cfg)
        if action == "play":
            sp.start_playback()
        elif action == "pause":
            sp.pause_playback()
        elif action == "next":
            sp.next_track()
        elif action == "previous":
            sp.previous_track()
        return {"status": "success"}
    except Exception as e:
        return {"error": str(e)}