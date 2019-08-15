import datetime
import logging
import os
import re
import shlex
import subprocess
import time

from funcs import check_host


class BBackup:
    def __init__(
            self,
            name,
            restrict_to_environments,
            allowed_environments,
            timestamp_file,
            interval,
            host,
            borg_repo,
            borg_passphrase,
            backup_directories,
            borg_prune_args,
            borg_list_args=(),
            borg_stats=True,
            borg_archive_name_template="%Y-%m-%d_%H-%M-%S",
            borg_rsh='ssh',
            borg_args=()
    ):
        self.name = name
        self.timestamp_file = timestamp_file
        self.interval = interval
        self.host = host
        self.borg_repo = borg_repo
        self.borg_passphrase = borg_passphrase
        self.borg_rsh = borg_rsh
        self.borg_archive_name_template = borg_archive_name_template
        self.backup_directories = backup_directories
        self.borg_prune_args = borg_prune_args
        self.borg_args = borg_args
        self.borg_list_args = borg_list_args
        self.borg_stats = borg_stats
        self.restrict_to_environments = restrict_to_environments
        self.allowed_environments = allowed_environments
        self.list = None

    def connect_check(self):
        return check_host(self.host)

    def env_check(self, valid_envs):
        if self.restrict_to_environments:
            for e in self.allowed_environments:
                if e in [e.name for e in valid_envs]:
                    return True
            return False
        else:
            return True

    def run(self):
        env = os.environ.copy()
        env['BORG_REPO'] = self.borg_repo
        env['BORG_RSH'] = self.borg_rsh
        env['BORG_PASSPHRASE'] = self.borg_passphrase

        now = time.time()

        archive_name = ('::{:%s}' % (self.borg_archive_name_template,)).format(datetime.datetime.fromtimestamp(now))
        params = ['borg', 'create'] + (['--stats'] if self.borg_stats else []) + [archive_name] + self.borg_args
        params += self.backup_directories

        tokens = [shlex.quote(token) for token in params]
        logging.info('Running \'%s\'', ' '.join(tokens))

        p = subprocess.Popen(
            params,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env
        )
        stdout, stderr = p.communicate()
        stdout_ = stdout.decode()
        stderr_ = stderr.decode()
        if stdout_ or stderr_:
            logging.info('BORG create output:\n' + stdout_ + stderr_)
        if p.returncode == 0:
            params = ['borg', 'prune'] + (['--stats'] if self.borg_stats else []) + self.borg_prune_args

            tokens = [shlex.quote(token) for token in params]
            logging.info('Running \'%s\'', ' '.join(tokens))

            p = subprocess.Popen(
                params,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env
            )
            stdout, stderr = p.communicate()
            stdout_ = stdout.decode()
            stderr_ = stderr.decode()
            if stdout_ or stderr_:
                logging.info('BORG prune output:\n' + stdout_ + stderr_)
            self.store_timestamp(now)
            return True
        else:
            return False

    def run_list(self):
        env = os.environ.copy()
        env['BORG_REPO'] = self.borg_repo
        env['BORG_RSH'] = self.borg_rsh
        env['BORG_PASSPHRASE'] = self.borg_passphrase

        params = ['borg', 'list'] + self.borg_list_args

        tokens = [shlex.quote(token) for token in params]
        logging.info('Running \'%s\'', ' '.join(tokens))

        p = subprocess.Popen(
            params,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env
        )
        stdout, stderr = p.communicate()
        stdout_ = stdout.decode()
        stderr_ = stderr.decode()
        if stdout_ or stderr_:
            logging.info('BORG list output:\n' + stdout_ + stderr_)
        self.list = stdout_ + stderr_
        return p.returncode == 0

    def check(self):
        try:
            with open(self.timestamp_file, 'r') as f:
                backup_ts = int(f.read())
                now_ts = time.time()
                return (now_ts - backup_ts) > self.interval
        except FileNotFoundError:
            return True

    def store_timestamp(self, timestamp):
        with open(self.timestamp_file, 'w') as f:
            f.write(str(int(timestamp)))

    @staticmethod
    def from_config(cnf):
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
        return bbackups
