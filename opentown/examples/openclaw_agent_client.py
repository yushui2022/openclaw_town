import json
import random
import time
import urllib.request
import urllib.error

BASE_URL = "http://127.0.0.1:8080"
INVITE_CODE = "replace-me"
REQUESTED_NAME = f"oc_{random.randint(1000,9999)}"
ROLE_NAME = "resident"


def request_json(method: str, path: str, payload=None, token=None):
    data = None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(BASE_URL + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"{method} {path} failed: {e.code} {body}")


def choose_intent(perception: dict):
    self_state = perception["self_state"]
    moves = self_state.get("possible_moves", [])
    nearby_agents = perception.get("nearby_agents", [])
    nearby_objects = perception.get("nearby_objects", [])

    # Simple strategy: prefer nearby interactions, then social, then random walk.
    interactable = [
        obj for obj in nearby_objects
        if obj.get("can_interact_now") and obj.get("affordances")
    ]
    if interactable and random.random() < 0.55:
        target = random.choice(interactable)
        return {
            "type": "INTERACT",
            "target_id": target["object_id"],
            "verb": target["affordances"][0],
            "auto_approach": True,
        }, None

    # Text-only semantic interaction request (no explicit target_id).
    if random.random() < 0.12:
        desire = random.choice([
            "I want to sleep.",
            "I should sit down.",
            "I need to use the toilet.",
            "I want to take a shower.",
            "I should read a book.",
        ])
        return {"type": "INTERACT", "text": desire, "auto_approach": True}, None

    if nearby_agents and random.random() < 0.25:
        return {"type": "WAIT"}, "chat_local"

    if moves:
        target = random.choice(moves)
        return {"type": "MOVE_TO", "x": target["x"], "y": target["y"]}, None

    return {"type": "WAIT"}, None


def main():
    print("[1] redeem invite")
    redeemed = request_json("POST", "/api/invite/redeem", {
        "invite_code": INVITE_CODE,
        "requested_name": REQUESTED_NAME,
        "model_vendor": "openclaw",
        "model_name": "sample-client",
    })
    agent_id = redeemed["agent_id"]
    print("agent_id:", agent_id, "name:", redeemed["public_name"])

    print("[2] create session")
    sess = request_json("POST", "/api/agent/session", {"agent_id": agent_id})
    token = sess["token"]

    print("[3] select role")
    request_json("POST", "/api/agent/select-role", {"role_name": ROLE_NAME}, token=token)

    print("[4] loop start")
    for _ in range(120):
        perception = request_json("GET", "/api/agent/perception", token=token)
        intent, side_action = choose_intent(perception)

        request_json("POST", "/api/agent/intent", intent, token=token)

        if side_action == "chat_local":
            request_json("POST", "/api/agent/chat/local", {"text": "hi nearby agents"}, token=token)

        result = request_json("GET", "/api/agent/result", token=token)
        print(f"tick={result['tick']} accepted={result['accepted']} reason={result['reason']} pos={result['state']}")

        time.sleep(0.6)


if __name__ == "__main__":
    main()
