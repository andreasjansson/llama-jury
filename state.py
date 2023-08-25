INITIAL_EVIDENCE = "The court is being assembled..."
DELIBERATION_EVIDENCE = "The jury now goes into deliberation..."


class State:
    EMPTY = "EMPTY"
    EMPTY_CASE = "EMPTY_CASE"
    PRESENTING_EVIDENCE = "PRESENTING_EVIDENCE"
    AWAITING_UTTERANCE = "AWAITING_UTTERANCE"
    AWAITING_SENTIMENT = "AWAITING_SENTIMENT"
    AWAITING_VERDICT = "AWAITING_VERDICT"
    COMPLETE = "COMPLETE"
    INVALID = "INVALID"

    def __init__(self, db, room, case_id, evidence, agents, verdict, transcript):
        self.db = db
        self.room = room
        self.case_id = case_id
        self.evidence = evidence
        self.agents = agents
        self.verdict = verdict
        self.transcript = transcript
        self.num_deliberation_steps = 0  # no big deal if this state is lost

    @classmethod
    async def load(cls, db, room):
        case_id, agents, evidence, verdict, transcript = await db.load_latest(room)
        return cls(
            db=db,
            room=room,
            case_id=case_id,
            evidence=evidence,
            agents=agents,
            verdict=verdict,
            transcript=transcript,
        )

    def current_step(self):
        if self.case_id is None:
            return State.EMPTY
        if self.evidence is None or self.agents is None or self.transcript is None:
            return State.EMPTY_CASE
        if self.evidence is not None and self.evidence not in (
            "",
            DELIBERATION_EVIDENCE,
        ):
            return State.PRESENTING_EVIDENCE
        if self.verdict is None and (
            (self.all_jurors_are_certain() and self.num_deliberation_steps > 3)
            or self.num_deliberation_steps > 100
        ):
            return State.AWAITING_VERDICT
        if self.evidence in ("", DELIBERATION_EVIDENCE) and self.verdict is None:
            if self.has_latest_sentiment() or (not self.has_latest_utterance()):
                return State.AWAITING_UTTERANCE
            return State.AWAITING_SENTIMENT
        if self.verdict:
            return State.COMPLETE
        return State.INVALID

    def has_latest_sentiment(self):
        return any(a.latest_sentiment for a in self.agents)

    def has_latest_utterance(self):
        return any(a.latest_utterance for a in self.agents)

    def all_jurors_are_certain(self):
        return all(a.is_certain() for a in self.agents)

    def next_evidence(self):
        sections = self.transcript.split("\n\n")
        if self.evidence == INITIAL_EVIDENCE:
            return sections[0]

        index = sections.index(self.evidence)
        if index == len(sections) - 1:
            return DELIBERATION_EVIDENCE
        return sections[index + 1]

    def previous_speaker(self):
        lst = [a for a in self.agents if a.latest_utterance]
        if lst:
            return lst[0]
        return None

    def previous_utterance(self):
        speaker = self.previous_speaker()
        if speaker is None:
            return None
        return speaker.latest_utterance

    def save(self, *properties):
        kwargs = {}
        if "agents" in properties:
            kwargs["agents"] = self.agents
        if "evidence" in properties:
            kwargs["evidence"] = self.evidence
        if "verdict" in properties:
            kwargs["verdict"] = self.verdict
        if "transcript" in properties:
            kwargs["transcript"] = self.transcript
        self.db.save(self.room, self.case_id, **kwargs)

    def reset_with_new_case(self):
        case_id = self.db.create_case(self.room)
        self.case_id = case_id
        self.evidence = None
        self.agents = None
        self.verdict = None
        self.transcript = None
        self.num_deliberation_steps = 0
