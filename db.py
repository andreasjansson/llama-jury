import sys
import dataclasses
import os
from supabase import create_client


class DatabaseSession:
    def __init__(self, room):
        self.room = room

        self.client = None
        if "SUPABASE_URL" not in os.environ:
            sys.stderr.write("No SUPABASE_URL provided, won't save to database\n")
            return

        self.client = create_client(
            os.environ["SUPABASE_URL"], os.environ["SUPABASE_API_KEY"]
        )

        row = self.client.table("case").insert({"room": room}).execute()
        self.case_id = row.data[0]["id"]
        print(f"Starting case {self.case_id} in room {room}")

    def save(self, room, agents=None, evidence=None, verdict=None):
        if self.client is None:
            return

        if agents is not None:
            state = []
            for a in agents:
                state.append(dataclasses.asdict(a))
            self.client.table("agents_state").insert(
                {"case_id": self.case_id, "state": state, "room": room}
            ).execute()

        if evidence is not None:
            self.client.table("evidence").insert(
                {"case_id": self.case_id, "text": evidence, "room": room}
            ).execute()

        if verdict is not None:
            self.client.table("verdict").insert(
                {"case_id": self.case_id, "text": verdict, "room": room}
            ).execute()
