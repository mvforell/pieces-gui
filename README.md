## pieces-gui
A simple classical music player with a GUI using Qt for Python.

## Requirements
Tested on python 3.7, also see `requirements.txt`.

## Installation and Setup
(I recommend setting up a virtual environment for python)

Run the following commands:

`git clone https://github.com/mvforell/pieces-gui`

`pip install -r requirements.txt`

You may need to re-configure the `KEY_CODES_...` variables in `ui.py`
for global hotkeys to work correctly on your system (to find the keycodes
of your system see https://gist.github.com/mvforell/dc4d028124f08f313df5b9798767cd27).

## Running
Run `python main.py`.

## Limitations
For security reasons, global hotkeys won't work on macOS unless you follow the
instructions at https://pynput.readthedocs.io/en/latest/limitations.html#mac-osx.

## License and copyright
For license information please refer to the `LICENSE` file.

Copyright (c) 2019 Max von Forell