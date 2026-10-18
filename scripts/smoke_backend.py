"""Start a temporary local backend, make real HTTP requests, and stop only that process."""
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='jbi-smoke-') as state:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    token=secrets.token_urlsafe(32)
    env=dict(os.environ,INSPECTION_DATA_DIR=state,INSPECTION_API_TOKEN=token)
    process=subprocess.Popen([sys.executable,'-m','uvicorn','backend.app:app','--host','127.0.0.1','--port',str(port),'--no-access-log'],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    base=f'http://127.0.0.1:{port}'
    try:
        for _ in range(100):
            if process.poll() is not None: raise RuntimeError('Backend failed to start')
            try:
                with urllib.request.urlopen(base+'/health',timeout=1) as response:
                    if json.load(response)['status']=='ok': break
            except OSError: time.sleep(.1)
        else: raise RuntimeError('Backend readiness timed out')
        request=urllib.request.Request(base+'/inspections',data=json.dumps({'title':'HTTP smoke test','inspection_date':'2026-10-15'}).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
        with urllib.request.urlopen(request,timeout=10) as response:
            record=json.load(response);assert response.status==201
        request=urllib.request.Request(base+'/inspections/'+record['id'],headers={'Authorization':'Bearer '+token})
        with urllib.request.urlopen(request,timeout=10) as response:
            assert json.load(response)['title']=='HTTP smoke test'
        print('Live HTTP smoke passed: startup, health, authenticated create/read, persistent record lookup.')
    finally:
        process.terminate()
        try: process.wait(timeout=10)
        except subprocess.TimeoutExpired: process.kill();process.wait()
