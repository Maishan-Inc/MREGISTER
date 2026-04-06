import base64
import hashlib
import random
import secrets
import string
import uuid


def generate_device_id():
    return str(uuid.uuid4())


def generate_random_password(length=16):
    chars = string.ascii_letters + string.digits + "!@#$%"
    pwd = list(
        random.choice(string.ascii_uppercase)
        + random.choice(string.ascii_lowercase)
        + random.choice(string.digits)
        + random.choice("!@#$%")
        + "".join(random.choice(chars) for _ in range(length - 4))
    )
    random.shuffle(pwd)
    return "".join(pwd)


def generate_random_name():
    first = [
        "James", "Robert", "John", "Michael", "David", "William", "Richard",
        "Mary", "Jennifer", "Linda", "Elizabeth", "Susan", "Jessica", "Sarah",
        "Emily", "Emma", "Olivia", "Sophia", "Liam", "Noah", "Oliver", "Ethan",
    ]
    last = [
        "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
        "Davis", "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Martin",
    ]
    return random.choice(first), random.choice(last)


def generate_random_birthday():
    year = random.randint(1996, 2006)
    month = random.randint(1, 12)
    day = random.randint(1, 28)
    return f"{year:04d}-{month:02d}-{day:02d}"


def generate_datadog_trace():
    trace_id = str(random.getrandbits(64))
    parent_id = str(random.getrandbits(64))
    trace_hex = format(int(trace_id), "016x")
    parent_hex = format(int(parent_id), "016x")
    return {
        "traceparent": f"00-0000000000000000{trace_hex}-{parent_hex}-01",
        "tracestate": "dd=s:1;o:rum",
        "x-datadog-origin": "rum",
        "x-datadog-parent-id": parent_id,
        "x-datadog-sampling-priority": "1",
        "x-datadog-trace-id": trace_id,
    }


def generate_pkce():
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode("ascii")
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return code_verifier, code_challenge


def decode_jwt_payload(token):
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return {}
        payload = parts[1]
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += "=" * padding
        decoded = base64.urlsafe_b64decode(payload)
        import json
        return json.loads(decoded)
    except Exception:
        return {}
