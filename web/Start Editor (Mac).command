#!/bin/zsh
# Serves the WA2 Translation Editor locally and opens it. Nothing leaves your machine.
cd "$(dirname "$0")"
PORT=8478
( sleep 1; open "http://localhost:$PORT/" ) &
exec python3 -m http.server $PORT
