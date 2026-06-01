#!/usr/bin/env python3
"""
AI小说创作工坊 - 移动版Web服务器
手机浏览器访问即可使用
"""

import http.server
import socketserver
import os
import socket
import webbrowser
from pathlib import Path

PORT = 8080
DIRECTORY = Path(__file__).parent / "dist"

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DIRECTORY), **kwargs)
    
    def end_headers(self):
        # 添加PWA所需的头
        self.send_header('Service-Worker-Allowed', '/')
        super().end_headers()

def get_local_ip():
    """获取本机IP地址"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

def main():
    ip = get_local_ip()
    url = f"http://{ip}:{PORT}"
    
    print("=" * 50)
    print("AI小说创作工坊 - 移动版")
    print("=" * 50)
    print()
    print(f"本地访问: http://localhost:{PORT}")
    print(f"手机访问: {url}")
    print()
    print("手机使用方法:")
    print("1. 确保手机和电脑在同一WiFi网络")
    print(f"2. 手机浏览器访问: {url}")
    print("3. 点击浏览器菜单 -> 添加到主屏幕")
    print("4. 即可像App一样使用")
    print()
    
    # 生成简单二维码
    print(f"手机浏览器访问: {url}")
    print("(安装qrcode库可显示二维码: pip install qrcode)")
    
    print()
    print("按 Ctrl+C 停止服务器")
    print("=" * 50)
    
    # 启动服务器
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n服务器已停止")

if __name__ == "__main__":
    main()
