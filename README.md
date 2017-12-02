# video_thumbnail_viewer
Python application to generate, view and play videos. Comes in handy when you have tons of videos you want browse.

VideoThumbViewer.py is GUI and that uses VideoThumbGenerator.py to create snapshots of videos.

VideoThumbGenerator.py creates video snapshots (e.g., frames from 30%, 60% and 90% timepoints) of all files in a given folder and its subfolders. It will also write textfile that contains paths of all figures and videos. FFMPEG is the main workhorse.

You can use GUI to browse all video thumbnails/previews and click to open videos in player.

This is a first working version, it rough and lots of stuff is missing. It's a work in progress..

-Janne K.
