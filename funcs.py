import subprocess
import shlex
import re


def get_ssid():
    p = subprocess.Popen(['nmcli', '-t', '-f', 'active,ssid', 'dev', 'wifi'], stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, bufsize=1, close_fds=True)
    try:
        stdout = p.communicate(timeout=0.5)[0]
    except subprocess.TimeoutExpired:
        p.kill()
        return None
    else:
        cmd_output = stdout.decode()
        rexpr = re.compile(r'yes:(.+)\n')
        match = rexpr.search(cmd_output)
        if match:
            ssid = match.groups()[0]
        else:
            ssid = None

        return ssid


def check_host(host):
    p = subprocess.Popen(['ping', '-c', '1', '-W', '1', host], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    p.wait()
    return p.returncode == 0


def getips():
    local = ['::1', '127.0.0.1']
    proc = subprocess.Popen(shlex.split('ip addr show'), stdout=subprocess.PIPE)
    stdout = proc.communicate()[0].decode().splitlines()
    addrs = []
    for line in stdout:
        match = re.match(r'^\s*inet6?\s+(?P<ip>((\d{1,3}\.){3}\d{1,3})|([:abcdef\d]+)).*$', line)
        if match is not None:
            addrs.append(match.groupdict()['ip'])

    return list(set(addrs) - set(local))
