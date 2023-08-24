import sys
import dataclasses
import os
from supabase import create_client

client = None
case_id = None


def init(room):
    global client, case_id

    if "SUPABASE_URL" not in os.environ:
        sys.stderr.write("No SUPABASE_URL provided, won't save to database\n")
        return

    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_API_KEY"])

    row = client.table("case").insert({"room": room}).execute()
    case_id = row.data[0]["id"]
    print(f"Starting case {case_id} in room {room}")


def save(room, agents=None, evidence=None, verdict=None):
    if client is None:
        return

    if agents is not None:
        state = []
        for a in agents:
            state.append(dataclasses.asdict(a))
        client.table("agents_state").insert(
            {"case_id": case_id, "state": state, "room": room}
        ).execute()

    if evidence is not None:
        client.table("evidence").insert(
            {"case_id": case_id, "text": evidence, "room": room}
        ).execute()

    if verdict is not None:
        client.table("verdict").insert(
            {"case_id": case_id, "text": verdict, "room": room}
        ).execute()
