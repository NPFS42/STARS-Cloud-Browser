#!/usr/bin/env python3
"""Start only the dedicated STARS browser container after scoped egress rules.

No shell, no systemctl or admin bypass. Scheduled by the existing authorized
VPS MCP cron service, which is later than Docker initialization and makes
browser non-restarting directly at Docker boot safe.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path('/opt/stars-cloud-browser')
COMPOSE = str(ROOT / 'compose.yaml')
NAME = 'stars-cloud-browser-browser-1'
NETWORK = 'stars-cloud-browser_browser-egress'
IMAGE = 'sha256:6eeb1bec3cc6bb8fa78c9121468a5d781964969c916e1cccd1fe1f22c1010dc9'
SECCOMP = '05f1eb585f560ad4c1301b1be3e3fd560bf77c59b6abaee65cb53697767f8ee5'

def exec_checked(*argv):
    return subprocess.run(argv, check=True, capture_output=True, text=True, timeout=75).stdout

def docker_json(*args):
    return json.loads(exec_checked('/usr/bin/docker', *args))

def main():
    if os.geteuid():
        raise RuntimeError('root required')
    secret = ROOT / '.env'
    if not secret.is_file() or secret.stat().st_mode & 0o077:
        raise RuntimeError('secret file missing or readable by other users')
    digest = hashlib.sha256((ROOT/'security/seccomp_profile.json').read_bytes()).hexdigest()
    if digest != SECCOMP:
        raise RuntimeError('seccomp profile changed: stop until revalidated')
    image = docker_json('image', 'inspect', 'stars-cloud-browser:0.4.1-local')[0]
    if image['Id'] != IMAGE:
        raise RuntimeError('browser image changed: stop until revalidated')
    try:
        net=docker_json('network','inspect',NETWORK)[0]
    except subprocess.CalledProcessError:
        # Create but do not start the container; network policy is applied next.
        exec_checked('/usr/bin/docker','compose','-f',COMPOSE,'create','--no-build')
        net=docker_json('network','inspect',NETWORK)[0]
    configs=net['IPAM']['Config']
    if len(configs)!=1 or configs[0]['Subnet']!='172.30.251.0/28':
        raise RuntimeError('unexpected browser network CIDR')
    try:
        c=docker_json('inspect',NAME)[0]
    except subprocess.CalledProcessError:
        exec_checked('/usr/bin/docker','compose','-f',COMPOSE,'create','--no-build')
        c=docker_json('inspect',NAME)[0]
    h=c['HostConfig']
    ports=h['PortBindings']
    if h['RestartPolicy']['Name']!='no' or ports != {'8811/tcp':[{'HostIp':'127.0.0.1','HostPort':'8811'}]}:
        raise RuntimeError('auto-restart or published-port mismatch')
    if h['NetworkMode'] != NETWORK:
        raise RuntimeError('unexpected container network')
    if c['Image'] != IMAGE:
        raise RuntimeError('unexpected running container image')
    # Never start a stopped browser unless the scoped egress ACL is effective.
    exec_checked('/usr/bin/python3', str(ROOT/'security/firewall.py'),'--apply')
    if c['State']['Running']:
        print('STARS_BROWSER_GUARDED_RUNNING')
        return
    exec_checked('/usr/bin/docker','compose','-f',COMPOSE,'up','-d','--no-build')
    print('STARS_BROWSER_GUARDED_STARTED')

if __name__=='__main__':
    try:
        main()
    except Exception as exc:
        print('STARS_BROWSER_GUARD_FAILED:', type(exc).__name__,str(exc)[:300],file=sys.stderr)
        sys.exit(2)