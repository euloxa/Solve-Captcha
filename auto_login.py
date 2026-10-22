#!/usr/bin/env python3
import os, sys, json, time, subprocess, requests, base64
from datetime import datetime
from typing import List, Tuple, Optional

VIA_PACKAGES = [f"mark.via.g{suffix}" for suffix in "pqrstuvwxyz"]
CONFIG = {
    "funbypass_api_key": "ISI_API_KEY_LU", 
    "funbypass_api_url": "https://api.funbypass.com",
    "roblox_login_url": "https://www.roblox.com/login",
    "roblox_funcaptcha_key": "476068BF-9607-4799-B53D-966BE98E2B81",
    "roblox_subdomain": "client-api",
    "proxy_url": "socks5://user:pass@ip:port", 
    "delay_after_launch": 5, "delay_after_input": 1, "delay_between_accounts": 120,
    "username_field": [540, 400], "password_field": [540, 500], "login_button": [540, 600],
    "max_captcha_retries": 1
}

def run_command(cmd: str, use_root: bool = True) -> Tuple[bool, str]:
    try:
        if use_root: cmd = f"su -c '{cmd}'"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        return result.returncode == 0, result.stdout.strip()
    except Exception as e: return False, str(e)

def log(message: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

def load_accounts(filename: str) -> List[Tuple[str, str]]:
    accounts = []
    if not os.path.exists(filename): return accounts
    with open(filename, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and ':' in line:
                u, p = line.split(':', 1)
                accounts.append((u.strip(), p.strip()))
    return accounts

def get_roblox_blob(username: str, password: str) -> Optional[str]:
    try:
        session = requests.Session()
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Content-Type": "application/json", "Origin": "https://www.roblox.com",
            "Referer": "https://www.roblox.com/"
        }
        session.get("https://www.roblox.com/", headers=headers, timeout=15)
        r_csrf = session.post("https://auth.roblox.com/v2/login", headers=headers, json={}, timeout=15)
        csrf = r_csrf.headers.get("x-csrf-token")
        if not csrf: return None
        
        headers["X-CSRF-Token"] = csrf
        r = session.post("https://auth.roblox.com/v2/login", json={"ctype": "Username", "cvalue": username, "password": password}, headers=headers, timeout=15)
        
        meta_b64 = r.headers.get("rblx-challenge-metadata")
        if not meta_b64: return None
        
        padding = len(meta_b64) % 4
        if padding: meta_b64 += "=" * (4 - padding)
        decoded = base64.b64decode(meta_b64).decode('utf-8')
        metadata = json.loads(decoded)
        
        return metadata.get("dataExchangeBlob") or metadata.get("sessionId") or metadata.get("genericChallengeId")
    except Exception:
        return None

def solve_captcha(username: str, password: str) -> Tuple[bool, Optional[str]]:
    try:
        blob = get_roblox_blob(username, password)
        if not blob: return False, "Gagal mendapatkan blob/sessionId"

        payload = {
            "clientKey": CONFIG['funbypass_api_key'],
            "task": {
                "type": "FunCaptchaTask",
                "websiteURL": CONFIG['roblox_login_url'],
                "websitePublicKey": CONFIG['roblox_funcaptcha_key'],
                "websiteSubdomain": CONFIG['roblox_subdomain'],
                "proxy": CONFIG['proxy_url'],
                "data": json.dumps({"blob": blob})
            }
        }
        log("  → Creating FunBypass Task...")
        resp = requests.post(f"{CONFIG['funbypass_api_url']}/createTask", json=payload, timeout=30).json()
        if resp.get("errorId", 0) != 0: return False, f"{resp.get('errorCode')} - {resp.get('errorDescription')}"
            
        task_id = resp.get("taskId")
        log(f"  → Task ID: {task_id}, polling...")
        for _ in range(150):
            time.sleep(2)
            res = requests.get(f"{CONFIG['funbypass_api_url']}/getTaskResult/{task_id}", timeout=10).json()
            if res.get("status") == "ready":
                if res.get("errorId", 0) == 0: return True, res.get("solution", {}).get("token")
                return False, f"Task fail: {res.get('errorCode')} - {res.get('errorDescription')}"
            elif res.get("status") == "failure": return False, f"Task failure: {res.get('errorCode')}"
        return False, "Timeout"
    except Exception as e: return False, str(e)

def launch_via_browser(package: str, url: str) -> bool:
    success, _ = run_command(f"am start -n {package}/.MainActivity -d '{url}'")
    if success: time.sleep(CONFIG['delay_after_launch'])
    return success

def force_stop(package: str):
    run_command(f"am force-stop {package}"); time.sleep(1)

def input_text(text: str):
    run_command(f"input text '{text.replace(' ', '%s')}'"); time.sleep(CONFIG['delay_after_input'])

def tap(x: int, y: int):
    run_command(f"input tap {x} {y}"); time.sleep(CONFIG['delay_after_input'])

def login_account(username: str, password: str, package: str, account_num: int) -> bool:
    log(f"\n{'-'*60}\nACCOUNT #{account_num}: {username}\n{'-'*60}")
    for retry in range(CONFIG['max_captcha_retries'] + 1):
        if retry > 0: log(f"🔄 Retry {retry}/{CONFIG['max_captcha_retries']}")
        if not launch_via_browser(package, CONFIG['roblox_login_url']): return False
        tap(*CONFIG['username_field']); input_text(username)
        tap(*CONFIG['password_field']); input_text(password)
        
        success, token = solve_captcha(username, password)
        if not success:
            log(f"   ❌ Captcha failed: {token}")
            force_stop(package); time.sleep(3); continue
        
        log(f"   ✅ Captcha solved! Token: {token[:20]}...")
        tap(*CONFIG['login_button']); time.sleep(5)
        force_stop(package)
        return True
    return False

def main():
    if len(sys.argv) < 2: print("Usage: python3 auto_login.py <accounts_file>"); return 1
    accounts = load_accounts(sys.argv[1])
    if not accounts: log("❌ No accounts found!"); return 1
    
    success, failed = 0, []
    for idx, (username, password) in enumerate(accounts, 1):
        if idx > len(VIA_PACKAGES): failed.append(username); continue
        if login_account(username, password, VIA_PACKAGES[idx-1], idx): success += 1
        else: failed.append(username)
        if idx < len(accounts): time.sleep(CONFIG['delay_between_accounts'])
    
    print(f"\n{'='*60}\n📊 SUMMARY\n{'='*60}\nTotal: {len(accounts)} | ✅ Success: {success} | ❌ Failed: {len(failed)}")
    for u in failed: print(f"  - {u}")
    return 0

if __name__ == "__main__": sys.exit(main())