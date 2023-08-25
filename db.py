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

    def save_state(self, state):
        if self.client is None:
            return

        agent_dicts = None
        if state.agents is not None:
            agent_dicts = []
            for a in state.agents:
                agent_dicts.append(dataclasses.asdict(a))

        self.client.table("state").insert(
            {
                "case_id": state.case_id,
                "room": state.room,
                "evidence": state.evidence,
                "agents": agent_dicts,
                "verdict": state.verdict,
            }
        ).execute()

    def save_transcript(self, case_id, transcript):
        if self.client is None:
            return

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

        state_result = (
            self.client.table("state")
            .select("*")
            .eq("case_id", case_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if len(state_result.data) == 0:
            return case_id, None, None, None, transcript

        state = state_result.data[0]
        agent_dicts = state["agents"]
        agents = None

        if agent_dicts:
            agents = []
            for agent_dict in agent_dicts:
                agent = Agent(**agent_dict)
                agents.append(agent)

        return (
            case_id,
            agents,
            state["evidence"],
            state["verdict"],
            transcript,
        )
