import os
from mutagen.easyid3 import EasyID3
from datetime import time


ICON_SIZE = '64px'


def get_pieces_from_sets(sets):
    """	takes a list of set filenames, reads the directories from those sets
        and then gets all the pieces which are in those directories """

    directories = []
    pieces = {}
    prefix = ''

    for path in sets:
        # utf-8 is important
        with open('../directories/' + path, encoding='utf-8') as input_file:
            lines = input_file.readlines()
        for line in lines:
            if line.startswith('prefix='):  # set prefix to non-empty string
                prefix = line[7:-1]
            # ignore commented or empty lines
            elif not ((line[0] == '#') or (line == '\n')):
                directories.append(prefix + line.replace('\n', ''))

    for directory in directories:
        # ID3-title (piece-specific, not per-movement) of last file
        # ('' if new directory, used to decide whether we found a new piece)
        id3 = ''
        for filename in sorted(os.listdir(directory)):
            if '.mp3' in filename:  # ignore non-mp3 files
                audio = EasyID3(os.path.join(directory, filename))
                try:
                    id3_text = audio['title'][0]
                except KeyError:
                    print(os.path.join(directory, filename) + ' does not have a TIT2 ID3 tag')
                    continue
                n_id3 = id3_text[:id3_text.find(' - ')] if (' - ' in id3_text) else id3_text
                # ID3-title of current file
                n_id3 = n_id3.strip()  # remove any spaces at beginning/end
                if n_id3 != id3:  # seems to be a new piece
                    id3 = n_id3  # set new ID3-title because new piece
                    # new piece so we need to create a new empty list that we
                    # can append files to
                    pieces[id3] = []
                pieces[id3].append(
                    '"' + os.path.join(directory, filename) + '"'
                )  # quotes needed for windows file name handling

    return pieces


def make_history_string_from_dict(history_dict):
    history_str = ''
    if history_dict == {}:
        history_str = 'Nothing has been played yet.'
    else:
        for key in history_dict.keys():
            history_str += f'[{key}] {history_dict[key]}\n'
    return history_str


def get_icon_path(icn_name):
    """	returns the path to the icon with the given name using ICON_SIZE
        (icn_name without .png) """

    return f'../icons/{ICON_SIZE}/{icn_name}.png'


def get_time_str_from_ms(ms):
    """ returns a strftime-formatted string created from the millisecond count
        given """

    # whatever works ¯\_(ツ)_/¯
    hours, minutes, seconds = ms // 3600000, ms // 60000 % 60, ms // 1000 % 60
    if hours > 0:
        return time(hour=hours, minute=minutes, second=seconds).strftime(
            "%H:%M:%S"
        )
    else:
        return time(minute=minutes, second=seconds).strftime("%M:%S")


def create_info_str(piece, files):
    info_str = f'"{piece}"'

    try:  # if artist can be read from first file add it to info_str
        info_str += f' by {EasyID3(files[0])["artist"][0]}'
    except KeyError:  # else just pass
        pass

    try:  # if album can be read from first file add it to info_str
        info_str += f' from album "{EasyID3(files[0])["album"][0]}" '
    except KeyError:  # else just pass
        pass

    try:  # if length can be read from files sum it up and add it to info_str
        play_time = 0
        for entry in files:
            play_time += int(EasyID3(entry)["length"][0])
        info_str += f' ({get_time_str_from_ms(play_time)})'
    except KeyError:  # else just pass
        pass

    return info_str
