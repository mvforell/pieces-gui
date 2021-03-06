from datetime import datetime
from os import listdir, name as os_name
from random import shuffle


if os_name == 'nt':
    from os import add_dll_directory
    add_dll_directory(r'C:\Program Files\VideoLAN\VLC')


from pynput import keyboard
from PySide2.QtCore import Qt, QTimer
from PySide2.QtGui import QIcon, QKeySequence
from PySide2.QtWidgets import (
    QMainWindow, QWidget, QDialog, QMessageBox, QGridLayout, QHBoxLayout,
    QVBoxLayout, QAbstractItemView, QListWidget, QTextEdit, QLineEdit, QSlider,
    QLabel, QPushButton, QCheckBox, QShortcut
)
from vlc import Instance as VLCInstance, EventType as VLCEventType

from useful_functions import (
    create_info_str, get_pieces_from_sets, make_history_string_from_dict,
    get_icon_path, get_time_str_from_ms
)


class DirectorySetChooseDialog(QDialog):
    """ simple dialog to let user choose from the available directory sets """

    def __init__(self, parent, set_pieces_and_playlist_function):
        """ pretty standard constructor: set up class variables, ui elements
            and layout parameters:
                - parent: parent widget of this dialog
                - set_pieces_and_playlist_function: is called to set the pieces
                  and playlist variables of the parent """

        super(DirectorySetChooseDialog, self).__init__(parent)

        # -- create and setup ui elements --
        self._lbl_prompt = QLabel(
            'Please choose one or more from the available directory sets:'
        )
        self._lbl_prompt.setMaximumHeight(30)
        self._listwidget_sets = QListWidget()
        self._checkbox_shuffle = QCheckBox('Shuffle playlist')
        self._checkbox_shuffle.setChecked(True)  # shuffling enabled by default
        self._listwidget_sets.itemDoubleClicked.connect(self.__action_choose)
        self._btn_choose = QPushButton('Choose')
        self._btn_choose.clicked.connect(self.__action_choose)

        # -- setup _listwidget_sets
        options = listdir('../directories')  # get list of available sets
        options.remove('Default.txt')  # remove default entry
        # and reinsert at index 0 to ensure that 'Default' is the first option
        options.insert(0, 'Default.txt')
        self._listwidget_sets.addItems([s[:-4] for s in options])
        self._listwidget_sets.setSelectionMode(  # allow multiple selections
            QAbstractItemView.ExtendedSelection
        )
        self._listwidget_sets.setCurrentRow(0)  # select default entry

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
            loads pieces from selected sets, creates a playlist
            (shuffled if wanted) and calls self._set_pieces_and_playlist """

        selected_sets = self._listwidget_sets.selectedItems()
        selected_str = 'Currently loaded directory set(s):\n"' + \
            '", "'.join([s.text() for s in selected_sets]) + '"'
        pieces = get_pieces_from_sets([
            s.text() + '.txt' for s in selected_sets
        ])
        playlist = list(pieces.keys())  # must be a list to be shuffled
        shuffled = self._checkbox_shuffle.isChecked()
        if shuffled:
            shuffle(playlist)
        self._set_pieces_and_playlist(pieces, playlist, selected_str, shuffled)
        self.close()


class HistoryDialog(QDialog):
    """ a simple dialog to let the user view the playing history """

    def __init__(self, parent, history_str):
        """ standard constructor: set up class variables, ui elements and layout
            parameters:
                - parent: parent widget of this dialog
                - history_str: str that will be displayed """

        super(HistoryDialog, self).__init__(parent)

        # -- create and setup ui elements --
        self._textview_history = QTextEdit('', parent=parent)
        self._textview_history.setReadOnly(True)
        # plain text needed for showing newlines
        self._textview_history.setPlainText(history_str)
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
        """ (called when self._btn_ok is clicked)
            closes this dialog """

        self.close()


class PiecesPlayer(QWidget):
    """ main widget of application (used as widget inside PiecesMainWindow) """

    def __init__(self, parent):
        """ standard constructor: set up class variables, ui elements
            and layout """

        # TODO: split current piece info into separate lineedits for title, album name and length
        # TODO: make time changeable by clicking next to the slider (not only
        #       by dragging the slider)
        # TODO: add "about" action to open info dialog in new "help" menu
        # TODO: add option to loop current piece (?)
        # TODO: more documentation
        # TODO: add some "whole piece time remaining" indicator? (complicated)
        # TODO: implement a playlist of pieces that can be edited and enable
        #       going back to the previous piece (also un- and re-shuffling?)
        # TODO: implement debug dialog as menu action (if needed)

        if not isinstance(parent, PiecesMainWindow):
            raise ValueError('Parent widget must be a PiecesMainWindow')

        super(PiecesPlayer, self).__init__(parent=parent)

        # -- declare and setup variables for storing information --
        # various data
        self._set_str = ''  # string of currently loaded directory sets
        self._pieces = {}  # {<piece1>: [<files piece1 consists of>], ...}
        self._playlist = []  # list of keys of self._pieces (determines order)
        self._shuffled = True  # needed for (maybe) reshuffling when looping
        # doc for self._history:
        # key: timestamp ('HH:MM:SS'),
        # value: info_str of piece that started playing at that time
        self._history = {}
        self._status = 'Paused'
        self._current_piece = {'title': '', 'files': [], 'play_next': 0}
        self._default_volume = 60  # in percent from 0 - 100
        self._volume_before_muted = self._default_volume
        # set to true by self.__event_movement_ended and used by self.__update
        self._skip_to_next = False
        # vlc-related variables
        self._vlc_instance = VLCInstance()
        self._vlc_mediaplayer = self._vlc_instance.media_player_new()
        self._vlc_mediaplayer.audio_set_volume(self._default_volume)
        self._vlc_medium = None
        self._vlc_events = self._vlc_mediaplayer.event_manager()

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
        # needed so that everything has the same position
        # independent of the number of digits of volume
        self._lbl_volume.setMinimumWidth(55)
        # sliders
        self._slider_time = QSlider(Qt.Horizontal)
        self._slider_volume = QSlider(Qt.Horizontal)
        self._slider_time.sliderReleased.connect(
            self.__event_time_changed_by_user
        )
        self._slider_volume.valueChanged.connect(self.__event_volume_changed)
        self._slider_time.setRange(0, 100)
        self._slider_volume.setRange(0, 100)
        self._slider_volume.setValue(self._default_volume)
        self._slider_volume.setMinimumWidth(100)
        # other elements
        self._checkbox_loop_playlist = QCheckBox('Loop playlist')
        self._lineedit_current_piece = QLineEdit()
        self._lineedit_current_piece.setReadOnly(True)
        self._lineedit_current_piece.textChanged.connect(
            self.__event_piece_text_changed
        )
        self._listwidget_movements = QListWidget()
        self._listwidget_movements.itemClicked.connect(
            self.__event_movement_selected
        )

        # -- create layout and insert ui elements--
        self._layout = QVBoxLayout(self)
        # row 0 (name of current piece)
        self._layout_piece_name = QHBoxLayout()
        self._layout_piece_name.addWidget(self._lbl_current_piece)
        self._layout_piece_name.addWidget(self._lineedit_current_piece)
        self._layout.addLayout(self._layout_piece_name)
        # rows 1 - 5 (movements of current piece)
        self._layout.addWidget(self._lbl_movements)
        self._layout.addWidget(self._listwidget_movements)
        # row 6 (time)
        self._layout_time = QHBoxLayout()
        self._layout_time.addWidget(self._lbl_time_played)
        self._layout_time.addWidget(self._slider_time)
        self._layout_time.addWidget(self._lbl_time_left)
        self._layout.addLayout(self._layout_time)
        # row 7 (buttons and volume)
        self._layout_buttons_and_volume = QHBoxLayout()
        self._layout_buttons_and_volume.addWidget(self._btn_play_pause)
        self._layout_buttons_and_volume.addWidget(self._btn_previous)
        self._layout_buttons_and_volume.addWidget(self._btn_next)
        self._layout_buttons_and_volume.addWidget(self._btn_loop)
        self._layout_buttons_and_volume.addSpacing(40)
        # distance between loop and volume buttons: min. 40, but stretchable
        self._layout_buttons_and_volume.addStretch()
        self._layout_buttons_and_volume.addWidget(self._btn_volume)
        self._layout_buttons_and_volume.addWidget(self._slider_volume)
        self._layout_buttons_and_volume.addWidget(self._lbl_volume)
        self._layout.addLayout(self._layout_buttons_and_volume)

        # -- setup hotkeys --
        self._KEY_CODES_PLAY_PAUSE = [269025044]
        self._KEY_CODES_NEXT = [269025047]
        self._KEY_CODES_PREVIOUS = [269025046]
        self._keyboard_listener = keyboard.Listener(on_press=self.__on_press)
        self._keyboard_listener.start()
        QShortcut(QKeySequence('Space'), self, self.__action_play_pause)

        # -- various setup --
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.__update)
        self._timer.start(100)  # update every 100ms
        self.setMinimumWidth(900)
        self.setMinimumHeight(400)
        # get directory set(s) input and set up self._pieces
        # (exec_ means we'll wait for the user input before continuing)
        DirectorySetChooseDialog(self, self.set_pieces_and_playlist).exec_()
        # skip to next movement / next piece when current one has ended
        self._vlc_events.event_attach(VLCEventType.MediaPlayerEndReached,
                                      self.__event_movement_ended)

    def __action_next(self):
        """ switches to next file in self._current_piece['files']
            or to the next piece, if the current piece has ended """

        reset_pause_after_current = False

        # current movement is last of the current piece
        if self._current_piece['play_next'] == -1:
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
                self.parentWidget().update_status_bar(
                    self._status, 'End of playlist reached.'
                )
                return
            else:
                if self.parentWidget().get_exit_after_current():
                    self.parentWidget().exit()
                if self.parentWidget().get_pause_after_current():
                    self.__action_play_pause()
                    reset_pause_after_current = True
                    # reset of the menu action will be at the end of this
                    # function, or else we won't stay paused

                self._current_piece['title'] = self._playlist.pop(0)
                self._current_piece['files'] = [
                    p[1:-1] for p in self._pieces[self._current_piece['title']]
                ]
                # some pieces only have one movement
                self._current_piece['play_next'] = \
                    1 if len(self._current_piece['files']) > 1 else -1
                self.__update_vlc_medium(0)
                self._lineedit_current_piece.setText(
                    create_info_str(
                        self._current_piece['title'],
                        self._current_piece['files']
                    )
                )
                self.__update_movement_list()
                self._history[datetime.now().strftime('%H:%M:%S')] = \
                    self._lineedit_current_piece.text()
        else:
            self.__update_vlc_medium(self._current_piece['play_next'])
            # next is last movement
            if self._current_piece['play_next'] == \
               len(self._current_piece['files']) - 1:
                self._current_piece['play_next'] = -1
            else:  # there are at least two movements of current piece left
                self._current_piece['play_next'] += 1
        if self._status == 'Paused' and not reset_pause_after_current:
            self.__action_play_pause()
        elif reset_pause_after_current:
            self.parentWidget().set_pause_after_current(False)
        else:
            self._vlc_mediaplayer.play()
        self.parentWidget().update_status_bar(
            self._status,
            f'{len(self._pieces) - len(self._playlist)}/{len(self._pieces)}'
        )

    def __action_play_pause(self):
        """ (gets called when self._btn_play_pause is clicked)
            toggles playing/pausing music and updates everything as needed """

        # don't do anything now (maybe end of playlist reached?)
        if self._current_piece['title'] == '':
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
        self.parentWidget().update_status_bar(
            self._status,
            f'{len(self._pieces) - len(self._playlist)}/{len(self._pieces)}'
        )

    def __action_previous(self):
        """ (called when self._btn_previous ist clicked)
            goes back one movement of the current piece, if possible
            (cannot go back to previous piece) """

        # can't go back to previous piece, but current one has no or one movement
        if len(self._current_piece['files']) <= 1:
            pass
        # currently playing first movement, so nothing to do as well
        elif self._current_piece['play_next'] == 1:
            pass
        else:  # we can go back one movement
            # currently at last movement
            if self._current_piece['play_next'] == -1:
                # set play_next to last movement
                self._current_piece['play_next'] = \
                    len(self._current_piece['files']) - 1
            else:  # currently before last movement
                # set play_next to current movement
                self._current_piece['play_next'] -= 1
            self._vlc_mediaplayer.stop()
            self.__update_vlc_medium(self._current_piece['play_next'] - 1)
            self._vlc_mediaplayer.play()

    def __action_volume_clicked(self):
        """ (called when self._btn_volume is clicked)
            (un)mutes volume """

        if self._slider_volume.value() == 0:  # unmute volume
            self._slider_volume.setValue(self._volume_before_muted)
        else:  # mute volume
            self._volume_before_muted = self._slider_volume.value()
            self._slider_volume.setValue(0)

    def __event_movement_ended(self, event):
        """ (called when self._vlc_media_player emits a MediaPlayerEndReached
            event)
            sets self._skip_to_next to True so the next self.__update call
            will trigger self.__action_next """

        self._skip_to_next = True

    def __event_movement_selected(self):
        """ (called when self._listwidget_movements emits itemClicked)
            skips to the newly selected movement """

        index = self._listwidget_movements.indexFromItem(
            self._listwidget_movements.currentItem()
        ).row()
        # user selected a movement different from the current one
        if index != self.__get_current_movement_index():
            self._current_piece['play_next'] = index
            self.__action_next()

    def __event_piece_text_changed(self):
        """ (called when self._lineedit_current_piece emits textChanged)
            ensures that the user sees the beginning of the text in
            self._lineedit_current_piece (if text is too long, the end will be
            cut off and the user must scroll manually to see it) """

        self._lineedit_current_piece.setCursorPosition(0)

    def __event_volume_changed(self):
        """ (called when value of self._slider_volume changes)
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
        """ (called when user releases self._slider_time)
            synchronizes self._vlc_mediaplayer's position to the new value
            of self._slider_time """

        self._vlc_mediaplayer.set_position(self._slider_time.value() / 100)

    def __get_current_movement_index(self):
        """ returns the index of the current movement in
            self._current_piece['files'] """

        play_next = self._current_piece['play_next']
        if play_next == -1:
            return len(self._current_piece['files']) - 1
        else:
            return play_next - 1

    def __on_press(self, key):
        """ (called by self._keyboard_listener when a key is pressed)
            looks up key code corresponding to key and calls the appropriate
            action function """

        try:  # key is not always of the same type (why would it be?!)
            key_code = key.vk
        except AttributeError:
            key_code = key.value.vk
        if key_code in self._KEY_CODES_PLAY_PAUSE:
            self.__action_play_pause()
        elif key_code in self._KEY_CODES_NEXT:
            self.__action_next()
        elif key_code in self._KEY_CODES_PREVIOUS:
            self.__action_previous()

    def __update_movement_list(self):
        """ removes all items currently in self._listwidget_movements and adds
            everything in self._current_piece['files] """

        # TODO: use ID3 title instead of filename

        while self._listwidget_movements.count() > 0:
            self._listwidget_movements.takeItem(0)
        files = self._current_piece['files']
        if os_name == 'nt':  # windows paths look different than posix paths
            # remove path to file, title number and .mp3 ending
            files = [i[i.rfind('\\') + 3:-4] for i in files]
        else:
            files = [i[i.rfind('/') + 4:-4] for i in files]
        self._listwidget_movements.addItems(files)

    def __update(self):
        """ (periodically called when self._timer emits timeout signal)
            updates various ui elements"""

        # -- select currently playing movement in self._listwidget_movements --
        if self._listwidget_movements.count() > 0:
            self._listwidget_movements.item(
                self.__get_current_movement_index()
            ).setSelected(True)

        # -- update text of self._lbl_time_played and self._lbl_time_left,
        # if necessary --
        if self._vlc_medium:
            try:
                time_played = self._vlc_mediaplayer.get_time()
                medium_duration = self._vlc_medium.get_duration()
                # other values don't make sense (but do occur)
                if (time_played >= 0) and (time_played <= medium_duration):
                    self._lbl_time_played.setText(
                        get_time_str_from_ms(time_played)
                    )
                else:
                    self._lbl_time_played.setText(get_time_str_from_ms(0))
                self._lbl_time_left.setText(
                    f'-{get_time_str_from_ms(medium_duration - time_played)}'
                )
            except OSError:  # don't know why that occurs sometimes
                pass

        # -- update value of self._slider_time --
        # don't reset slider to current position if user is dragging it
        if not self._slider_time.isSliderDown():
            try:
                self._slider_time.setValue(self._vlc_mediaplayer.get_position()
                                           * 100)
            except OSError:  # don't know why that occurs sometimes
                pass

        if self._skip_to_next:
            self._skip_to_next = False
            self.__action_next()

    def __update_vlc_medium(self, files_index):
        old_medium = self._vlc_medium
        self._vlc_medium = self._vlc_instance.media_new(
            self._current_piece['files'][files_index]
        )
        self._vlc_medium.parse()
        self._vlc_mediaplayer.set_media(self._vlc_medium)
        if old_medium:  # only release if not None
            old_medium.release()

    def get_history(self):
        """ getter function for parent widget """

        return self._history

    def get_set_str(self):
        """ getter function for parent widget """

        return self._set_str if self._set_str != '' \
            else 'No directory set loaded.'

    def set_pieces_and_playlist(self, pieces, playlist, set_str, shuffled):
        """ needed so that DirectorySetChooseDialog can set our self._pieces
            and self._playlist """

        # just to be sure
        if isinstance(pieces, dict) and isinstance(playlist, list):
            self._vlc_mediaplayer.stop()
            self._set_str = set_str
            self._pieces = pieces
            self._playlist = playlist
            self._shuffled = shuffled
            self._current_piece['title'] = self._playlist.pop(0)
            self._current_piece['files'] = [
                p.replace('"', '') for p in self._pieces[
                    self._current_piece['title']
                ]
            ]
            self._current_piece['play_next'] = \
                1 if len(self._current_piece['files']) > 1 else -1
            self._lineedit_current_piece.setText(
                create_info_str(
                    self._current_piece['title'], self._current_piece['files']
                )
            )
            self.__update_movement_list()
            self.__update_vlc_medium(0)
            self._history[datetime.now().strftime('%H:%M:%S')] = \
                self._lineedit_current_piece.text()

    def exit(self):
        """ exits cleanly """

        try:  # don't know why that occurs sometimes
            self._vlc_mediaplayer.stop()
            self._vlc_mediaplayer.release()
            self._vlc_instance.release()
        except OSError:
            pass

        self._keyboard_listener.stop()


class PiecesMainWindow(QMainWindow):
    """ main window of this application, wrapping a menu and status bar around
        the PiecesPlayer widget """

    def __init__(self):
        """ standard constructor: set up ui elements and layout """

        super(PiecesMainWindow, self).__init__()

        # -- create and setup statusbar elements --
        self._statuslbl_play_pause = QLabel('Paused')
        self._statuslbl_playlist_position = QLabel('Position in playlist: 0/?')

        # -- menu and status bar setup --
        # menu bar
        self._menu_options = self.menuBar().addMenu('Options')
        self._menu_options_action_pause_after_current = self._menu_options.addAction(
            'Pause after current piece',
            None,  # "called" when clicked, needed for complying with signature
            QKeySequence('Ctrl+P')
        )
        self._menu_options_action_pause_after_current.setCheckable(True)
        self._menu_options_action_exit_after_current = self._menu_options.addAction(
            'Exit after current piece',
            None,  # "called" when clicked, needed for complying with signature
            QKeySequence('Ctrl+E')
        )
        self._menu_options_action_exit_after_current.setCheckable(True)
        self._menu_options.addAction(
            QIcon(get_icon_path('info')),
            'Show loaded directory set(s)',
            self.__action_show_set,
            QKeySequence('Ctrl+D')
        )
        self._menu_options.addAction(
            QIcon(get_icon_path('reload')),
            'Load new directory set(s)',
            self.__action_reload_sets,
            QKeySequence('Ctrl+L')
        )
        self._menu_options.addAction(
            QIcon(get_icon_path('history')),
            'Show history',
            self.__action_show_history,
            QKeySequence('Ctrl+H')
        )
        self._menu_options.addAction(
            QIcon(get_icon_path('exit')),
            'Exit',
            self.__action_exit,
            QKeySequence('Ctrl+W')
        )
        # status bar
        self.statusBar().addPermanentWidget(self._statuslbl_play_pause)
        self.statusBar().addWidget(self._statuslbl_playlist_position)
        self._statuslbl_playlist_position.hide()

        # -- various setup --
        self.setWindowIcon(QIcon(get_icon_path('music-folder')))
        self.setWindowTitle('Pieces Player')
        self._widget_player = PiecesPlayer(self)
        self.setCentralWidget(self._widget_player)

    def __action_reload_sets(self):
        """ (called when menu action "Load new directory set(s)" is clicked)
            opens a DirectorySetChooseDialog, which sets self._pieces and
            self._playlist to new values """

        # get and wait for directory set(s) input
        DirectorySetChooseDialog(
            self,
            self._widget_player.set_pieces_and_playlist
        ).exec_()

    def __action_show_history(self):
        """ (gets called when 'show history' menu entry is clicked)
            shows an QMessageBox.information Dialog containing the playing
            history """

        history = self._widget_player.get_history()
        if history == {}:
            QMessageBox.information(
                self,
                'Playing history',
                'Nothing has been played yet.'
            )
        else:
            HistoryDialog(self, make_history_string_from_dict(history)).exec_()

    def __action_show_set(self):
        """ (gets called when 'show history' menu entry is clicked)
            shows an QMessageBox.information Dialog containing the playing
            history """

        sets = self._widget_player.get_set_str()
        QMessageBox.information(
            self,
            'Loaded set(s)',
            sets
        )

    def __action_exit(self):
        """ (called when menu action "Exit" is clicked)
            exits cleanly by calling exit function of the central widget and
            then closing """

        self._widget_player.exit()
        self.close()

    def closeEvent(self, event):
        """ -- override (inherited from QWidget) --
            (called when user closes the window not via the menu action)
            wrapper function that calls self.__action_exit and accepts the
            event """

        self.__action_exit()
        event.accept()

    def exit(self):
        self.__action_exit()

    def get_pause_after_current(self):
        """ getter function for self._widget_player """

        return self._menu_options_action_pause_after_current.isChecked()

    def set_pause_after_current(self, bool_val):
        """ setter function for self._widget_player """

        self._menu_options_action_pause_after_current.setChecked(bool_val)

    def get_exit_after_current(self):
        """ getter function for self._widget_player """

        return self._menu_options_action_exit_after_current.isChecked()

    def update_status_bar(self, txt_play_pause, txt_playlist_position):
        """ (called by self._widget_player)
            updates text of statusbar QLabel widgets and (un)hides
            self._statuslbl_playlist_position if as necessary """

        self._statuslbl_play_pause.setText(txt_play_pause)
        if txt_playlist_position != '':
            self._statuslbl_playlist_position.setText(
                'Piece ' + txt_playlist_position
            )
            self._statuslbl_playlist_position.show()
        else:
            self._statuslbl_playlist_position.hide()
