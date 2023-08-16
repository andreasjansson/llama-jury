import sys
import dataclasses
import os
from supabase import create_client
from dotenv import load_dotenv

client = None
case_id = None

def init():
    global client, case_id

    load_dotenv()
    if "SUPABASE_URL" not in os.environ:
        sys.stderr.write("No SUPABASE_URL provided, won't save to database\n")
        return

    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_API_KEY"])

    row = client.table("case").insert({}).execute()
    case_id = row.data[0]["id"]


def save(agents=None, evidence=None, verdict=None):
    if client is None:
        return

    if agents is not None:
        state = []
        for a in agents:
            state.append(dataclasses.asdict(a))
        client.table('agents_state').insert({"case_id": case_id, "state": state}).execute()

    if evidence is not None:
        client.table("evidence").insert({"case_id": case_id, "text": evidence}).execute()

    if verdict is not None:
        row = client.table("case").update({"verdict": verdict}).eq("id", case_id).execute()
