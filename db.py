import sys
import dataclasses
import os
from supabase import create_client

from agent import Agent


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

    def create_case(self, room):
        row = self.client.table("case").insert({"room": room}).execute()
        case_id = row.data[0]["id"]
        print(f"Starting case {case_id} in room {room}")
        return case_id

    def save(
        self, room, case_id, agents=None, evidence=None, verdict=None, transcript=None
    ):
        if self.client is None:
            return

        if agents is not None:
            state = []
            for a in agents:
                state.append(dataclasses.asdict(a))
            self.client.table("agents_state").insert(
                {"case_id": case_id, "state": state, "room": room}
            ).execute()

        if evidence is not None:
            self.client.table("evidence").insert(
                {"case_id": case_id, "text": evidence, "room": room}
            ).execute()

        if verdict is not None:
            self.client.table("verdict").insert(
                {"case_id": case_id, "text": verdict, "room": room}
            ).execute()

        if transcript is not None:
            self.client.table("case").update({"transcript": transcript}).eq(
                "id", case_id
            ).execute()


    async def load_latest(self, room):
        if self.client is None:
            return None, None, None, None, None

        # Fetch the latest case for the room
        case_result = (
            self.client.table("case")
            .select("*")
            .eq("room", room)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

        if len(case_result.data) == 0:
            return None, None, None, None, None

        latest_case = case_result.data[0]
        case_id = latest_case["id"]
        transcript = latest_case["transcript"]

        # Initialize empty dictionaries to hold the latest agents_state, evidence, and verdict
        latest_agents = None
        latest_evidence = None
        latest_verdict = None

        # Fetch the latest agents_state
        agents_state_result = (
            self.client.table("agents_state")
            .select("*")
            .eq("case_id", case_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

        if len(agents_state_result.data) > 0:
            latest_agents_state = agents_state_result.data[0]
            latest_agents = []
            if latest_agents_state and "state" in latest_agents_state:
                for agent_dict in latest_agents_state["state"]:
                    agent = Agent(**agent_dict)
                    latest_agents.append(agent)

        # Fetch the latest evidence
        evidence_result = (
            self.client.table("evidence")
            .select("*")
            .eq("case_id", case_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

        if len(evidence_result.data) > 0:
            latest_evidence = evidence_result.data[0]['text']

        # Fetch the latest verdict
        verdict_result = (
            self.client.table("verdict")
            .select("*")
            .eq("case_id", case_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

        if len(verdict_result.data) > 0:
            latest_verdict = verdict_result.data[0]['text']

        return (
            case_id,
            latest_agents,
            latest_evidence,
            latest_verdict,
            transcript,
        )
