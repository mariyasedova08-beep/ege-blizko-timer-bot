#!/usr/bin/env python3
"""Loopback-only laboratory UI/chemistry sandbox. No bot imports or databases."""
import argparse
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import urlsplit
import zlib

MAX_BUNDLE = 8_000_000
MAX_CONTENT = 12_000_000


def unpack(encoded):
    packed = base64.b64decode(encoded, validate=True)
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    data = decoder.decompress(packed, MAX_CONTENT + 1)
    if len(data) > MAX_CONTENT or not decoder.eof or decoder.unused_data:
        raise ValueError('invalid or excessive compressed content')
    return data


def load_bundle(path):
    raw = Path(path).read_bytes()
    if len(raw) > MAX_BUNDLE:
        raise ValueError('bundle too large')
    bundle = json.loads(raw)
    if bundle.get('format') != 'ege-lab-sandbox-v1':
        raise ValueError('unknown bundle')
    html = unpack(bundle['html_gzip_base64'])
    payload_bytes = unpack(bundle['payload_gzip_base64'])
    if hashlib.sha256(html).hexdigest() != bundle['html_sha256'] or hashlib.sha256(payload_bytes).hexdigest() != bundle['payload_sha256']:
        raise ValueError('content digest mismatch')
    payload = json.loads(payload_bytes)
    if payload.get('ok') is not True or not payload['data'].get('preview'):
        raise ValueError('sandbox payload required')
    health = {'ok': True, 'sandbox': True, 'build': bundle['build'],
              'bundle_sha256': hashlib.sha256(raw).hexdigest(),
              'html_sha256': bundle['html_sha256'], 'payload_sha256': bundle['payload_sha256'],
              'coverage': payload['data']['coverage']}
    return html, payload, health


def handler_for(html, payload, health):
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def log_message(self, *args):
            pass  # No uploaded documents, credentials or request bodies in logs.

        def send(self, code, body, content_type='application/json; charset=utf-8'):
            self.send_response(code)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(body)

        def json(self, code, data):
            self.send(code, json.dumps(data, ensure_ascii=False).encode())

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == '/lab-app':
                return self.send(200, html, 'text/html; charset=utf-8')
            if path == '/healthz':
                return self.json(200, health)
            return self.json(404, {'ok': False, 'error': 'not_found'})

        def do_POST(self):
            if urlsplit(self.path).path != '/lab-app/api':
                return self.json(404, {'ok': False, 'error': 'not_found'})
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 50_000:
                    raise ValueError('length')
                request = json.loads(self.rfile.read(size))
                if not isinstance(request, dict):
                    raise ValueError('request object required')
            except (ValueError, UnicodeError):
                return self.json(400, {'ok': False, 'error': 'invalid_request'})
            action = request.get('action')
            if action == 'load':
                return self.json(200, payload)
            if action == 'event':
                return self.json(200, {'ok': True, 'stats': payload['data']['stats'], 'preview': True})
            return self.json(200, {'ok': False, 'error': 'not_available_in_isolated_sandbox'})
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--port', type=int, default=8768)
    args = parser.parse_args()
    html, payload, health = load_bundle(args.bundle)
    with ThreadingHTTPServer(('127.0.0.1', args.port), handler_for(html, payload, health)) as server:
        server.daemon_threads = True
        print(json.dumps(health), flush=True)
        server.serve_forever()


if __name__ == '__main__':
    main()
