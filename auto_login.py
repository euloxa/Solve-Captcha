#!/usr/bin/env python3
"""
Roblox Auto Login - Simple Version
Login credentials to 10 Via Browser instances with FunBypass captcha solving
Does NOT extract cookies - use roblox-cookie-extractor for that
"""

import os
import sys
import json
import time
import subprocess
from datetime import datetime
from typing import List, Tuple, Optional


# ====================================
# CONFIGURATION
# ====================================

VIA_PACKAGES = [
    "mark.via.gp",
    "mark.via.gq",
    "mark.via.gr",
    "mark.via.gs",
    "mark.via.gt",
    "mark.via.gu",
    "mark.via.gv",
    "mark.via.gw",
    "mark.via.gx",
    "mark.via.gy"
]

# Default config
CONFIG = {
    "funbypass_api_key": "FUN-GHRXV8FVZOTZCJQB",
    "funbypass_api_url": "https://app.funbypass.com/api/v1/funcaptcha",
    "roblox_login_url": "https://www.roblox.com/login",
    "roblox_funcaptcha_key": "476068BF-9607-4799-B53D-966BE98E2B81",
    "delay_after_launch": 5,
    "delay_after_input": 1,
    "delay_between_accounts": 120,
    "username_field": [540, 400],
    "password_field": [540, 500],
    "login_button": [540, 600],
    "max_captcha_retries": 1
}


# ====================================
# UTILITY FUNCTIONS
# ====================================

def run_command(cmd: str, use_root: bool = True) -> Tuple[bool, str]:
    """Execute shell command"""
    try:
        if use_root:
            cmd = f"su -c '{cmd}'"
        
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        return result.returncode == 0, result.stdout.strip()
    except Exception as e:
        return False, str(e)


def log(message: str):
    """Print with timestamp"""
    timestamp = datetime.now().strftime('%H:%M:%S')
    print(f"[{timestamp}] {message}")


def load_accounts(filename: str) -> List[Tuple[str, str]]:
    """Load accounts from file (username:password format)"""
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
            username = parts[0].strip()
            password = parts[1].strip()
            
            if username and password:
                accounts.append((username, password))
    
    return accounts


# ====================================
# VIA BROWSER CONTROL
# ====================================

def launch_via_browser(package: str, url: str) -> bool:
    """Launch Via Browser with URL"""
    cmd = f"am start -n {package}/.MainActivity -d '{url}'"
    success, _ = run_command(cmd)
    
    if success:
        time.sleep(CONFIG['delay_after_launch'])
    
    return success


def force_stop(package: str):
    """Force stop Via Browser"""
    run_command(f"am force-stop {package}")
    time.sleep(1)


def input_text(text: str):
    """Input text via ADB"""
    escaped = text.replace(' ', '%s').replace('&', '\\&')
    run_command(f"input text '{escaped}'")
    time.sleep(CONFIG['delay_after_input'])


def tap(x: int, y: int):
    """Tap screen coordinate"""
    run_command(f"input tap {x} {y}")
    time.sleep(CONFIG['delay_after_input'])


def take_screenshot(output_path: str) -> bool:
    """Take screenshot"""
    if os.path.exists(output_path):
        os.remove(output_path)
    
    success, _ = run_command(f"screencap -p {output_path}")
    return success and os.path.exists(output_path)


# ====================================
# FUNBYPASS CAPTCHA SOLVER
# ====================================

def solve_captcha(screenshot_path: str) -> Tuple[bool, Optional[str]]:
    """Solve FunCaptcha via FunBypass API"""
    import requests
    import base64
    
    try:
        # Read screenshot
        with open(screenshot_path, 'rb') as f:
            image_data = base64.b64encode(f.read()).decode('utf-8')
        
        # Prepare payload
        payload = {
            'siteUrl': CONFIG['roblox_login_url'],
            'publicKey': CONFIG['roblox_funcaptcha_key'],
            'captchaType': 'funcaptcha',
            'imageBase64': image_data
        }
        
        headers = {
            'Authorization': f"Bearer {CONFIG['funbypass_api_key']}",
            'Content-Type': 'application/json'
        }
        
        # Submit
        log("  → Submitting to FunBypass...")
        response = requests.post(CONFIG['funbypass_api_url'], json=payload, headers=headers, timeout=30)
        
        if response.status_code != 200:
            return False, f"API error: {response.status_code}"
        
        result = response.json()
        
        # Check immediate response
        if result.get('status') == 'success' and result.get('token'):
            return True, result['token']
        
        # Poll for result
        task_id = result.get('taskId')
        if not task_id:
            return False, "No task ID"
        
        log(f"  → Task ID: {task_id}, polling...")
        
        poll_url = f"{CONFIG['funbypass_api_url'].rsplit('/', 1)[0]}/status/{task_id}"
        start = time.time()
        
        while time.time() - start < 60:
            time.sleep(3)
            
            resp = requests.get(poll_url, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                
                if data.get('status') == 'completed':
                    token = data.get('token') or data.get('solution')
                    if token:
                        return True, token
                
                elif data.get('status') == 'failed':
                    return False, data.get('message', 'Solving failed')
        
        return False, "Timeout"
    
    except Exception as e:
        return False, str(e)


# ====================================
# MAIN LOGIN ROUTINE
# ====================================

def login_account(username: str, password: str, package: str, account_num: int) -> bool:
    """Login single account"""
    log("")
    log("=" * 60)
    log(f"ACCOUNT #{account_num}: {username}")
    log(f"Package: {package}")
    log("=" * 60)
    
    retry_count = 0
    max_retries = CONFIG['max_captcha_retries']
    
    while retry_count <= max_retries:
        if retry_count > 0:
            log(f"🔄 Retry {retry_count}/{max_retries}")
        
        try:
            # Launch browser
            log("1️⃣  Launching Via Browser...")
            if not launch_via_browser(package, CONFIG['roblox_login_url']):
                log("   ❌ Launch failed")
                return False
            
            log("   ✅ Browser launched")
            
            # Wait for page load
            time.sleep(3)
            
            # Input username
            log("2️⃣  Inputting credentials...")
            tap(CONFIG['username_field'][0], CONFIG['username_field'][1])
            input_text(username)
            
            tap(CONFIG['password_field'][0], CONFIG['password_field'][1])
            input_text(password)
            
            log("   ✅ Credentials entered")
            
            # Screenshot
            log("3️⃣  Taking screenshot...")
            screenshot = "/sdcard/Download/temp_screenshot.png"
            
            if not take_screenshot(screenshot):
                log("   ❌ Screenshot failed")
                return False
            
            log("   ✅ Screenshot taken")
            
            # Solve captcha
            log("4️⃣  Solving captcha...")
            success, token = solve_captcha(screenshot)
            
            if not success:
                log(f"   ❌ Captcha failed: {token}")
                
                if retry_count < max_retries:
                    retry_count += 1
                    force_stop(package)
                    time.sleep(3)
                    continue
                else:
                    return False
            
            log(f"   ✅ Captcha solved!")
            
            # Submit login
            log("5️⃣  Submitting login...")
            tap(CONFIG['login_button'][0], CONFIG['login_button'][1])
            time.sleep(5)
            
            log("   ✅ Login submitted!")
            
            # Close browser
            log("6️⃣  Closing browser...")
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
    """Main execution"""
    print("=" * 60)
    print("🤖 ROBLOX AUTO LOGIN")
    print("=" * 60)
    print()
    
    # Check arguments
    if len(sys.argv) < 2:
        print("Usage: python3 auto_login.py <accounts_file>")
        print("Example: python3 auto_login.py device1.txt")
        return 1
    
    accounts_file = sys.argv[1]
    
    # Load accounts
    log(f"Loading accounts from: {accounts_file}")
    accounts = load_accounts(accounts_file)
    
    if not accounts:
        log("❌ No accounts found!")
        return 1
    
    log(f"✅ Loaded {len(accounts)} accounts")
    
    # Process accounts
    success_count = 0
    failed = []
    
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
        
        # Delay before next account
        if idx < len(accounts):
            delay = CONFIG['delay_between_accounts']
            log(f"\n⏳ Waiting {delay}s before next account...")
            time.sleep(delay)
    
    # Summary
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
    print("Next: Run cookie extractor to get .ROBLOSECURITY tokens")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
