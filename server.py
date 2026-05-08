#!/usr/bin/env python3
"""
Francis Jazz FM — Local server with B站 audio proxy
Usage: python3 server.py
Then open: http://localhost:8765

This server:
1. Serves static files (index.html, audio/)
2. Proxies B站 API to avoid CORS — allows real volume control
"""
import http.server, urllib.request, urllib.parse, json, socketserver, os, sys

PORT = int(os.environ.get('PORT', 8765))
HOST = '0.0.0.0'
ROOT = os.path.dirname(os.path.abspath(__file__))

class ProxyHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        # Proxy B站 playurl API
        if parsed.path == '/api/bili/playurl':
            qs = urllib.parse.parse_qs(parsed.query)
            bvid = qs.get('bvid', [''])[0]
            cid = qs.get('cid', [''])[0]
            if bvid and cid:
                url = f'https://api.bilibili.com/x/player/playurl?bvid={bvid}&cid={cid}&fnval=1&qn=0&platform=html5'
                req = urllib.request.Request(url, headers={
                    'User-Agent': 'Mozilla/5.0',
                    'Referer': 'https://www.bilibili.com'
                })
                try:
                    resp = urllib.request.urlopen(req, timeout=10)
                    data = json.loads(resp.read())
                    durl = data.get('data', {}).get('durl', [])
                    if durl and durl[0]:
                        self.send_response(200)
                        self.send_header('Content-Type', 'application/json')
                        self.send_header('Access-Control-Allow-Origin', '*')
                        self.end_headers()
                        self.wfile.write(json.dumps({'url': durl[0]['url']}).encode())
                        return
                except Exception as e:
                    self.send_error(502, str(e))
                    return
            self.send_error(400, 'Missing bvid/cid')
            return

        # Proxy B站 video info (for cid lookup)
        if parsed.path == '/api/bili/info':
            qs = urllib.parse.parse_qs(parsed.query)
            bvid = qs.get('bvid', [''])[0]
            if bvid:
                url = f'https://api.bilibili.com/x/web-interface/view?bvid={bvid}'
                req = urllib.request.Request(url, headers={
                    'User-Agent': 'Mozilla/5.0',
                    'Referer': 'https://www.bilibili.com'
                })
                try:
                    resp = urllib.request.urlopen(req, timeout=10)
                    data = json.loads(resp.read())
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(json.dumps(data).encode())
                    return
                except Exception as e:
                    self.send_error(502, str(e))
                    return
            self.send_error(400, 'Missing bvid')
            return

        # Proxy B站 audio stream (MP4)
        if parsed.path == '/api/bili/stream':
            qs = urllib.parse.parse_qs(parsed.query)
            mp4url = qs.get('url', [''])[0]
            if mp4url:
                try:
                    req = urllib.request.Request(mp4url, headers={
                        'User-Agent': 'Mozilla/5.0',
                        'Referer': 'https://www.bilibili.com'
                    })
                    resp = urllib.request.urlopen(req, timeout=30)
                    self.send_response(200)
                    self.send_header('Content-Type', 'video/mp4')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.send_header('Accept-Ranges', 'bytes')
                    length = resp.getheader('Content-Length')
                    if length:
                        self.send_header('Content-Length', length)
                    self.end_headers()
                    # Stream in chunks
                    while True:
                        chunk = resp.read(65536)
                        if not chunk: break
                        self.wfile.write(chunk)
                    return
                except Exception as e:
                    self.send_error(502, str(e))
                    return
            self.send_error(400, 'Missing url')
            return

        # Relay jazz radio stream (proxy to avoid network restrictions)
        if parsed.path == '/api/stream':
            JAZZ_STREAM = 'https://icecast.radiofrance.fr/fipjazz-midfi.mp3'
            # Fallback streams
            FALLBACKS = [
                'https://jazzradio.ice.infomaniak.ch/jazzradio-high.mp3',
                'https://jazz.streamr.ru/jazz-64.mp3',
            ]
            for url in [JAZZ_STREAM] + FALLBACKS:
                try:
                    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                    resp = urllib.request.urlopen(req, timeout=15)
                    self.send_response(200)
                    self.send_header('Content-Type', 'audio/mpeg')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.send_header('Cache-Control', 'no-cache')
                    self.send_header('Connection', 'keep-alive')
                    self.end_headers()
                    while True:
                        chunk = resp.read(32768)
                        if not chunk: break
                        try: self.wfile.write(chunk)
                        except: break
                    return
                except Exception as e:
                    print(f"  Stream failed: {url} -> {e}")
                    continue
            self.send_error(502, 'All streams unavailable')
            return

        # Default: serve static files
        super().do_GET()

    def log_message(self, format, *args):
        # Reduce log noise
        if '/api/bili/' in str(args[0]):
            print(f"  [B站 API] {args[0]}")
        elif '/api/stream' in str(args[0]):
            print(f"  [Stream] Client connected")
        elif args[0].startswith('GET /audio/'):
            pass
        else:
            super().log_message(format, *args)

if __name__ == '__main__':
    print(f"""
╔══════════════════════════════════════════╗
║     🎵 Francis Jazz FM Server 🎵        ║
╠══════════════════════════════════════════╣
║  Local:  http://localhost:{PORT}          ║
║  Network: http://0.0.0.0:{PORT}           ║
║                                          ║
║  ✓ Static files served                   ║
║  ✓ B站 API proxy (no CORS)               ║
║  ✓ Full volume control                   ║
║                                          ║
║  Press Ctrl+C to stop                    ║
╚══════════════════════════════════════════╝
""")
    with socketserver.TCPServer((HOST, PORT), ProxyHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped.")
