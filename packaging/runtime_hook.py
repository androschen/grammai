"""Capture early windowed-startup errors before the app's logger is available."""
import os
from pathlib import Path
import sys

folder=Path(os.environ.get('GRAMMAI_DATA_DIR') or str(Path(os.environ.get('LOCALAPPDATA',Path.home()))/'GrammAI'))/'logs'
folder.mkdir(parents=True,exist_ok=True)
path=folder/'startup.log'
stream=path.open('w' if path.exists() and path.stat().st_size>512*1024 else 'a',encoding='utf8',buffering=1)
sys.stdout=stream
sys.stderr=stream
os.environ.setdefault('PYTHAINLP_OFFLINE','1')
