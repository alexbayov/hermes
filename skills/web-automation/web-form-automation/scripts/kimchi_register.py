#!/usr/bin/env python3
"""
Kimchi auto-register + email confirm via Supabase Auth + IMAP.
No browser needed. Full cycle ~9 seconds.
"""
import requests, subprocess, time, re

KIMCHI_KEY = open("/tmp/kimchi_key.txt").read().strip()
SUPA_URL   = "https://dipswfuzhdgwirixmeem.supabase.co/auth/v1"
HIMALAYA   = "/root/.local/bin/himalaya"


def register(email: str, password: str, alias_tag: str = "kimchi") -> dict:
    t0 = time.time()

    # 1. signup via Supabase Auth API
    r = requests.post(
        f"{SUPA_URL}/signup",
        headers={"apikey": KIMCHI_KEY, "Content-Type": "application/json"},
        json={"email": email, "password": password},
        timeout=20,
    )
    r.raise_for_status()
    data = r.json()
    print(f"[1] signup OK: {data['id']}  ({time.time()-t0:.1f}s)")

    # 2. poll Gmail via himalaya IMAP for confirmation link
    time.sleep(6)  # let Supabase send the email
    link = None
    for _ in range(10):
        res = subprocess.run(
            [HIMALAYA, "envelope", "list", "--account", "antisecta", "--folder", "INBOX"],
            capture_output=True, text=True, timeout=20,
        )
        for line in res.stdout.splitlines():
            if "confirm" in line.lower():
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if not parts:
                    continue
                msg_id = parts[0]
                body_res = subprocess.run(
                    [HIMALAYA, "message", "read", msg_id, "--account", "antisecta"],
                    capture_output=True, text=True, timeout=15,
                )
                body = body_res.stdout
                urls = re.findall(r'https://\S+', body)
                for url in urls:
                    # Kimchi uses lovable.cloud redirect links
                    if "lovable" in url or "auth" in url:
                        link = url
                        print(f"[2] email found, link extracted  ({time.time()-t0:.1f}s)")
                        break
        if link:
            break
        time.sleep(2)
    if not link:
        raise RuntimeError("confirmation link not found in inbox")

    # 3. follow redirect — this confirms the email
    r2 = requests.get(link, timeout=20, allow_redirects=True)
    print(f"[3] confirm GET: {r2.status_code}  ({time.time()-t0:.1f}s)")

    # The redirect final URL contains access_token in fragment
    access_token = None
    if "access_token=" in r2.url:
        access_token = r2.url.split("access_token=")[1].split("&")[0]
        print(f"[3b] token extracted from redirect URL ({len(access_token)} chars)")

    # 4. verify login works (token from API is cleaner)
    r3 = requests.post(
        f"{SUPA_URL}/token?grant_type=password",
        headers={"apikey": KIMCHI_KEY, "Content-Type": "application/json"},
        json={"email": email, "password": password},
        timeout=20,
    )
    r3.raise_for_status()
    j = r3.json()
    confirmed_at = j["user"].get("email_confirmed_at")
    api_token = j["access_token"]
    print(f"[4] login OK, confirmed_at={confirmed_at}  ({time.time()-t0:.1f}s)")

    return {
        "status": "ok",
        "user_id": data["id"],
        "confirmed_at": confirmed_at,
        "token_from_api": api_token,
        "token_from_redirect": access_token,
        "elapsed_sec": round(time.time() - t0, 1),
    }


if __name__ == "__main__":
    result = register("i.bayov@antisecta.com", "1286520zZ!")
    print("\nResult:", result)
