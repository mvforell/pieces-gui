import os
from mutagen.easyid3 import EasyID3
from datetime import time


ICON_SIZE = '64px'


def get_pieces_from_sets(sets):
	"""	takes a list of set filenames, reads the directories from those sets and then gets all the pieces
		which are in those directories """

	directories = []
	pieces = {}
	prefix = ''

	for path in sets:
		with open('../directories/' + path, encoding='utf-8') as input_file:  # utf-8 is important
			lines = input_file.readlines()
		for line in lines:
			if line.startswith('prefix='):  # set prefix to non-empty string if specified
				prefix = line[7:-1]
			elif not ((line[0] == '#') or (line == '\n')):  # ignore commented or empty lines
				directories.append(prefix + line.replace('\n', ''))

	for directory in directories:
		id3 = ''  # ID3-title (piece-specific, not per-movement) of last file ('' if new directory)
		# (used to decide whether current file is a new piece)
		for filename in os.listdir(directory):
			if '.mp3' in filename:  # ignore non-mp3 files
				audio = EasyID3(os.path.join(directory, filename))
				n_id3 = audio['title'][0][:audio['title'][0].find(' - ')] if (' - ' in audio['title'][0]) else audio['title'][0]
				# ID3-title of current file
				n_id3 = n_id3.strip()  # remove any eventual spaces at the beginning/end
				if n_id3 != id3:  # seems to be a new piece
					id3 = n_id3  # set new ID3-title because we are handling a new piece now
					pieces[id3] = []  # new piece so we need to create a new empty list that we can append files to
				pieces[id3].append('"' + os.path.join(directory, filename) + '"')  # quotes needed for windows file name handling
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
	""" returns a strftime-formatted string created from the millisecond count given """

	hours, minutes, seconds = ms // 3_600_000, ms // 60_000 % 60, ms // 1000 % 60  # whatever works ¯\_(ツ)_/¯
	if hours > 0:
		return time(hour=hours, minute=minutes, second=seconds).strftime("%H:%M:%S")
	else:
		return time(minute=minutes, second=seconds).strftime("%M:%S")


def create_info_str(piece, files):
	info_str = f'"{piece}"'

	try:  # if artist can be read from original file add it to info_str
		info_str += f' by {EasyID3(files[0])["artist"][0]}'
	except KeyError:  # else just pass
		pass

	try:  # if length can be read from original file add it to info_str
		play_time = 0
		for entry in files:
			play_time += int(EasyID3(entry)["length"][0])
		info_str += f' ({get_time_str_from_ms(play_time)})'
	except KeyError:  # else just pass
		pass

	return info_str
