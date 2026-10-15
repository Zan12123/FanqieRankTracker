#!/usr/bin/env python3
"""Simple HTTP server with UTF-8 charset headers for Chinese web novel dashboard."""
import http.server
import os
import signal
import sys

PORT = 8080

class UTF8HTTPHandler(http.server.SimpleHTTPRequestHandler):
    def guess_type(self, path):
        mime = super().guess_type(path)
        ext = os.path.splitext(path)[1].lower()
        if ext in ('.html', '.htm', '.json', '.js', '.css'):
            if 'charset=' not in mime:
                mime += '; charset=utf-8'
        return mime

    def end_headers(self):
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        super().end_headers()

if __name__ == '__main__':
    # Allow address reuse even if TIME_WAIT
    http.server.HTTPServer.allow_reuse_address = True
    os.system(f"lsof -ti :{PORT} | xargs kill -9 2>/dev/null")
    
    server = http.server.HTTPServer(('0.0.0.0', PORT), UTF8HTTPHandler)
    print(f'✅ 服务器已启动: http://localhost:{PORT}')
    print(f'📊 女频新书榜:   http://localhost:{PORT}/index.html')
    print(f'📊 女频阅读榜:   http://localhost:{PORT}/read.html')
    print(f'📊 男频新书榜:   http://localhost:{PORT}/male.html')
    print(f'📊 男频阅读榜:   http://localhost:{PORT}/male_read.html')
    print(f'📊 趋势分析(女): http://localhost:{PORT}/trend.html')
    print(f'📊 趋势分析(男): http://localhost:{PORT}/male_trend.html')
    
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
