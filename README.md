# PicsNest

A modern image and video management application built with Python and Tkinter.

## Features

- Browse and manage images and videos in a grid view
- Preview images and videos
- Navigate through folders easily
- Delete files with undo functionality
- Multi-select support
- Image viewing with zoom and navigation
- Video playback support (requires VLC)

## Requirements

- Python 3.8 or higher
- Pillow (PIL) library
- python-vlc (optional, for video playback)

## Installation

1. Clone this repository:
```powershell
git clone https://github.com/yourusername/PicsNest.git
cd PicsNest
```

2. Create a virtual environment (recommended):
```powershell
python -m venv venv
.\venv\Scripts\activate
```

3. Install required packages:
```powershell
pip install -r requirements.txt
```

## Usage

Run the application:
```powershell
python main.py
```

## Building from Source

To create a standalone executable:

1. Install PyInstaller:
```powershell
pip install pyinstaller
```

2. Build the executable:
```powershell
pyinstaller PicsNest.spec
```

The executable will be created in the `dist` folder.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
