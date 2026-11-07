# TV Caster

Cast videos and audio to Chromecast / Google Cast TVs on the same Wi-Fi, and
control playback (play, pause, stop, seek, volume, mute) from your computer.

## Run from source
1. Install Python 3.9+.
2. `pip install -r requirements.txt`
3. `python tvcaster.py`
4. Click **Scan**, pick your TV, then either paste a direct video/audio link and click
   **Cast URL**, or click **Cast File...** to stream a file from this computer.

## Build a downloadable Windows app
```
pip install pyinstaller
pyinstaller --noconsole --onefile --name TVCaster tvcaster.py
```
The app is created at `dist/TVCaster.exe`. Share that file.

## Notes
- The computer and the TV must be on the same network, and your firewall must allow
  Python/TVCaster on private networks. Local files are served on port 8765.
- "Cast File" serves only the one file you choose, and only while it is casting.
- Works with Google Cast devices (Chromecast, Google TV, Android TV with Cast, and
  many smart TVs with built-in Cast). Apple AirPlay and Roku are not supported.
- Direct media links must be publicly reachable by the TV (plain .mp4/.mp3/.m3u8 files work
  best). Streaming sites with DRM (Netflix, etc.) cannot be cast this way.
