import re
import shlex
from funcs import *
import logging


class BEnv:
    def __init__(self, name, match_local_ip_address, match_global_ip_address, match_ssid, ping_hosts, allow_other, allow_wifi):
        self.name = name
        self.match_local_ip_address = match_local_ip_address
        self.match_global_ip_adress = match_global_ip_address
        self.match_ssid = match_ssid
        self.ping_hosts = ping_hosts
        self.allow_other = allow_other
        self.allow_wifi = allow_wifi

    def check(self):
        logging.debug('Running env check for \'%s\'...', self.name)
        ssid = get_ssid()
        logging.debug('Current SSID is %s', ssid)
        if (self.allow_wifi and ssid is not None and re.fullmatch(self.match_ssid, ssid)) or (self.allow_other and ssid is None):
            logging.debug('Wifi allowed and SSID matched \'%s\' or other allowed and SSID is None.', self.match_ssid)
            # wifi and correct ssid or no wifi and other allowed
            ips = get_local_ips()
            gip = get_global_ip()
            logging.debug('Current local ips are %s', str(ips))
            logging.debug('Current global ip is %s', str(gip))
            if any([re.fullmatch(self.match_local_ip_address, ip) for ip in ips]):
                logging.debug('At least one local IP matched the pattern \'%s\'', self.match_local_ip_address)
                # at least one ip matches
                if re.fullmatch(self.match_global_ip_adress, gip):
                    logging.debug('The global ip matched the pattern \'%s\'', self.match_global_ip_adress)
                    # global ip matches
                    for host in self.ping_hosts:
                        logging.debug('Ping required host \'%s\'...', host)
                        # check all required hosts
                        if not check_host(host):
                            return False
                    # everything ok
                    logging.debug('Requirements of \'%s\' satisfied.', self.name)
                    return True
        return False

    @staticmethod
    def from_config(cnf):
        lst = {}
        for sec in cnf.sections():
            if re.fullmatch(r'env_\w+', sec):
                logging.info('> Registered environment \'%s\'', sec)
                lst[sec] = BEnv(
                        name=sec,
                        match_local_ip_address=cnf.get(sec, 'match_ip_address', fallback='.+'),
                        match_global_ip_address=cnf.get(sec, 'match_public_ip_address', fallback='.+'),
                        match_ssid=cnf.get(sec, 'match_ssid', fallback='.+'),
                        ping_hosts=shlex.split(cnf.get(sec, 'ping_hosts', fallback='')),
                        allow_wifi=cnf.getboolean(sec, 'allow_wifi', fallback=False),
                        allow_other=cnf.getboolean(sec, 'allow_other', fallback=False)
                    )
        return lst

