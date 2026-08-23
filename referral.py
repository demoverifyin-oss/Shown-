#!/usr/bin/env python3
"""
Maccaron Referral Logic Module
Branded for @prime5d
"""
import asyncio
import random
import string
import re
import time
import httpx
from typing import Any, Tuple

# GraphQL Constants
GRAPHQL_URL = "https://graphql.maccaron.in/graphql/"
ORIGIN = "https://maccaron.in"
SIGNUP_PLATFORM = "Web"
MAILTM_API = "https://api.mail.tm"
MAIL_POLL_INTERVAL = 6
MAIL_POLL_TIMEOUT = 180
HTTP_TIMEOUT = 30.0

# GraphQL Queries
REFERRAL_QUERY = "query referral($code: String!) { referral(code: $code) { id owner { id firstName lastName __typename } __typename } }"
CREATE_OTP = "mutation createOtp($input: OtpInput!) { createOtp(input: $input) { otp { receiver status __typename } errors { field message __typename } __typename } }"
VERIFY_OTP = "mutation verifyOtp($input: VerifyOtpInput!) { verifyOtp(input: $input) { otp { id receiver value status __typename } verified errors { field message __typename } __typename } }"
CUSTOMER_SIGNUP = "mutation customerSignUp($input: CustomerSignUpInput!) { customerSignUp(input: $input) { user { id email __typename } errors { field message __typename } __typename } }"
TOKEN_CREATE = "mutation tokenCreate($email: String!, $password: String!) { tokenCreate(email: $email, password: $password) { token user { id email emailVerified mobileVerified __typename } errors { field message __typename } __typename } }"
SEND_VERIFY_EMAIL = "mutation sendVerifyEmail { sendVerifyEmail { errors { field message __typename } __typename } }"
VERIFY_EMAIL = "mutation verifyEmail($id: ID!, $input: VerifyEmailInput!) { verifyEmail(id: $id, input: $input) { errors { message __typename } __typename } }"

VERIFY_LINK_RE = re.compile(r"https://maccaron\.in/en/account/verify-email/([A-Za-z0-9=_-]+)/([A-Za-z0-9_-]+)")

class FlowError(Exception): pass
class GqlError(Exception): pass

def generate_name():
    first_names = ["Aarav", "Aarush", "Advait", "Amit", "Ananya", "Anika", "Anmol", "Arjun", "Arnav", "Aryan", "Atharv", "Ayush", "Dev", "Dhruv", "Divya", "Ishaan", "Ishita", "Kabir", "Kavya", "Kunal", "Laksh", "Meera", "Mihir", "Mira", "Nikhil", "Nisha", "Pranav", "Priya", "Rahul", "Riya", "Rohan", "Sahil", "Samarth", "Sanya", "Shreya", "Siddharth", "Tanvi", "Varun", "Ved", "Vihaan", "Aisha", "Akanksha", "Akshay", "Amaira", "Aman", "Aparna", "Avni", "Bhavna", "Chetan", "Deepak", "Esha", "Gaurav", "Harsh", "Jhanvi", "Karan", "Kirti", "Manoj", "Neha", "Pooja", "Rajat", "Ritika", "Rupal", "Sakshi", "Sanjay", "Shubham", "Sneha", "Sonia", "Sourabh", "Tanya", "Vikram", "Yash", "Zoya"]
    last_names = ["Sharma", "Verma", "Gupta", "Kumar", "Singh", "Patel", "Reddy", "Rao", "Nair", "Menon", "Iyer", "Mehta", "Shah", "Joshi", "Desai", "Kulkarni", "Pandey", "Mishra", "Yadav", "Chauhan", "Agarwal", "Bansal", "Kapoor", "Malhotra", "Chopra", "Khanna", "Bhatia", "Sethi", "Tandon", "Grover", "Saxena", "Trivedi", "Bhatt", "Gandhi", "Chawla", "Dutta", "Banerjee", "Chatterjee", "Mukherjee", "Das", "Bose", "Ghosh", "Saha", "Roy", "Sen", "Pillai", "Naidu", "Krishnan", "Ranganathan", "Subramanian", "Shetty", "Hegde", "Gowda", "Prakash", "Anand", "Sundaram"]
    return random.choice(first_names), random.choice(last_names)

def generate_password():
    return "".join(random.choice(string.ascii_letters + string.digits + "!@#") for _ in range(16))

def random_user_agent():
    return f"Mozilla/5.0 (Linux; Android {random.randint(10, 14)}; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/{random.randint(110, 122)}.0.0.0 Mobile Safari/537.36"

async def with_retry(coro_factory, attempts=3, base_delay=2.0):
    last = None
    for i in range(attempts):
        try: return await coro_factory()
        except (httpx.TimeoutException, httpx.ConnectError, httpx.TransportError) as e:
            last = e
            if i < attempts - 1: await asyncio.sleep(base_delay * (i + 1))
    raise last

class TempMail:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client
        self.address = ""
        self.password = ""
        self.token = ""

    async def create(self):
        r = await self.client.get(f"{MAILTM_API}/domains")
        r.raise_for_status()
        domain = r.json()["hydra:member"][0]["domain"]
        local = "".join(random.choices(string.ascii_lowercase + string.digits, k=12))
        self.address, self.password = f"{local}@{domain}", generate_password()
        
        r = await self.client.post(f"{MAILTM_API}/accounts", json={"address": self.address, "password": self.password})
        if r.status_code not in (200, 201): raise FlowError(f"mail.tm account failed: HTTP {r.status_code}")
        
        r = await self.client.post(f"{MAILTM_API}/token", json={"address": self.address, "password": self.password})
        r.raise_for_status()
        self.token = r.json()["token"]
        return self.address

    async def wait_for_verification_link(self, timeout=MAIL_POLL_TIMEOUT):
        headers = {"Authorization": f"Bearer {self.token}"}
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                r = await self.client.get(f"{MAILTM_API}/messages", headers=headers)
                if r.status_code == 200:
                    msgs = r.json().get("hydra:member", [])
                    for m in msgs:
                        full = await self.client.get(f"{MAILTM_API}/messages/{m['id']}", headers=headers)
                        if full.status_code != 200: continue
                        b_txt = full.json().get("text") or ""
                        b_html = full.json().get("html") or ""
                        body = str(b_txt) + "\n" + str(b_html)
                        match = VERIFY_LINK_RE.search(body)
                        if match: return match.group(1), match.group(2)
            except: pass
            await asyncio.sleep(MAIL_POLL_INTERVAL)
        return None, None

class ReferralSession:
    def __init__(self, code: str):
        self.code = code
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(HTTP_TIMEOUT), follow_redirects=True)
        self.user_agent = random_user_agent()

    async def close(self):
        await self.client.aclose()

    def _headers(self, token=None):
        h = {"Content-Type": "application/json", "Origin": ORIGIN, "User-Agent": self.user_agent}
        if token: h["Authorization"] = f"JWT {token}"
        return h

    async def gql(self, query, variables=None, token=None):
        r = await self.client.post(GRAPHQL_URL, json={"query": query, "variables": variables or {}}, headers=self._headers(token))
        payload = r.json()
        if payload.get("errors"): raise GqlError("; ".join(e.get("message", str(e)) for e in payload["errors"]))
        return payload.get("data") or {}

    async def check_referral(self):
        data = await with_retry(lambda: self.gql(REFERRAL_QUERY, {"code": self.code}))
        if not data.get("referral"): raise FlowError("Invalid referral code")
        return data["referral"]["owner"]

    async def send_otp(self, mobile):
        data = await with_retry(lambda: self.gql(CREATE_OTP, {"input": {"receiver": mobile}}))
        node = data.get("createOtp") or {}
        if node.get("errors"): raise FlowError(node["errors"][0]["message"])
        return node.get("otp", {}).get("status")

    async def verify_otp(self, mobile, otp):
        data = await with_retry(lambda: self.gql(VERIFY_OTP, {"input": {"receiver": mobile, "value": otp}}))
        node = data.get("verifyOtp") or {}
        if not node.get("verified"): raise FlowError("Invalid OTP")
        return node["otp"]["id"]

    async def signup(self, mobile, otp_id, otp_value):
        mailbox = TempMail(self.client)
        email = await mailbox.create()
        password = generate_password()
        fn, ln = generate_name()
        
        vars_signup = {"input": {
            "firstName": fn, "lastName": ln, "email": email, "password": password,
            "otpId": otp_id, "otpValue": otp_value, "mobileNumber": mobile,
            "referralCode": self.code, "cartToken": None, "signupPlatform": SIGNUP_PLATFORM,
        }}
        data = await with_retry(lambda: self.gql(CUSTOMER_SIGNUP, vars_signup))
        if data.get("customerSignUp", {}).get("errors"):
            raise FlowError(data["customerSignUp"]["errors"][0]["message"])
            
        data = await with_retry(lambda: self.gql(TOKEN_CREATE, {"email": email, "password": password}))
        jwt = data.get("tokenCreate", {}).get("token")
        
        await with_retry(lambda: self.gql(SEND_VERIFY_EMAIL, {}, token=jwt))
        uid, vtoken = await mailbox.wait_for_verification_link()
        if not uid: raise FlowError("Email verification timeout")
        
        await with_retry(lambda: self.gql(VERIFY_EMAIL, {"id": uid, "input": {"token": vtoken}}, token=jwt))
        return email, f"{fn} {ln}"
