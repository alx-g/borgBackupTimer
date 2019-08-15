#!/usr/bin/env python
import configparser
import logging
import logging.handlers
import os
import shlex
import subprocess
import sys
import tempfile
from collections import deque
from functools import partial

from PyQt5.QtCore import QTimer, QThreadPool
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QSystemTrayIcon, QMenu, QAction, QApplication

from BBackup import BBackup
from BEnv import BEnv
from BTask import BTask


class MainApp:
    def __init__(
            self,
            qapp,
            bbackups,
            check_interval,
            environments,
            graphical_editor
    ):
        # Reference to main PyQt.QApplication
        self.qapp = qapp

        # Config-defined editor to use when showing borg command output
        self.graphical_editor = graphical_editor

        # Load all tray icon files
        self.icon = QIcon("icons/icon.png")
        self.icon_running = [
            QIcon("icons/icon_running0.png"),
            QIcon("icons/icon_running1.png"),
            QIcon("icons/icon_running2.png"),
            QIcon("icons/icon_running3.png"),
            QIcon("icons/icon_running4.png"),
            QIcon("icons/icon_running5.png"),
            QIcon("icons/icon_running6.png"),
            QIcon("icons/icon_running7.png")
        ]
        self.icon_running_idx = 0
        self.icon_error = QIcon("icons/icon_error.png")
        self.icon_ok = QIcon("icons/icon_ok.png")
        self.icon_attention = QIcon("icons/icon_attention.png")

        # Load icons for menu
        self.micon_exit = QIcon("icons/micon_exit.png")
        self.micon_info = QIcon("icons/micon_info.png")
        self.micon_run = QIcon("icons/micon_run.png")

        # Keep track of borg backups
        self.bbackups = deque(bbackups)
        self.bbackups_ = deque()

        # Keep track of stati of borg backups and other commands
        # This dict determines which icon is displayed in tray
        self.status = {}

        # Get all environments (BEnv objects)
        self.environments = environments

        # Setup tray icon
        self.qapp.setQuitOnLastWindowClosed(False)
        self.tray = QSystemTrayIcon()
        self.tray.setIcon(self.icon)

        # Create right-click menu for tray
        self.menu = QMenu()

        self.exit_action = QAction("Exit", self.qapp)
        self.exit_action.triggered.connect(self.click_exit)
        self.exit_action.setIcon(self.micon_exit)
        self.menu.addAction(self.exit_action)

        self.borg_list_actions = {}
        self.borg_create_actions = {}
        for bbackup in self.bbackups:
            self.menu.addSeparator()
            self.borg_list_actions[bbackup.name] = QAction('List "%s"' % bbackup.name, self.qapp)
            self.borg_create_actions[bbackup.name] = QAction('Run "%s" now' % bbackup.name, self.qapp)
            self.borg_list_actions[bbackup.name].triggered.connect(partial(self.click_borg_list, bbackup))
            self.borg_create_actions[bbackup.name].triggered.connect(partial(self.click_borg_create, bbackup))
            self.borg_list_actions[bbackup.name].setIcon(self.micon_info)
            self.borg_create_actions[bbackup.name].setIcon(self.micon_run)
            self.menu.addAction(self.borg_list_actions[bbackup.name])
            self.menu.addAction(self.borg_create_actions[bbackup.name])

        self.tray.setContextMenu(self.menu)

        # Setup main timer and set interval to config-defined value
        self.main_timer = QTimer()
        self.main_timer.setInterval(check_interval * 1000)
        self.main_timer.timeout.connect(self.timed)

        # Setup icon update timer with interval of 200ms
        self.status_timer = QTimer()
        self.status_timer.setInterval(200)
        self.status_timer.timeout.connect(self.update_status)

        # Instantiate a thread pool for long running operations later
        self.thread_pool = QThreadPool()

        # Display tray icon
        self.tray.setVisible(True)

        # Create status variables
        self.cur = None
        self.busy = False
        self.valid_envs = []
        self.user_mode = False

        # Trigger normally timer-triggered function first
        self.timed()
        # Then start timers
        self.main_timer.start()
        self.status_timer.start()

        logging.debug('Setup main qt app, main_timer started with interval of %d seconds.' % (check_interval,))

    def update_status(self):
        # Make sure buttons are disabled when borgBackupTimer is busy
        if self.busy:
            for a in self.borg_list_actions.values():
                a.setEnabled(False)
        else:
            for a in self.borg_list_actions.values():
                a.setEnabled(True)

        # Depending on values in status, set icon
        vals = self.status.values()

        # -1 represents a running process
        if -1 in vals:
            self.tray.setIcon(self.icon_running[self.icon_running_idx])
            if self.icon_running_idx < 7:
                self.icon_running_idx += 1
            else:
                self.icon_running_idx = 0
        else:
            # 0 represents everything is ok
            if not vals or max(vals) < 1:
                self.tray.setIcon(self.icon_ok)
            # 1 represents no internet connection
            elif max(vals) == 1:
                self.tray.setIcon(self.icon_attention)
            # 2 represents an error
            elif max(vals) > 1:
                self.tray.setIcon(self.icon_error)

    def timed(self):
        # this function is triggered by the main timer
        if not self.busy:
            logging.debug('Main timer triggered.')

            # Run update_env (Long running, therefore started asynchronously)
            self.busy = True
            task = BTask(self.update_env)
            task.signals.done.connect(self.call_env_update_done)
            task.signals.fail.connect(self.call_env_update_failed)
            logging.info('Updating valid environments')
            self.thread_pool.start(task)

    def update_env(self):
        # Check all environments, add them to valid_envs if check() returns true
        try:
            self.valid_envs = [e for e in self.environments.values() if e.check()]
            logging.info('Valid environments: %s', str([e.name for e in self.valid_envs]))
        except:
            return False
        else:
            return True

    def call_env_update_failed(self):
        logging.error('Valid environments update failed! Setting to [].')
        self.valid_envs = []
        self.busy = False

    def call_env_update_done(self):
        # Environments are updated now
        # If queue is empty, refill
        if not self.bbackups:
            while self.bbackups_:
                item = self.bbackups_.popleft()
                self.bbackups.append(item)

        # Walk through entries in the queue
        while self.bbackups:
            self.cur = self.bbackups.popleft()

            # Does this bbackup need to be run?
            if self.cur.check():
                logging.info('Check if \'%s\' needs to be run: YES', self.cur.name)

                # Can this backup run in an environment that is currently valid?
                if self.cur.env_check(self.valid_envs):
                    logging.info('Check if \'%s\' is allowed to be run in current environment: YES', self.cur.name)

                    # Run connect_check
                    self.status[self.cur.name] = -1
                    task = BTask(self.cur.connect_check)
                    task.signals.done.connect(self.call_host_check_done)
                    task.signals.fail.connect(self.call_host_check_fail)
                    self.thread_pool.start(task)
                    return
                else:
                    self.status[self.cur.name] = 0
                    logging.info('Check if \'%s\' is allowed to be run in current environment: NO', self.cur.name)
                    self.bbackups_.append(self.cur)
            else:
                self.status[self.cur.name] = 0
                logging.info('Check if \'%s\' needs to be run: NO', self.cur.name)
                self.bbackups_.append(self.cur)

        # Walked through all bbackups, none was started, so we're done for now
        self.busy = False

    def call_host_check_done(self):
        # current bbackup host is reachable
        logging.debug('Check if backup (\'%s\') host \'%s\' can be reached: YES', self.cur.name, self.cur.host)

        # start current bbackup
        task = BTask(self.cur.run)
        task.signals.done.connect(self.call_backup_done)
        task.signals.fail.connect(self.call_backup_fail)
        logging.info('Launching borg...')
        self.thread_pool.start(task)

    def call_host_check_fail(self):
        # current bbackup host is not reachable
        logging.warning('Check if backup (\'%s\') host \'%s\' can be reached: NO', self.cur.name, self.cur.host)
        logging.warning('Aborted backup.')

        # We're done with this bbackup for now
        self.bbackups_.append(self.cur)
        self.status[self.cur.name] = 1

        # As we tried this backup, but could not start it, we're done for this main timer cycle
        self.cur = None
        self.busy = False

    def call_backup_done(self):
        # The bbackup completed successfully
        logging.info('Backup (\'%s\') completed successfully.', self.cur.name)
        if not self.user_mode:
            self.bbackups_.append(self.cur)
        self.status[self.cur.name] = 0
        self.cur = None
        self.busy = False

    def call_backup_fail(self):
        # The bbackup failed
        logging.error('Backup (\'%s\') failed.', self.cur.name)
        if not self.user_mode:
            self.bbackups_.append(self.cur)
        self.status[self.cur.name] = 2
        self.cur = None
        self.busy = False

    def click_borg_list(self, bbackup):
        # The user requested a borg list command on bbackup
        if not self.busy:
            self.busy = True
            self.cur = bbackup
            self.status['user'] = -1
            logging.info('User requested list command on \'%s\'', bbackup.name)

            # Run borg list
            task = BTask(bbackup.run_list)
            task.signals.done.connect(self.call_list_done)
            task.signals.fail.connect(self.call_list_done)
            self.thread_pool.start(task)

    def call_list_done(self):
        # user-requested borg list command completed
        # now display result in an editor
        ret = self.cur.list
        fh, pth = tempfile.mkstemp()
        with open(pth, 'w') as f:
            f.write(ret)
        params = self.graphical_editor + [pth]
        subprocess.Popen(params, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.busy = False
        self.status['user'] = 0

    def click_borg_create(self, bbackup):
        # The user requested to run this bbackup now
        if not self.busy:
            self.busy = True
            self.cur = bbackup
            self.status[bbackup.name] = -1
            self.user_mode = True
            logging.info('User requested to run \'%s\'', bbackup.name)

            # Run host check
            task = BTask(bbackup.connect_check)
            task.signals.done.connect(self.call_host_check_done)
            task.signals.fail.connect(self.call_host_check_fail)
            self.thread_pool.start(task)

    @staticmethod
    def click_exit():
        logging.info('User requested exit.')
        exit()


def main():
    script_dir = os.path.dirname(os.path.realpath(__file__))

    # Setup config parser
    cnf = configparser.ConfigParser()
    cnf._interpolation = configparser.ExtendedInterpolation()
    cnf.read(os.path.join(script_dir, 'config.ini'))

    # Setup logging
    log_formatter = logging.Formatter("%(asctime)s [%(levelname)8.8s] %(message)s", datefmt="%Y-%m-%d %H-%M-%S")
    root_logger = logging.getLogger()

    log_path = cnf.get('logging', 'log_dir', fallback='.')
    log_path = os.path.join(script_dir, log_path, cnf.get('logging', 'log_file', fallback='BorgBackupTimer.log'))

    file_handler = logging.handlers.RotatingFileHandler(log_path,
                                                        maxBytes=cnf.getint('logging', 'log_max_bytes',
                                                                            fallback=524288),
                                                        backupCount=cnf.getint('logging', 'log_backup_count',
                                                                               fallback=3))
    file_handler.setFormatter(log_formatter)
    root_logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(log_formatter)
    root_logger.addHandler(console_handler)

    # keywords for setting logging level
    lut = {
        'debug': logging.DEBUG,
        'info': logging.INFO,
        'warn': logging.WARNING,
        'warning': logging.WARNING,
        'error': logging.ERROR,
        'critical': logging.CRITICAL
    }
    root_logger.setLevel(lut[cnf.get('logging', 'log_level', fallback='INFO').lower()])

    logging.info('Started BorgBackupTimer.')

    # cwd to script dir
    os.chdir(script_dir)
    logging.debug('Changed directory to script dir "%s"' % (script_dir,))

    # Create main Application
    qapp = QApplication(sys.argv)

    # Get bbackup objects
    bbackups = BBackup.from_config(cnf)

    if not bbackups:
        logging.error('No backups registered. There will be no action.')
        exit(255)

    # Setup MainApp and read config values
    MainApp(qapp=qapp,
            check_interval=cnf.getint('main', 'check_interval', fallback=500),
            bbackups=bbackups,
            environments=BEnv.from_config(cnf),
            graphical_editor=shlex.split(cnf.get('main', 'graphical_editor', fallback='gedit')))

    # Run event loop
    sys.exit(qapp.exec_())


if __name__ == '__main__':
    main()
