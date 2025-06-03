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

Before you start, make sure you have:
- Python 3.8 or higher installed
- VLC Media Player installed (for video playback support)
- Git installed (to clone the repository)

All other dependencies will be installed automatically during setup.

## Installation

1. Clone this repository:
```powershell
git clone https://github.com/IsmarWolf/PicsNest.git
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

To run the application:

1. For Windows users:
```powershell
python main.py
```

2. For Mac/Linux users:
```bash
python3 main.py
```

The application will open and you can:
- Browse your folders in the grid view
- Click on images to preview them
- Double-click to open in full view
- Use arrow keys to navigate between images
- Delete files with 'Delete' key (with undo support)
- Multi-select files by dragging or Ctrl+Click

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
