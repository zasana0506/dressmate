# -*- coding: utf-8 -*-
"""一键启动：起服务 → 等就绪 → 打开浏览器。双击「一键启动.bat」即可。"""
import os
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser

BASE = os.path.dirname(os.path.abspath(__file__))
PORT = 8848
URL = f"http://127.0.0.1:{PORT}"


def alive(timeout=1.0):
    try:
        with urllib.request.urlopen(URL + "/api/health", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return ""
    finally:
        s.close()


def main():
    if alive():
        print("服务已经在运行了，直接打开页面。")
    else:
        print("正在启动服务…（会弹出一个最小化的黑色窗口，那个就是服务，别关它）")
        flags = 0
        if os.name == "nt":
            flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        subprocess.Popen([sys.executable, os.path.join(BASE, "server.py"), str(PORT)],
                         cwd=BASE, creationflags=flags)
        ok = False
        for _ in range(60):
            time.sleep(0.3)
            if alive():
                ok = True
                break
        if not ok:
            print("启动超时。请手动在该目录执行：python server.py")
            input("按回车关闭…")
            return
        print("服务已就绪。")

    print(f"电脑访问： {URL}")
    ip = lan_ip()
    if ip:
        print(f"手机访问： http://{ip}:{PORT}   （手机和电脑要连同一个 WiFi）")
    webbrowser.open(URL)
    print("\n这个窗口可以关掉，服务在另一个窗口里继续跑。")
    time.sleep(2)


if __name__ == "__main__":
    main()
