# Torrent Downloader (WIP)

A python package to download torrents written in python asyncio.


## Features
- Download torrents using .torrent files
- Track download progress
- Resume partially downloaded torrents

## Installation

```sh
pip install torrentix
```

## Usage

```python
from torrentix import Torrent

async def main():
    # Initialize downloader
    t = Torrent("path/to/file.torrent")

    # Start download
    await t.start()
```

## Roadmap
- [ ] Support for magnet links
- [ ] Downloading specific files from a torrent
...

## License
MIT License

## Disclaimer
This tool is for educational purposes only. Ensure you have the right to download any torrent before using this software.

