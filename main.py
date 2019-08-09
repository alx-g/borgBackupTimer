#!/usr/bin/env python
from PyQt5.QtWidgets import QSystemTrayIcon, QMenu, QAction, QApplication
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import QTimer, QThreadPool
import sys
from BBackup import *
import os
from BTask import *
from BEnv import *
import logging
import logging.handlers
import configparser
import shlex
from collections import deque
from functools import partial
import tempfile

class MainApp:
    def __init__(
            self,
            qapp,
            bbackups,
            check_interval,
            environments,
            graphical_editor
    ):
        self.qapp = qapp

        self.graphical_editor = graphical_editor

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
        self.icon_exit = QIcon("icons/icon_exit.png")
        self.icon_info = QIcon("icons/icon_info.png")

        self.bbackups = deque(bbackups)
        self.bbackups_ = deque()
        self.status = {}

        self.environments = environments

        self.qapp.setQuitOnLastWindowClosed(False)
        self.tray = QSystemTrayIcon()
        self.tray.setIcon(self.icon)

        self.menu = QMenu()

        self.exit_action = QAction("Exit", self.qapp)
        self.exit_action.triggered.connect(self.click_exit)
        self.exit_action.setIcon(self.icon_exit)
        self.menu.addAction(self.exit_action)

        self.menu.addSeparator()

        self.backup_actions = {}
        for bbackup in self.bbackups:
            self.backup_actions[bbackup.name] = QAction('borg list %s' % bbackup.name, self.qapp)
            self.backup_actions[bbackup.name].triggered.connect(partial(self.click_backup, bbackup))
            self.backup_actions[bbackup.name].setIcon(self.icon_info)
            self.menu.addAction(self.backup_actions[bbackup.name])

        self.tray.setContextMenu(self.menu)

        self.main_timer = QTimer()
        self.main_timer.setInterval(check_interval * 1000)
        self.main_timer.timeout.connect(self.timed)

        self.status_timer = QTimer()
        self.status_timer.setInterval(200)
        self.status_timer.timeout.connect(self.update_status)

        self.thread_pool = QThreadPool()

        self.tray.setVisible(True)
        self.cur = None
        self.busy = False
        self.valid_envs = []

        self.timed()
        self.main_timer.start()
        self.status_timer.start()

        logging.debug('Setup main qt app, main_timer started with interval of %d seconds.' % (check_interval,))

    def update_status(self):
        if self.busy:
            for a in self.backup_actions.values():
                a.setEnabled(False)
        else:
            for a in self.backup_actions.values():
                a.setEnabled(True)
        vals = self.status.values()
        if -1 in vals:
            self.tray.setIcon(self.icon_running[self.icon_running_idx])
            if self.icon_running_idx < 7:
                self.icon_running_idx += 1
            else:
                self.icon_running_idx = 0
        else:
            if not vals or max(vals) < 1:
                self.tray.setIcon(self.icon_ok)
            elif max(vals) == 1:
                self.tray.setIcon(self.icon_attention)
            elif max(vals) > 1:
                self.tray.setIcon(self.icon_error)

    def timed(self):
        if not self.busy:
            logging.debug('Main timer triggered.')
            self.busy = True
            task = BTask(self.update_env)
            task.signals.done.connect(self.call_env_update_done)
            task.signals.fail.connect(self.call_env_update_failed)
            logging.info('Updating valid environments')
            self.thread_pool.start(task)

    def update_env(self):
        try:
            self.valid_envs = [e for e in self.environments.values() if e.check()]
            logging.info('Valid environments: %s', str([e.name for e in self.valid_envs]))
        except:
            return False
        else:
            return True

    def call_env_update_failed(self):
        logging.critical('Valid environments update failed!')
        logging.info('Exiting.')
        exit(1)

    def call_env_update_done(self):
        if not self.bbackups:
            while self.bbackups_:
                item = self.bbackups_.popleft()
                self.bbackups.append(item)

        while self.bbackups:
            self.cur = self.bbackups.popleft()
            if self.cur.check():
                logging.info('Check if \'%s\' needs to be run: YES', self.cur.name)
                if self.cur.env_check(self.valid_envs):
                    logging.info('Check if \'%s\' is allowed to be run in current environment: YES', self.cur.name)
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
        self.busy = False

    def call_host_check_done(self):
        logging.debug('Check if backup (\'%s\') host \'%s\' can be reached: YES', self.cur.name, self.cur.host)
        task = BTask(self.cur.run)
        task.signals.done.connect(self.call_backup_done)
        task.signals.fail.connect(self.call_backup_fail)
        logging.info('Launching borg...')
        self.thread_pool.start(task)

    def call_host_check_fail(self):
        logging.warning('Check if backup (\'%s\') host \'%s\' can be reached: NO', self.cur.name, self.cur.host)
        logging.warning('Aborted backup.')
        self.bbackups_.append(self.cur)
        self.status[self.cur.name] = 1
        self.cur = None
        self.busy = False

    def call_backup_done(self):
        logging.info('Backup (\'%s\') completed successfully.', self.cur.name)
        self.bbackups_.append(self.cur)
        self.status[self.cur.name] = 0
        self.cur = None
        self.busy = False

    def call_backup_fail(self):
        logging.error('Backup (\'%s\') failed.', self.cur.name)
        self.bbackups_.append(self.cur)
        self.status[self.cur.name] = 2
        self.cur = None
        self.busy = False

    def click_backup(self, bbackup):
        if not self.busy:
            self.busy = True
            self.cur = bbackup
            self.status['user'] = -1
            logging.info('User requested list command on \'%s\'', bbackup.name)
            task = BTask(bbackup.run_list)
            task.signals.done.connect(self.call_list_done)
            task.signals.fail.connect(self.call_list_done)
            self.thread_pool.start(task)

    def call_list_done(self):
        ret = self.cur.list
        fh, pth = tempfile.mkstemp()
        with open(pth, 'w') as f:
            f.write(ret)
        params = self.graphical_editor + [pth]
        subprocess.Popen(params, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.busy = False
        self.status['user'] = 0

    def click_exit(self):
        logging.info('User requested exit.')
        exit()


def main():
    script_dir = os.path.dirname(os.path.realpath(__file__))

    cnf = configparser.ConfigParser()
    cnf._interpolation = configparser.ExtendedInterpolation()
    cnf.read(os.path.join(script_dir, 'config.ini'))

    logFormatter = logging.Formatter("%(asctime)s [%(levelname)8.8s] %(message)s", datefmt="%Y-%m-%d %H-%M-%S")
    rootLogger = logging.getLogger()

    log_path = cnf.get('logging', 'log_dir', fallback='.')
    log_path = os.path.join(script_dir, log_path, cnf.get('logging', 'log_file', fallback='BorgBackupTimer.log'))

    fileHandler = logging.handlers.RotatingFileHandler(log_path,
                                                       maxBytes=cnf.getint('logging', 'log_max_bytes', fallback=524288),
                                                       backupCount=cnf.getint('logging', 'log_backup_count',
                                                                              fallback=3))
    fileHandler.setFormatter(logFormatter)
    rootLogger.addHandler(fileHandler)

    consoleHandler = logging.StreamHandler(sys.stdout)
    consoleHandler.setFormatter(logFormatter)
    rootLogger.addHandler(consoleHandler)

    lut = {
        'debug': logging.DEBUG,
        'info': logging.INFO,
        'warn': logging.WARNING,
        'warning': logging.WARNING,
        'error': logging.ERROR,
        'critical': logging.CRITICAL
    }
    rootLogger.setLevel(lut[cnf.get('logging', 'log_level', fallback='INFO').lower()])

    logging.info('Started BorgBackupTimer.')

    os.chdir(script_dir)
    logging.debug('Changed directory to script dir "%s"' % (script_dir,))

    qapp = QApplication(sys.argv)

    bbackups = []
    for s in cnf.sections():
        if re.fullmatch(r'backup_\w+', s):
            logging.info('> Registered backup \'%s\'', s)
            bbackups.append(BBackup(
                name=s,
                timestamp_file=cnf.get(s, 'timestamp_file'),
                interval=cnf.getint(s, 'interval'),
                host=cnf.get(s, 'host'),
                borg_repo=cnf.get(s, 'borg_repo'),
                borg_rsh=cnf.get(s, 'borg_rsh', fallback='ssh'),
                borg_archive_name_template=cnf.get(s, 'borg_archive_name_template', fallback='%Y-%m-%d_%H-%M-%S'),
                borg_passphrase=cnf.get(s, 'borg_passphrase'),
                backup_directories=shlex.split(cnf.get(s, 'backup_directories')),
                borg_prune_args=shlex.split(cnf.get(s, 'borg_prune_args')),
                borg_args=shlex.split(cnf.get(s, 'borg_args', fallback='')),
                borg_stats=cnf.getboolean(s, 'borg_stats', fallback=True),
                borg_list_args=shlex.split(cnf.get(s, 'borg_list_args', fallback='')),
                restrict_to_environments=cnf.getboolean(s, 'restrict_to_environments', fallback=False),
                allowed_environments=shlex.split(cnf.get(s, 'allowed_environments', fallback=''))
            ))

    if not bbackups:
        logging.warning('No backups registered. There will be no action.')

    app = MainApp(qapp=qapp,
                  check_interval=cnf.getint('main', 'check_interval', fallback=30),
                  bbackups=bbackups,
                  environments=BEnv.from_config(cnf),
                  graphical_editor=shlex.split(cnf.get('main', 'graphical_editor', fallback='gedit')))

    sys.exit(qapp.exec_())


if __name__ == '__main__':
    main()
