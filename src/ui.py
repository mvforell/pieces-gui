from datetime import datetime
from os import listdir
from random import shuffle

from useful_functions import (
	create_info_str, get_pieces_from_sets, make_history_string_from_dict, get_icon_path, get_time_str_from_ms
)

from PySide2.QtCore import Qt, QTimer
from PySide2.QtGui import QIcon
from PySide2.QtWidgets import (
	QMainWindow, QWidget, QDialog, QMessageBox, QGridLayout, QHBoxLayout, QVBoxLayout, QAbstractItemView, QListWidget,
	QTextEdit, QLineEdit, QSlider, QLabel, QPushButton, QCheckBox
)
from vlc import Instance as VLCInstance


class DirectorySetChooseDialog(QDialog):
	""" a simple dialog to let the user choose from the available directory sets """

	def __init__(self, parent, set_pieces_and_playlist_function):
		"""	pretty standard constructor: set up class variables, ui elements and layout
			parameters:
				- parent: parent widget of this dialog
				- set_pieces_and_playlist_function: is called to set the pieces and playlist variables of the parent """

		super(DirectorySetChooseDialog, self).__init__(parent)

		# -- create and setup ui elements --
		self._lbl_prompt = QLabel('Please choose one or more from the available directory sets:')
		self._lbl_prompt.setMaximumHeight(30)
		self._listwidget_sets = QListWidget()
		self._checkbox_shuffle = QCheckBox('Shuffle playlist')
		self._checkbox_shuffle.setChecked(True)  # shuffling is enabled by default
		self._btn_choose = QPushButton('Choose')
		self._btn_choose.clicked.connect(self.__action_choose)

		# -- setup _listwidget_sets
		options = listdir('../directories')  # get a list of all available directory sets
		options.remove('Default.txt')  # remove default entry
		options.insert(0, 'Default.txt')  # and reinsert it at index 0 to make sure that 'Default' always is the first option
		self._listwidget_sets.addItems([s[:-4] for s in options])
		self._listwidget_sets.setSelectionMode(QAbstractItemView.ExtendedSelection)  # allow multiple selections
		self._listwidget_sets.setCurrentRow(0)  # default entry should be the default selection

		# -- create layout --
		self._layout = QGridLayout(self)
		self._layout.addWidget(self._lbl_prompt, 0, 0, 1, -1)
		self._layout.addWidget(self._listwidget_sets, 1, 0, 4, -1)
		self._layout.addWidget(self._checkbox_shuffle, 5, 0, 1, -1)
		self._layout.addWidget(self._btn_choose, 6, 0, 1, -1)

		# -- various setup --
		self._set_pieces_and_playlist = set_pieces_and_playlist_function
		self.setModal(True)
		self.setWindowTitle('Please choose a directory set')
		self.setMinimumWidth(600)
		self.setMinimumHeight(400)

	def __action_choose(self):
		""" (gets called when self._btn_choose is clicked)
			loads pieces from selected sets, creates a playlist (shuffled if wanted)
			and calls self._set_pieces_and_playlist """

		pieces = get_pieces_from_sets([s.text() + '.txt' for s in self._listwidget_sets.selectedItems()])
		playlist = list(pieces.keys())  # must be a list to be shuffled
		shuffled = self._checkbox_shuffle.isChecked()
		if shuffled:
			shuffle(playlist)
		self._set_pieces_and_playlist(pieces, playlist, shuffled)
		self.close()


class HistoryDialog(QDialog):
	""" a simple dialog to let the user view the playing history """

	def __init__(self, parent, history_str):
		"""	standard constructor: set up class variables, ui elements and layout
			parameters:
				- parent: parent widget of this dialog
				- history_str: str that will be displayed """

		super(HistoryDialog, self).__init__(parent)

		# -- create and setup ui elements --
		self._textview_history = QTextEdit('', parent=parent)
		self._textview_history.setReadOnly(True)
		self._textview_history.setPlainText(history_str)  # plaint text needed for showing newlines
		self._btn_ok = QPushButton('OK')
		self._btn_ok.clicked.connect(self.__action_ok)

		# -- create layout --
		self._layout = QVBoxLayout(self)
		self._layout.addWidget(self._textview_history)
		self._layout.addWidget(self._btn_ok)

		# -- various setup --
		self.setModal(True)
		self.setWindowTitle('Playing History')
		self.setMinimumWidth(800)
		self.setMinimumHeight(300)

	def __action_ok(self):
		"""	(called when self._btn_ok is clicked)
			closes this dialog """

		self.close()


class PiecesPlayer(QWidget):
	""" main widget of this application (used as widget inside a QMainWindow) """

	def __init__(self, parent):
		""" standard constructor: set up class variables, ui elements and layout """

		# TODO: debug in general
		# TODO: fix randomly (?) skipping to next movement when either selecting a new one or current one is finished
		# TODO: add some "whole piece time remaining" indicator
		# TODO: add option to loop current piece (?)
		# TODO: take a look at PySide2.QtWidgets.QShortcut (especially for playing/pausing via hotkey while minimized)
		# TODO: own function for setting new VLC medium (release old one!)
		# TODO: more documentation
		# TODO: implement dialog showing currently loaded set(s) as menu action
		# TODO: implement debug dialog as menu action, if needed

		if not isinstance(parent, PiecesMainWindow):
			raise ValueError('Parent widget must be a PiecesMainWindow')

		super(PiecesPlayer, self).__init__(parent=parent)

		# -- declare and setup variables for storing information --
		# various data
		self._pieces = {}  # {<name of piece1>: [<files piece1 consists of>], ...}
		self._playlist = []  # list of keys of self._pieces which determines the order of playing
		self._shuffled = True  # needed for (maybe) reshuffling playlist when looping
		self._history = {}  # key: timestamp ('HH:MM:SS'), value: info_str of piece that started playing at that time
		self._status = 'Paused'
		self._current_piece = {'title': '', 'files': [], 'play_next': 0}
		self._default_volume = 100  # in percent from 0 - 100
		self._volume_before_muted = self._default_volume
		# vlc-related variables
		self._vlc_instance = VLCInstance()
		self._vlc_mediaplayer = self._vlc_instance.media_player_new()
		self._vlc_mediaplayer.audio_set_volume(self._default_volume)
		self._vlc_medium = None

		# -- create and setup ui elements --
		# buttons
		self._btn_play_pause = QPushButton(QIcon(get_icon_path('play')), '')
		self._btn_previous = QPushButton(QIcon(get_icon_path('previous')), '')
		self._btn_next = QPushButton(QIcon(get_icon_path('next')), '')
		self._btn_volume = QPushButton(QIcon(get_icon_path('volume-high')), '')
		self._btn_loop = QPushButton(QIcon(get_icon_path('loop')), '')
		self._btn_loop.setCheckable(True)
		self._btn_play_pause.clicked.connect(self.__action_play_pause)
		self._btn_previous.clicked.connect(self.__action_previous)
		self._btn_next.clicked.connect(self.__action_next)
		self._btn_volume.clicked.connect(self.__action_volume_clicked)
		# labels
		self._lbl_current_piece = QLabel('Current piece:')
		self._lbl_movements = QLabel('Movements:')
		self._lbl_time_played = QLabel('00:00')
		self._lbl_time_left = QLabel('-00:00')
		self._lbl_volume = QLabel('100%')
		# needed so that everything has the same position independent of the number of digits of volume
		self._lbl_volume.setMinimumWidth(55)
		# sliders
		self._slider_time = QSlider(Qt.Horizontal)
		self._slider_volume = QSlider(Qt.Horizontal)
		self._slider_time.sliderReleased.connect(self.__event_time_changed_by_user)
		self._slider_volume.valueChanged.connect(self.__event_volume_changed)
		self._slider_time.setRange(0, 100)
		self._slider_volume.setRange(0, 100)
		self._slider_volume.setValue(self._default_volume)
		self._slider_volume.setMinimumWidth(100)
		# other elements
		self._checkbox_loop_playlist = QCheckBox('Loop playlist')
		self._lineedit_current_piece = QLineEdit()
		self._lineedit_current_piece.setReadOnly(True)
		self._lineedit_current_piece.textChanged.connect(self.__event_piece_text_changed)
		self._listwidget_movements = QListWidget()
		self._listwidget_movements.itemClicked.connect(self.__event_movement_selected)  # or maybe itemDoubleClicked?

		# -- create layout and insert ui elements--
		self._layout = QGridLayout(self)
		# row 0 (name of current piece)
		self._layout.addWidget(self._lbl_current_piece, 0, 0)
		self._layout.addWidget(self._lineedit_current_piece, 0, 1, 1, -1)
		# rows 1 - 5 (movements of current piece)
		self._layout.addWidget(self._lbl_movements, 1, 0)
		self._layout.addWidget(self._listwidget_movements, 2, 0, 4, -1)
		# row 6 (time)
		self._layout_time = QHBoxLayout()
		self._layout_time.addWidget(self._lbl_time_played)
		self._layout_time.addWidget(self._slider_time)
		self._layout_time.addWidget(self._lbl_time_left)
		self._layout.addLayout(self._layout_time, 6, 0, 1, -1)
		self._layout.setRowMinimumHeight(6, 65)
		# row 7 (buttons and volume)
		self._layout_buttons_and_volume = QHBoxLayout()
		self._layout_buttons_and_volume.addWidget(self._btn_play_pause)
		self._layout_buttons_and_volume.addWidget(self._btn_previous)
		self._layout_buttons_and_volume.addWidget(self._btn_next)
		self._layout_buttons_and_volume.addWidget(self._btn_loop)
		self._layout_buttons_and_volume.addSpacing(40)
		self._layout_buttons_and_volume.addStretch()  # distance between loop and volume buttons: min. 40, but stretchable
		self._layout_buttons_and_volume.addWidget(self._btn_volume)
		self._layout_buttons_and_volume.addWidget(self._slider_volume)
		self._layout_buttons_and_volume.addWidget(self._lbl_volume)
		self._layout.addLayout(self._layout_buttons_and_volume, 7, 0, 1, -1)

		# -- various setup --
		self._timer = QTimer(self)
		self._timer.timeout.connect(self.__update)
		self._timer.start(250)  # update every 250ms
		self.setMinimumWidth(800)
		# get directory set(s) input and set up self._pieces (exec_ means we'll wait for the user input before continuing)
		DirectorySetChooseDialog(self, self.set_pieces_and_playlist).exec_()

	def __action_next(self):
		""" switches to next file in self._current_piece['files'] or to the next piece, if the current piece has ended """

		if self._current_piece['play_next'] == -1:  # current movement is the last of the current piece
			if len(self._playlist) == 0:  # reached end of playlist
				if self._btn_loop.isChecked():
					self._playlist = list(self._pieces.keys())
					if self._shuffled:
						shuffle(self._playlist)
					return

				if self._status == 'Playing':
					self.__action_play_pause()
				self._current_piece['title'] = ''
				self._current_piece['files'] = []
				self._current_piece['play_next'] = -1
				self._lineedit_current_piece.setText('')
				self.__update_movement_list()
				self.parentWidget().update_status_bar(self._status, 'End of playlist reached.')
				return
			else:
				if self.parentWidget().get_exit_after_current():
					self.parentWidget().exit()
				if self.parentWidget().get_pause_after_current():
					self.__action_play_pause()
					# reset of the menu action will be at the end of this function, or else we won't stay paused

				self._current_piece['title'] = self._playlist.pop(0)
				self._current_piece['files'] = [p[1:-1] for p in self._pieces[self._current_piece['title']]]
				# some pieces only have one movement
				self._current_piece['play_next'] = 1 if len(self._current_piece['files']) > 1 else -1
				self._vlc_medium = self._vlc_instance.media_new(self._current_piece['files'][0])
				self._lineedit_current_piece.setText(create_info_str(self._current_piece['title'], self._current_piece['files']))
				self.__update_movement_list()
				self._history[datetime.now().strftime('%H:%M:%S')] = self._lineedit_current_piece.text()
		else:
			self._vlc_medium = self._vlc_instance.media_new(self._current_piece['files'][self._current_piece['play_next']])
			if self._current_piece['play_next'] == len(self._current_piece['files']) - 1:  # current is last movement
				self._current_piece['play_next'] = -1
			else:  # there is at least one movement of the current piece to be played
				self._current_piece['play_next'] += 1
		self._vlc_medium.parse()
		self._vlc_mediaplayer.set_media(self._vlc_medium)
		if self._status == 'Paused' and not self.parentWidget().get_pause_after_current():
			self.__action_play_pause()
		elif self.parentWidget().get_pause_after_current():
			self.parentWidget().set_pause_after_current(False)
		else:
			self._vlc_mediaplayer.play()
		self.parentWidget().update_status_bar(self._status, f'{len(self._pieces) - len(self._playlist)}/{len(self._pieces)}')

	def __action_play_pause(self):
		"""	(gets called when self._btn_play_pause is clicked)
			toggles playing/pausing music and updates everything as needed """

		if self._current_piece['title'] == '':  # don't do anything now (maybe end of playlist reached?)
			return

		if self._status == 'Paused':
			if not self._vlc_medium:
				self.__action_next()
			self._vlc_mediaplayer.play()
			self._btn_play_pause.setIcon(QIcon(get_icon_path('pause')))
			self._status = 'Playing'
		else:
			self._vlc_mediaplayer.pause()
			self._btn_play_pause.setIcon(QIcon(get_icon_path('play')))
			self._status = 'Paused'
		self.parentWidget().update_status_bar(self._status, f'{len(self._pieces) - len(self._playlist)}/{len(self._pieces)}')

	def __action_previous(self):
		"""	(called when self._btn_previous ist clicked)
			goes back one movement of the current piece, if possible (cannot go back to previous piece) """

		if len(self._current_piece['files']) == 1:  # can't go back to previous piece, but current one has one movement
			pass
		elif self._current_piece['play_next'] == 1:  # currently playing first movement, so nothing to do as well
			pass
		else:  # we can go back one movement
			if self._current_piece['play_next'] == -1:  # currently at last movement
				self._current_piece['play_next'] = len(self._current_piece['files']) - 1  # set play_next to last movement
			else:  # currently before last movement
				self._current_piece['play_next'] -= 1  # set play_next to current movement
			self._vlc_mediaplayer.stop()
			self._vlc_medium = self._vlc_instance.media_new(self._current_piece['files'][self._current_piece['play_next'] - 1])
			self._vlc_medium.parse()
			self._vlc_mediaplayer.set_media(self._vlc_medium)
			self._vlc_mediaplayer.play()

	def __action_volume_clicked(self):
		"""	(called when self._btn_volume is clicked)
			(un)mutes volume """

		if self._slider_volume.value() == 0:  # unmute volume
			self._slider_volume.setValue(self._volume_before_muted)
		else:  # mute volume
			self._volume_before_muted = self._slider_volume.value()
			self._slider_volume.setValue(0)

	def __event_movement_selected(self):
		"""	(called when self._listwidget_movements emits itemClicked) (or itemDoubleClicked, see self.__init__ to be sure)
			skips to the newly selected movement """

		index = self._listwidget_movements.indexFromItem(self._listwidget_movements.currentItem()).row()
		if index != self.__get_current_movement_index():  # user selected a movement different from the current one
			self._current_piece['play_next'] = index
			self.__action_next()

	def __event_piece_text_changed(self):
		"""	(called when self._lineedit_current_piece emits textChanged)
			ensures that the user sees the beginning of the text in self._lineedit_current_piece
			(if text is too long, the end will be cut off and the user must scroll manually to see it) """

		self._lineedit_current_piece.setCursorPosition(0)

	def __event_volume_changed(self):
		"""	(called when value of self._slider_volume changes)
			updates text of self._lbl_volume to new value of self._slider_value
			and sets icon of self._btn_volume to a fitting one """

		volume = self._slider_volume.value()
		self._lbl_volume.setText(f'{volume}%')
		if volume == 0:
			self._btn_volume.setIcon(QIcon(get_icon_path('volume-muted')))
		elif volume < 34:
			self._btn_volume.setIcon(QIcon(get_icon_path('volume-low')))
		elif volume < 67:
			self._btn_volume.setIcon(QIcon(get_icon_path('volume-medium')))
		else:
			self._btn_volume.setIcon(QIcon(get_icon_path('volume-high')))
		self._vlc_mediaplayer.audio_set_volume(volume)

	def __event_time_changed_by_user(self):
		"""	(called when user releases self._slider_time)
			synchronizes self._vlc_mediaplayer's position to the new value of self._slider_time """

		self._vlc_mediaplayer.set_position(self._slider_time.value() / 100)

	def __get_current_movement_index(self):
		""" returns the index of the current movement in self._current_piece['files'] """

		play_next = self._current_piece['play_next']
		if play_next == -1:
			return len(self._current_piece['files']) - 1
		else:
			return play_next - 1

	def __update_movement_list(self):
		"""	removes all items currently in self._listwidget_movements and adds everything in self._current_piece['files] """

		while self._listwidget_movements.count() > 0:
			self._listwidget_movements.takeItem(0)
		files = self._current_piece['files']
		files = [i[i.rfind('\\') + 3:-4] for i in files]  # remove path to file, title number and .mp3 ending
		self._listwidget_movements.addItems(files)

	def __update(self):
		"""	(periodically called when self._timer emits timeout signal)
			updates various ui elements"""

		# -- select currently playing movement in self._listwidget_movements --
		if self._listwidget_movements.count() > 0:
			self._listwidget_movements.item(self.__get_current_movement_index()).setSelected(True)

		# -- update text of self._lbl_time_played and self._lbl_time_left, if necessary --
		if self._vlc_medium:
			time_played = self._vlc_mediaplayer.get_time()
			medium_duration = self._vlc_medium.get_duration()
			if (time_played >= 0) and (time_played <= medium_duration):  # other values don't make sense (but do occur)
				self._lbl_time_played.setText(get_time_str_from_ms(time_played))
			else:
				self._lbl_time_played.setText(get_time_str_from_ms(0))
			self._lbl_time_left.setText(f'-{get_time_str_from_ms(medium_duration - time_played)}')

		# -- update value of self._slider_time --
		if not self._slider_time.isSliderDown():  # don't reset slider to current position if user is dragging it
			self._slider_time.setValue(self._vlc_mediaplayer.get_position() * 100)

		# -- go to next movement/piece when current movement/piece has ended --
		if (self._current_piece['files'] != []) and (self._status == 'Playing') and (not self._vlc_mediaplayer.is_playing()):
			self.__action_next()

	def get_history(self):
		""" getter function for parent widget """

		return self._history

	def set_pieces_and_playlist(self, pieces, playlist, shuffled):
		""" needed so that DirectorySetChooseDialog can set our self._pieces and self._playlist """

		if isinstance(pieces, dict) and isinstance(playlist, list):  # just to be sure
			self._vlc_mediaplayer.stop()
			self._pieces = pieces
			self._playlist = playlist
			self._shuffled = shuffled
			self._current_piece['title'] = self._playlist.pop(0)
			self._current_piece['files'] = [p[1:-1] for p in self._pieces[self._current_piece['title']]]  # remove any "s
			self._current_piece['play_next'] = 1 if len(self._current_piece['files']) > 1 else -1
			self._lineedit_current_piece.setText(create_info_str(self._current_piece['title'], self._current_piece['files']))
			self.__update_movement_list()
			self._vlc_medium = self._vlc_instance.media_new(self._current_piece['files'][0])
			self._vlc_medium.parse()
			self._vlc_mediaplayer.set_media(self._vlc_medium)
			self._history[datetime.now().strftime('%H:%M:%S')] = self._lineedit_current_piece.text()

	def exit(self):
		""" exits cleanly """

		self._vlc_mediaplayer.stop()
		self._vlc_mediaplayer.release()
		self._vlc_instance.release()


class PiecesMainWindow(QMainWindow):
	""" main window of this application, wrapping a menu and status bar around the PiecesPlayer widget """

	def __init__(self):
		""" standard constructor: set up ui elements and layout """

		# TODO: add icon (already found some candidates on icons8.com)
		# TODO: disable maximizing/add maximum width & height? (looks pretty awful for big sizes)
		# TODO: exit cleanly as well when not using the menu action (e.g. by closing the window)

		super(PiecesMainWindow, self).__init__()

		# -- create and setup ui elements --
		self._widget_player = PiecesPlayer(self)
		self._statuslbl_play_pause = QLabel('Paused')
		self._statuslbl_playlist_position = QLabel('Position in playlist: 0/?')

		# -- setup layout --
		self.setCentralWidget(self._widget_player)

		# -- menu and status bar setup --
		# menu bar
		self._menu_file = self.menuBar().addMenu('File')
		self._menu_file_action_pause_after_current = self._menu_file.addAction('Pause after current piece')
		self._menu_file_action_pause_after_current.setCheckable(True)
		self._menu_file_action_exit_after_current = self._menu_file.addAction('Exit after current piece')
		self._menu_file_action_exit_after_current.setCheckable(True)
		self._menu_file.addAction(QIcon(get_icon_path('reload')), 'Load new directory set(s)', self.__action_reload_sets)
		self._menu_file.addAction(QIcon(get_icon_path('history')), 'Show history', self.__action_show_history)
		self._menu_file.addAction(QIcon(get_icon_path('exit')), 'Exit', self.__action_exit)
		# status bar
		self.statusBar().addPermanentWidget(self._statuslbl_play_pause)
		self.statusBar().addWidget(self._statuslbl_playlist_position)
		self._statuslbl_playlist_position.hide()

		# -- various setup --
		self.setWindowTitle('Pieces Player')

	def __action_reload_sets(self):
		""" (called when menu action "Load new directory set(s)" is clicked)
			opens a DirectorySetChooseDialog, which sets self._pieces and self._playlist to new values """

		# get directory set(s) input and set up wait for user input before continuing
		DirectorySetChooseDialog(self, self._widget_player.set_pieces_and_playlist).exec_()

	def __action_show_history(self):
		"""	(gets called when 'show history' menu entry is clicked)
			shows an QMessageBox.information Dialog containing the playing history """

		history = self._widget_player.get_history()
		if history == {}:
			QMessageBox.information(self, 'Playing history', 'Nothing has been played yet.')
		else:
			HistoryDialog(self, make_history_string_from_dict(history)).exec_()

	def __action_exit(self):
		"""	(called when menu action "Exit" is clicked)
			exits cleanly by calling exit function of the central widget and then closing """

		self._widget_player.exit()
		self.close()

	def exit(self):
		self.__action_exit()

	def get_pause_after_current(self):
		""" getter function for self._widget_player """

		return self._menu_file_action_pause_after_current.isChecked()

	def set_pause_after_current(self, bool_val):
		""" setter function for self._widget_player """

		self._menu_file_action_pause_after_current.setChecked(bool_val)

	def get_exit_after_current(self):
		""" getter function for self._widget_player """

		return self._menu_file_action_exit_after_current.isChecked()

	def update_status_bar(self, txt_play_pause, txt_playlist_position):
		"""	(called by self._widget_player)
			updates text of statusbar QLabel widgets and (un)hides self._statuslbl_playlist_position if as necessary """

		self._statuslbl_play_pause.setText(txt_play_pause)
		if txt_playlist_position != '':
			self._statuslbl_playlist_position.setText(txt_playlist_position)
			self._statuslbl_playlist_position.show()
		else:
			self._statuslbl_playlist_position.hide()
