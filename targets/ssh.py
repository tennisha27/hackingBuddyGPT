import re

from fabric import Connection
from invoke import Responder
from io import StringIO

def get_ssh_connection(ip, user, password):

    if ip != '' and user != '' and password != '':
        return SSHHostConn(ip, user, password)
    else:
        raise Exception("Please configure SSH through environment variables (TARGET_IP, TARGET_USER, TARGET_PASSWORD)")

class SSHHostConn:

    def __init__(self, host, username, password):
        self.host = host
        self.username = username
        self.password = password

    def connect(self):
        # create the SSH Connection
        conn = Connection(
            "{username}@{ip}:{port}".format(
                username=self.username,
                ip=self.host,
                port=22,
            ),
            connect_kwargs={"password": self.password},
        )
        self.conn=conn
        self.conn.open()

    def run(self, cmd):
        gotRoot = False
        sudopass = Responder(
            pattern=r'\[sudo\] password for ' + self.username + ':',
            response=self.password + '\n',
        )
        
        out = StringIO()
        try:
            resp = self.conn.run(cmd, pty=True, warn=True, out_stream=out, watchers=[sudopass], timeout=5)
        except Exception as e:
            print("TIMEOUT!")
        out.seek(0)
        tmp = ""
        lastline = ""
        for line in out.readlines():
            if not line.startswith('[sudo] password for ' + self.username + ':'):
                line = line.replace("\r", "")
                lastline = line
                tmp = tmp + line

        # remove ansi shell codes
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        lastline = ansi_escape.sub('', lastline)

        if lastline.startswith("# "):
            gotRoot = True
        if lastline.startswith('root@debian:'):
            gotRoot = True
        if lastline.startswith("bash-5.2# "):
            gotRoot = True
        return tmp, gotRoot
