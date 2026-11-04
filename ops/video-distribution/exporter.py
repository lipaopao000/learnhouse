"""Private, read-only video export for the origin cache; never user-facing.

Only database-referenced MP4/WebM files are listed, including drafts. A
column-scoped read-only PostgreSQL role supplies metadata, not user records.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import re
import secrets
import urllib.parse
import psycopg2

CONFIG = json.loads(Path('/run/config/exporter.private.json').read_text())
ROOT = Path('/content').resolve()


def file_for_uri(uri):
    parts = urllib.parse.unquote(uri).strip('/').split('/')
    if any(p in ('', '.', '..') or '\\' in p or '\x00' in p for p in parts):
        return None
    if parts[:4] == ['api', 'v1', 'stream', 'video'] and len(parts) == 8:
        org, course, activity, filename = parts[4:]
        relative = ['orgs', org, 'courses', course, 'activities', activity, 'video', filename]
    elif parts[:4] == ['api', 'v1', 'stream', 'block'] and len(parts) == 9:
        org, course, activity, block, filename = parts[4:]
        relative = ['orgs', org, 'courses', course, 'activities', activity, 'dynamic', 'blocks', 'videoBlock', block, filename]
    else:
        return None
    target = ROOT.joinpath(*relative).resolve()
    if not target.is_relative_to(ROOT) or target.suffix.lower() not in ('.mp4', '.webm') or not target.is_file():
        return None
    return target


def manifest():
    with psycopg2.connect(CONFIG['db_dsn'], connect_timeout=5) as connection:
        with connection.cursor() as cursor:
            cursor.execute('''SELECT o.org_uuid,c.course_uuid,a.activity_uuid,a.content
                FROM activity a JOIN course c ON c.id=a.course_id
                JOIN organization o ON o.id=c.org_id WHERE o.id=%s''', (CONFIG['org_id'],))
            rows = []
            for org, course, activity, content in cursor.fetchall():
                content = content or {}
                filename = content.get('filename') if isinstance(content, dict) else None
                if filename and isinstance(filename, str):
                    rows.append('/api/v1/stream/video/' + '/'.join(urllib.parse.quote(v, safe='') for v in [org, course, activity, filename]))
            cursor.execute('''SELECT o.org_uuid,c.course_uuid,a.activity_uuid,b.block_uuid,b.content
                FROM block b JOIN activity a ON a.id=b.activity_id
                JOIN course c ON c.id=b.course_id JOIN organization o ON o.id=c.org_id
                WHERE o.id=%s AND b.block_type='BLOCK_VIDEO' ''', (CONFIG['org_id'],))
            for org, course, activity, block, content in cursor.fetchall():
                content = content or {}
                name = content.get('file_id')
                extension = content.get('file_format')
                filename = (name + '.' + extension) if isinstance(name, str) and isinstance(extension, str) else None
                if filename and isinstance(filename, str):
                    rows.append('/api/v1/stream/block/' + '/'.join(urllib.parse.quote(v, safe='') for v in [org, course, activity, block, filename]))
    items = []
    for uri in sorted(set(rows)):
        target = file_for_uri(uri)
        if target:
            stat = target.stat()
            items.append({'uri': uri, 'bytes': stat.st_size, 'mtime_ns': stat.st_mtime_ns})
    items.sort(key=lambda item: item['mtime_ns'], reverse=True)
    return {'videos': items}


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *args):
        pass  # Do not record request headers or private video identifiers.

    def error(self, code):
        self.send_response(code)
        self.send_header('Content-Length', '0')
        self.end_headers()

    def do_HEAD(self):
        self.serve(False)

    def do_GET(self):
        self.serve(True)

    def serve(self, body):
        self.connection.settimeout(60)
        uri = urllib.parse.urlsplit(self.path).path
        if uri == '/health':
            self.error(200)
            return
        if not secrets.compare_digest(self.headers.get('X-LearnHouse-Origin-Key', ''), CONFIG['read_key']):
            self.error(403)
            return
        if uri == '/manifest':
            try:
                data = json.dumps(manifest()).encode()
            except Exception:
                self.error(503)
                return
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            if body:
                self.wfile.write(data)
            return
        target = file_for_uri(uri)
        if target is None:
            self.error(404)
            return
        size = target.stat().st_size
        start, end = 0, size - 1
        header = self.headers.get('Range') if body else None
        if header:
            match = re.fullmatch(r'bytes=(\d+)-(\d*)', header)
            if not match or int(match[1]) >= size:
                self.error(416)
                return
            start = int(match[1])
            end = min(int(match[2]) if match[2] else size-1, size-1)
            if end < start:
                self.error(416)
                return
        self.send_response(206 if header else 200)
        self.send_header('Content-Type', mimetypes.guess_type(target.name)[0] or 'video/mp4')
        self.send_header('Content-Length', str(max(0, end-start+1)))
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Cache-Control', 'private, no-store')
        if header:
            self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        self.end_headers()
        if body:
            try:
                with target.open('rb') as stream:
                    stream.seek(start)
                    remaining = end-start+1
                    while remaining > 0:
                        data = stream.read(min(131072, remaining))
                        if not data:
                            break
                        self.wfile.write(data)
                        remaining -= len(data)
            except (BrokenPipeError, ConnectionResetError):
                pass


ThreadingHTTPServer(('0.0.0.0', 8817), Handler).serve_forever()
