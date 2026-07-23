#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BULK INSTAGRAM REELS DOWNLOADER
Created by : Alfinsr
License    : MIT License
Copyright (c) 2026 Alfinsr
"""

import sys
import os
import re
import time
import shutil
import itertools
import threading
from pathlib import Path
from typing import Optional, Dict, List, Tuple
import yt_dlp

# ======================== CONFIG ========================
BROWSER = "chrome"
DELAY_SECONDS = 4
OUTPUT_DIR = "downloads"
DEFAULT_TXT = "urls.txt"
TEST_URL = "https://www.instagram.com/reel/C7xqK1yI9xj/"

# ======================== COLORS ========================
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"

# ======================== LOGGER ========================
class SilentLogger:
    def debug(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass
    def info(self, msg): pass

# ======================== UTILS ========================
def clear_line(length: int = 140):
    print("\r" + " " * length + "\r", end="")

def sanitize_filename(text: str, max_length: int = 38) -> str:
    if not text:
        return "No Caption"
    text = re.sub(r'[\\/*?:"<>|]', "", text)
    text = re.sub(r'\s+', ' ', text).strip()
    return (text[:max_length].rstrip() + "...") if len(text) > max_length else text

def make_progress_bar(current: int, total: int, width: int = 18) -> str:
    if total <= 0:
        return "░" * width
    filled = int(width * current / total)
    return "█" * filled + "░" * (width - filled)

def translate_error(error: str) -> str:
    msg = error.lower()
    mapping = {
        "unsupported url": "Link tidak didukung / bukan Reels valid",
        "no video formats": "Link tidak didukung / bukan Reels valid",
        "rate-limit": "Rate limit - coba lagi nanti",
        "login page": "Rate limit - coba lagi nanti",
        "private": "Konten privat / butuh login",
        "login required": "Konten privat / butuh login",
        "not found": "Link tidak ditemukan atau sudah dihapus",
        "404": "Link tidak ditemukan atau sudah dihapus",
        "could not copy": "Gagal baca cookies - tutup browser",
        "cookie database": "Gagal baca cookies - tutup browser",
        "429": "Terlalu banyak request",
    }
    for key, value in mapping.items():
        if key in msg:
            return value
    return "Gagal mengunduh"

# ======================== COOKIES ========================
def get_cookie_opts(use_cookies: bool) -> Dict:
    if not use_cookies:
        return {}
    if Path("cookies.txt").exists():
        return {"cookiefile": "cookies.txt"}
    return {"cookiesfrombrowser": (BROWSER,)}

def ask_use_cookies() -> bool:
    print(f"\n{CYAN}Apakah ingin menggunakan cookies?{RESET}")
    print(f"{YELLOW}Sangat disarankan menggunakan cookies agar tidak mudah kena rate-limit.{RESET}")
    choice = input("Gunakan cookies? (Y/n): ").strip().lower()
    return choice in ("", "y", "yes")

def check_cookies(cookie_opts: Dict) -> bool:
    if not cookie_opts:
        print(f"{YELLOW}⚠️  Mode tanpa cookies (anonymous) - rawan rate-limit{RESET}")
        return True

    print(f"{YELLOW}⏳  Mengecek cookies...{RESET}", end="", flush=True)

    opts = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "logger": SilentLogger(),
        "skip_download": True,
        **cookie_opts
    }

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.extract_info(TEST_URL, download=False)
        print(f"\r{GREEN}✅  Cookies aktif dan siap digunakan{RESET}          ")
        return True
    except Exception:
        print(f"\r{RED}❌  Cookies tidak valid / sudah kedaluwarsa{RESET}          ")
        print("""
╭────────────────────────────────────────────────────────────╮
│  COOKIES ANDA SUDAH TIDAK BISA DIGUNAKAN                   │
├────────────────────────────────────────────────────────────┤
│  Cara mengambil cookies baru:                              │
│  1. Install ekstensi: Get cookies.txt LOCALLY              │
│  2. Buka Instagram → pastikan sudah LOGIN                  │
│  3. Klik ikon ekstensi → Export                            │
│  4. Simpan sebagai cookies.txt                             │
│  5. Taruh di folder yang sama dengan script                │
│  6. Jalankan ulang program ini                             │
╰────────────────────────────────────────────────────────────╯
""")
        return False

# ======================== PROGRESS ========================
class LiveStatus:
    def __init__(self, total: int):
        self.total = total
        self.success = 0
        self.failed = 0
        self.current = 0
        self.filename = "Menyiapkan..."
        self.is_error = False
        self.running = False
        self.failed_list: List[Tuple[int, str]] = []
        self.spinner = itertools.cycle("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏")
        self.lock = threading.Lock()

    def start(self):
        self.running = True
        threading.Thread(target=self._animate, daemon=True).start()

    def _animate(self):
        while self.running:
            with self.lock:
                spin = next(self.spinner)
                done = self.success + self.failed
                percent = int(100 * done / self.total) if self.total else 0
                bar = make_progress_bar(done, self.total)

                status = f"{RED}Gagal{RESET}: {self.filename}" if self.is_error else self.filename
                line = (f"\r  {spin}  [{self.current}/{self.total}] {status:<48} "
                        f"{bar} {percent:3d}%  ✅{self.success} ❌{self.failed}  ")
                print(line, end="", flush=True)
            time.sleep(0.1)

    def update(self, current: int, filename: str, is_error: bool = False):
        with self.lock:
            self.current = current
            self.filename = filename
            self.is_error = is_error

    def success_one(self):
        with self.lock:
            self.success += 1
            self.is_error = False

    def fail_one(self, index: int, reason: str):
        with self.lock:
            self.failed += 1
            self.failed_list.append((index, reason))
            self.is_error = True

    def stop(self):
        self.running = False
        time.sleep(0.12)
        clear_line()

# ======================== DOWNLOAD ========================
def download_one(url: str, index: int, total: int, cookie_opts: Dict, status: LiveStatus) -> Tuple[bool, str]:
    if not url.startswith(("https://www.instagram.com/", "https://instagram.com/")):
        return False, "Link bukan dari Instagram"

    silent = SilentLogger()
    base_opts = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "logger": silent,
        **cookie_opts
    }

    # Extract info
    try:
        with yt_dlp.YoutubeDL({**base_opts, "skip_download": True}) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        return False, translate_error(str(e))

    caption = info.get("description") or info.get("title") or info.get("fulltitle") or "No Caption"
    filename = f"Reels{index}. {sanitize_filename(caption)}"
    status.update(index, filename)

    # Download
    opts = {
        **base_opts,
        "outtmpl": f"{OUTPUT_DIR}/{filename}.%(ext)s",
        "format": "best[ext=mp4]/bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
        "prefer_ffmpeg": True,
    }

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
        return True, filename
    except Exception as e:
        return False, translate_error(str(e))

# ======================== MENU ACTIONS ========================
def single_download():
    use_cookies = ask_use_cookies()
    cookie_opts = get_cookie_opts(use_cookies)

    if not check_cookies(cookie_opts):
        return

    print("\n" + "─" * 60)
    url = input("Masukkan URL Instagram Reels: ").strip()
    if not url:
        print("❌ URL tidak boleh kosong!")
        return

    Path(OUTPUT_DIR).mkdir(exist_ok=True)
    print()

    status = LiveStatus(1)
    status.start()

    ok, result = download_one(url, 1, 1, cookie_opts, status)
    if ok:
        status.success_one()
    else:
        status.fail_one(1, result)
        status.update(1, result, is_error=True)

    status.stop()

    print("─" * 60)
    print(f"{'✅  Berhasil : ' + result + '.mp4' if ok else '❌  Gagal    : ' + result}")
    print(f"📂  Folder  : {OUTPUT_DIR}/")
    print()

def bulk_download():
    use_cookies = ask_use_cookies()
    cookie_opts = get_cookie_opts(use_cookies)

    if not check_cookies(cookie_opts):
        return

    print("\n" + "─" * 60)
    txt_file = input(f"Nama file .txt (kosongkan = {DEFAULT_TXT}): ").strip() or DEFAULT_TXT

    if not Path(txt_file).exists():
        print(f"❌ File '{txt_file}' tidak ditemukan!")
        return

    urls = [line.strip() for line in Path(txt_file).read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")]

    if not urls:
        print("❌ Tidak ada URL valid.")
        return

    Path(OUTPUT_DIR).mkdir(exist_ok=True)
    print(f"\n📁  Total : {len(urls)} reels")
    print(f"📂  Output: {OUTPUT_DIR}/")
    print()

    status = LiveStatus(len(urls))
    status.start()

    for i, url in enumerate(urls, 1):
        ok, result = download_one(url, i, len(urls), cookie_opts, status)

        if ok:
            status.success_one()
        else:
            status.fail_one(i, result)
            status.update(i, result, is_error=True)
            if "Rate limit" in result:
                time.sleep(25)

        if i < len(urls):
            time.sleep(DELAY_SECONDS)

    status.stop()

    print("─" * 60)
    print(f"✅  Berhasil : {status.success}")
    print(f"❌  Gagal    : {status.failed}")

    if status.failed_list:
        print("\nDaftar yang gagal:")
        for idx, reason in status.failed_list:
            print(f"  • Reels {idx} → {reason}")

    print(f"\n📂  Selesai  : {OUTPUT_DIR}/")
    print()

# ======================== MAIN ========================
def print_banner():
    print(r"""
    ____  _   _ _     _  __    ___ _   _ ____ _____  _    ____ ____      _    __  __ 
   | __ )| | | | |   | |/ /   |_ _| \ | / ___|_   _|/ \  / ___|  _ \    / \  |  \/  |
   |  _ \| | | | |   | ' /     | ||  \| \___ \ | | / _ \| |  _| |_) |  / _ \ | |\/| |
   | |_) | |_| | |___| . \     | || |\  |___) || |/ ___ \ |_| |  _ <  / ___ \| |  | |
   |____/ \___/|_____|_|\_\   |___|_| \_|____/ |_/_/   \_\____|_| \_\/_/   \_\_|  |_|
                                                                                     
                      BULK INSTAGRAM REELS DOWNLOADER
                                 by Alfinsr
    """)
    print("─" * 90 + "\n")

def main():
    while True:
        print_banner()

        if not shutil.which("ffmpeg"):
            print("❌ ffmpeg tidak ditemukan di PATH!")
            sys.exit(1)

        print("""
╭──────────────────────────────────────╮
│           MAIN MENU                  │
├──────────────────────────────────────┤
│  1. Single Link Download             │
│  2. Bulk Download                    │
│  3. Exit                             │
╰──────────────────────────────────────╯
""")

        choice = input("Pilih menu [1-3]: ").strip()

        if choice == "1":
            single_download()
        elif choice == "2":
            bulk_download()
        elif choice == "3":
            print("\n👋 Terima kasih! Sampai jumpa.\nCreated by Alfinsr\n")
            break
        else:
            print("❌ Pilihan tidak valid!")
            time.sleep(1)
            continue

        input("\nTekan Enter untuk kembali ke menu...")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Dibatalkan oleh user.\nCreated by Alfinsr\n")