"""Build locally; optionally forward this machine's supported proxy and public CA bundle."""
import argparse
import os
import socket
import ssl
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--environment-proxy',action='store_true')
parser.add_argument('--docker-config')
parser.add_argument('--tag',default='jbi-inspections:local')
args=parser.parse_args()
command=['docker']+(['--config',args.docker_config] if args.docker_config else [])+['build']
if args.environment_proxy:
    proxy=urlsplit(os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy') or '')
    if not proxy.hostname: raise SystemExit('No configured HTTPS proxy is available')
    command+=['--network=host','--add-host',proxy.hostname+':'+socket.gethostbyname(proxy.hostname)]
    for name in ['HTTP_PROXY','HTTPS_PROXY','NO_PROXY']:
        if os.environ.get(name): command+=['--build-arg',name]
    bundle=ssl.get_default_verify_paths().cafile
    if bundle: command+=['--secret','id=build_ca,src='+bundle]
command+=['-f','backend/Dockerfile','--tag',args.tag,'.']
raise SystemExit(subprocess.run(command,cwd=Path(__file__).resolve().parents[1]).returncode)
