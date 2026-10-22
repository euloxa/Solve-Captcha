#!/usr/bin/env python3
import os
import sys
import json
import time
import subprocess
import requests
import base64
from datetime import datetime
from typing import List, Tuple, Optional

VIA_PACKAGES = [
    "mark.via.gp", "mark.via.gq", "mark.via.gr", "mark.via.gs", "mark.via.gt",
    "mark.via.gu", "mark.via.gv", "mark.via.gw", "mark.via.gx", "mark.via.gy"
]

CONFIG = {
    "funbypass_api_key": "", 
    "funbypass_api_url": "https://api.funbypass.com",
    "roblox_login_url": "https://www.roblox.com/login",
    "roblox_funcaptcha_key": "476068BF-9607-4799-B53D-966BE98E2B81",
    "roblox_subdomain": "roblox-api.arkoselabs.com",
    "proxy_url": "", 
    "delay_after_launch": 5,
    "delay_after_input": 1,
    "delay_between_accounts": 120,
    "username_field": [540, 400],
    "password_field": [540, 500],
    "login_button": [540, 600],
    "max_captcha_retries": 1
}

def run_command(cmd: str, use_root: bool = True) -> Tuple[bool, str]:
    try:
        if use_root:
            cmd = f"su -c '{cmd}'"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        return result.returncode == 0, result.stdout.strip()
    except Exception as e:
        return False, str(e)

def log(message: str):
    timestamp = datetime.now().strftime('%H:%M:%S')
    print(f"[{timestamp}] {message}")

def load_accounts(filename: str) -> List[Tuple[str, str]]:
    accounts = []
    if not os.path.exists(filename):
        log(f"❌ File not found: {filename}")
        return accounts
    with open(filename, 'r') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if ':' not in line:
                log(f"⚠️  Line {line_num}: Invalid format (skip)")
                continue
            parts = line.split(':', 1)
            username, password = parts[0].strip(), parts[1].strip()
            if username and password:
                accounts.append((username, password))
    return accounts

def get_roblox_blob(username: str, password: str) -> Tuple[Optional[str], Optional[str]]:
    try:
        log("  → Fetching Roblox Blob...")
        session = requests.Session()
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": "https://www.roblox.com",
            "Referer": "https://www.roblox.com/"
        }
        
        session.get("https://www.roblox.com/", headers=headers, timeout=15)
        
        r_csrf = session.post("https://auth.roblox.com/v2/login", headers=headers, json={}, timeout=15)
        csrf_token = r_csrf.headers.get("x-csrf-token")
        
        if not csrf_token:
            log("  ❌ Gagal mendapatkan CSRF Token.")
            return None, None
        
        log("  ✅ CSRF Token didapat.")
        
        headers["X-CSRF-Token"] = csrf_token
        login_payload = {"ctype": "Username", "cvalue": username, "password": password}
        r = session.post("https://auth.roblox.com/v2/login", json=login_payload, headers=headers, timeout=15)
        
        log(f"  → Status Code Roblox: {r.status_code}")

        cookies_str = "; ".join([f"{k}={v}" for k, v in session.cookies.get_dict().items()])

        metadata_b64 = r.headers.get("rblx-challenge-metadata") or r.headers.get("Rblx-Challenge-Metadata")
        
        if metadata_b64:
            padding_needed = len(metadata_b64) % 4
            if padding_needed:
                metadata_b64 += "=" * (4 - padding_needed)
            
            try:
                try:
                    decoded = base64.b64decode(metadata_b64).decode('utf-8')
                except Exception:
                    decoded = base64.urlsafe_b64decode(metadata_b64).decode('utf-8')
                    
                metadata = json.loads(decoded)
                log(f"  [DEBUG] Isi Metadata: {json.dumps(metadata)[:300]}...")
                
                blob = metadata.get("dataExchangeBlob")
                if blob:
                    log(f"  ✅ Blob ditemukan di Header! (Panjang: {len(blob)})")
                    return blob, cookies_str
                else:
                    log(f"  ❌ 'dataExchangeBlob' tidak ada di metadata! Keys: {list(metadata.keys())}")
            except Exception as e:
                log(f"  ❌ Gagal decode metadata header: {e}")
        else:
            log("  ❌ Header 'rblx-challenge-metadata' tidak ditemukan di response!")

        try:
            body_json = r.json()
            blob = body_json.get("data", {}).get("dataExchangeBlob") or body_json.get("dataExchangeBlob")
            if blob:
                log(f"  ✅ Blob ditemukan di Body! (Panjang: {len(blob)})")
                return blob, cookies_str
        except Exception:
            pass

        log(f"  ❌ Blob tidak ada. Respon Roblox: {r.text[:200]}")
        return None, None
    except Exception as e:
        log(f"  ❌ Error ambil blob: {e}")
        return None, None

def solve_captcha(username: str, password: str) -> Tuple[bool, Optional[str]]:
    try:
        blob, cookies_str = get_roblox_blob(username, password)
        if not blob:
            return False, "Gagal mendapatkan blob dari Roblox (Cek Proxy/IP)"

        payload = {
            "clientKey": CONFIG['funbypass_api_key'],
            "task": {
                "type": "FunCaptchaTask",
                "websiteURL": CONFIG['roblox_login_url'],
                "websitePublicKey": CONFIG['roblox_funcaptcha_key'],
                "websiteSubdomain": CONFIG['roblox_subdomain'],
                "proxy": CONFIG['proxy_url'],
                "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                "cookies": cookies_str,
                "data": json.dumps({"blob": blob})
            }
        }
        
        log("  → Creating FunBypass Task...")
        response = requests.post(f"{CONFIG['funbypass_api_url']}/createTask", json=payload, timeout=30)
        
        if response.status_code != 200:
            return False, f"HTTP Error: {response.status_code}"
            
        data = response.json()
        if data.get("errorId", 0) != 0:
            return False, f"{data.get('errorCode')} - {data.get('errorDescription')}"
            
        task_id = data.get("taskId")
        log(f"  → Task ID: {task_id}, polling...")
        
        start_time = time.time()
        while time.time() - start_time < 120:
            time.sleep(2)
            poll_url = f"{CONFIG['funbypass_api_url']}/getTaskResult/{task_id}"
            result = requests.get(poll_url, timeout=10).json()
            
            if result.get("status") == "ready":
                if result.get("errorId", 0) == 0:
                    token = result.get("solution", {}).get("token")
                    if token:
                        return True, token
                    return False, "Token kosong"
                return False, f"Task fail: {result.get('errorCode')}"
            elif result.get("status") == "failure":
                return False, f"Task failure: {result.get('errorCode')}"
                
        return False, "Timeout"
    except Exception as e:
        return False, str(e)

def launch_via_browser(package: str, url: str) -> bool:
    cmd = f"am start -n {package}/.MainActivity -d '{url}'"
    success, _ = run_command(cmd)
    if success:
        time.sleep(CONFIG['delay_after_launch'])
    return success

def force_stop(package: str):
    run_command(f"am force-stop {package}")
    time.sleep(1)

def input_text(text: str):
    escaped = text.replace(' ', '%s').replace('&', '\\&')
    run_command(f"input text '{escaped}'")
    time.sleep(CONFIG['delay_after_input'])

def tap(x: int, y: int):
    run_command(f"input tap {x} {y}")
    time.sleep(CONFIG['delay_after_input'])

def login_account(username: str, password: str, package: str, account_num: int) -> bool:
    log("")
    log("-" * 60)
    log(f"ACCOUNT #{account_num}: {username}")
    log(f"Package: {package}")
    log("-" * 60)
    retry_count, max_retries = 0, CONFIG['max_captcha_retries']
    
    while retry_count <= max_retries:
        if retry_count > 0:
            log(f"🔄 Retry {retry_count}/{max_retries}")
        try:
            log("1️⃣  Launching Via Browser...")
            if not launch_via_browser(package, CONFIG['roblox_login_url']):
                log("   ❌ Launch failed")
                return False
            log("   ✅ Browser launched")
            time.sleep(3)
            
            log("2️⃣  Inputting credentials...")
            tap(CONFIG['username_field'][0], CONFIG['username_field'][1])
            input_text(username)
            tap(CONFIG['password_field'][0], CONFIG['password_field'][1])
            input_text(password)
            log("   ✅ Credentials entered")
            
            log("3️⃣  Solving captcha...")
            success, token = solve_captcha(username, password)
            
            if not success:
                log(f"   ❌ Captcha failed: {token}")
                if retry_count < max_retries:
                    retry_count += 1
                    force_stop(package)
                    time.sleep(3)
                    continue
                else:
                    return False
            
            log(f"   ✅ Captcha solved! Token: {token[:20]}...")
            log("4️⃣  Submitting login...")
            tap(CONFIG['login_button'][0], CONFIG['login_button'][1])
            time.sleep(5)
            log("   ✅ Login submitted!")
            
            log("5️⃣  Closing browser...")
            force_stop(package)
            log("")
            log("✅ SUCCESS: Login complete!")
            return True
        except Exception as e:
            log(f"❌ Error: {e}")
            force_stop(package)
            return False
    return False

def main():
    print("=" * 60)
    print("🤖 ROBLOX AUTO LOGIN")
    print("=" * 60)
    print()
    if len(sys.argv) < 2:
        print("Usage: python3 auto_login.py <accounts_file>")
        return 1
    
    accounts_file = sys.argv[1]
    log(f"Loading accounts from: {accounts_file}")
    accounts = load_accounts(accounts_file)
    
    if not accounts:
        log("❌ No accounts found!")
        return 1
    log(f"✅ Loaded {len(accounts)} accounts")
    
    success_count, failed = 0, []
    for idx, (username, password) in enumerate(accounts, 1):
        if idx > len(VIA_PACKAGES):
            log(f"\n⚠️  Account #{idx}: No Via Browser available")
            failed.append(username)
            continue
        
        package = VIA_PACKAGES[idx - 1]
        if login_account(username, password, package, idx):
            success_count += 1
        else:
            failed.append(username)
        
        if idx < len(accounts):
            delay = CONFIG['delay_between_accounts']
            log(f"\n⏳ Waiting {delay}s before next account...")
            time.sleep(delay)
    
    print()
    print("=" * 60)
    print("📊 SUMMARY")
    print("=" * 60)
    print(f"Total: {len(accounts)}")
    print(f"✅ Success: {success_count}")
    print(f"❌ Failed: {len(failed)}")
    if failed:
        print(f"\nFailed accounts:")
        for username in failed:
            print(f"  - {username}")
    print("=" * 60)
    print("\n✅ Auto-login complete!")
    return 0

if __name__ == "__main__":
    sys.exit(main())