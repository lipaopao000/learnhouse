"""Operator-only helper. Credentials stay in the existing private deploy file."""
import json
from pathlib import Path
import urllib.parse
import urllib.request


class Client:
    def __init__(self, deployment_dir):
        self.base = 'https://syyedu.toofun.fun'
        self.token = None
        env = json.loads((Path(deployment_dir) / 'config/env.private.json').read_text())
        result = self.request('/api/v1/auth/login', {
            'username': env['LEARNHOUSE_INITIAL_ADMIN_EMAIL'],
            'password': env['LEARNHOUSE_INITIAL_ADMIN_PASSWORD'], 'org_slug': 'default'}, form=True)
        self.token = result['tokens']['access_token']

    def request(self, path, data=None, *, form=False, method=None):
        headers = {'Origin': self.base}
        if self.token:
            headers['Authorization'] = 'Bearer ' + self.token
        if data is not None:
            raw = urllib.parse.urlencode(data).encode() if form else json.dumps(data).encode()
            headers['Content-Type'] = 'application/x-www-form-urlencoded' if form else 'application/json'
        else:
            raw = None
        request = urllib.request.Request(self.base + path, data=raw, headers=headers, method=method)
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read()
            return json.loads(body) if body else None
