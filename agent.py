import random
import re
import sys
from typing import Optional
from dataclasses import dataclass, field
from typing import Dict

from llama import (
    gen,
    gen_formatted_response,
    response_format_prompt,
    fuzzy_percent,
)
from sd import make_image


@dataclass
class Agent:
    name: str
    description: str

    # Summary of the case
    summary: str = ""

    # Beliefs about the case
    beliefs: str = "No opinions yet."

    # When guilty_percent - innocent_percent > 50 (or the other way around) the agent is certain
    guilty_percent: int = 50
    innocent_percent: int = 50

    # Beliefs about the other people in the jury (name -> sentiment)
    agent_sentiments: Dict[str, str] = field(default_factory=dict)

    # One word describing current mood, also used in the UI
    mood: str = ""

    # Whether the agent has something to say
    speak_eagerness: int = 0

    # Latest opinion about someone in response to their last utterance. Used in UI.
    latest_sentiment: str = ""

    # Latest utterance
    latest_utterance: str = ""

    # Used in UI
    image_uri: str = ""

    def description_prompt(self, is_in_deliberation):
        prompt = (
            f"You are {self.description}. You are a member of a jury in a court case. "
        )
        if is_in_deliberation:
            prompt += "The jury is now in deliberation and no further evidence will be presented. You must now examine the evidence and argue your opinion and work towards a conclusive verdict."
        else:
            prompt += "Evidence is being presented and you are forming an opinion."
        return prompt

    def mood_prompt(self):
        return f"Your current mood is: {self.mood}"

    def beliefs_prompt(self):
        return f"""Summary of the evidence: {self.summary}

Your current opinions and beliefs about the court case are: {self.beliefs}

You are currently {self.guilty_percent}% sure that the defendant is guilty and {self.innocent_percent}% sure that the defendant is innocent."""

    def agent_sentiments_prompt(self):
        prompt = "Your current opinions about your fellow jury members are:\n"
        for name, sentiment in self.agent_sentiments.items():
            prompt += f"* {name}: {sentiment}\n"
        return prompt

    async def set_initial_mood(self):
        prompt = f"""{self.description_prompt(is_in_deliberation=False)}

What is your current mood? Respond in only one or two words."""
        self.mood = await gen(prompt)
        self.image_uri = await make_image(self)

    async def set_preconceptions_about_fellow_jury_members(self, other_agents):
        for a in other_agents:
            self.agent_sentiments[a.name] = await gen(
                f"""{self.description_prompt(is_in_deliberation=False)}

{self.mood_prompt()}

Describe your opinion of your fellow jury member, {a.description}.

Only base your opinion on their superficial appearence and mannerisms. Respond in only one or two words."""
            )

    async def hear(
        self, utterance, is_in_deliberation, speaker: Optional["Agent"] = None
    ):
        prompt = f"""{self.description_prompt(is_in_deliberation=is_in_deliberation)}

{self.mood_prompt()}

"""
        beliefs_key = self.name_key() + "_BELIEFS"
        if speaker is None:
            response_fields = [
                ("FACTUAL_SUMMARY", str),
                ("MOOD", str),
                (beliefs_key, str),
                ("GUILTY_PERCENTAGE", fuzzy_percent),
                ("INNOCENT_PERCENTAGE", fuzzy_percent),
            ]

            prompt += f"""{self.beliefs_prompt()}

The court says:
{utterance}

You are {self.description}, in your own distinctive tone of voice, describe your updated summary of what the court has said so far (factual bullet points only), mood (one word), beliefs (several bullet points in the voice of {self.name}), and certainty of guilt and innocence (percentages) in the following format::
"""
        else:
            prompt += f"""{self.agent_sentiments_prompt()}

{self.beliefs_prompt()}

{speaker.name} says: {utterance}

You are {self.description}, given your previous beliefs and what {speaker.name} said, in your own distinctive voice, describe your updated mood (one word), new beliefs (several bullet points in the voice of {self.name}), updated certainty of guilt and innocence (percentages), and updated opinion about the speaker {speaker.name}'s views in relation to your own beliefs (concise) in the following format (do not output anything else):
"""
            opinion_key = "OPINION_ABOUT_" + speaker.name_key()
            response_fields = [
                ("MOOD", str),
                (beliefs_key, str),
                ("GUILTY_PERCENTAGE", fuzzy_percent),
                ("INNOCENT_PERCENTAGE", fuzzy_percent),
                (opinion_key, str),
            ]

        prompt += response_format_prompt(response_fields)
        parsed = await gen_formatted_response(prompt, response_fields)
        old_mood = self.mood
        if parsed:
            self.mood = parsed["MOOD"]
            self.beliefs = parsed[beliefs_key]
            self.guilty_percent = parsed["GUILTY_PERCENTAGE"]
            self.innocent_percent = parsed["INNOCENT_PERCENTAGE"]
            if speaker is None:
                self.summary = parsed["FACTUAL_SUMMARY"]
            else:
                self.agent_sentiments[speaker.name] = parsed[opinion_key]
                self.latest_sentiment = parsed[opinion_key]
        else:
            sys.stderr.write(
                "Failed to parse belief, interpreting as mishearing and falling back on previous beliefs\n"
            )
            sys.stderr.flush()

        if old_mood != self.mood:
            self.image_uri = await make_image(self)

    async def decide_to_speak(
        self, is_in_deliberation, previous_utterance, previous_speaker
    ):
        response_fields = [("SPEAK_EAGERNESS", fuzzy_percent)]
        prompt = f"""{self.description_prompt(is_in_deliberation)}

{self.mood_prompt()}

{self.beliefs_prompt()}

{self.agent_sentiments_prompt()}

{self.previous_utterance_prompt(previous_utterance, previous_speaker)}

How eager are you to speak? Reply as a percentage in the following format:

{response_format_prompt(response_fields)}
"""
        parsed = await gen_formatted_response(prompt, response_fields)
        if parsed is None:
            sys.stderr.write("Failed to parse speaking intent, tossing a coin\n")
            sys.stderr.flush()
            speak_eagerness = random.choice(range(100))
        else:
            speak_eagerness = parsed["SPEAK_EAGERNESS"]
        self.speak_eagerness = speak_eagerness

    async def say(self, is_in_deliberation, previous_utterance, previous_speaker):
        prompt = f"""{self.description_prompt(is_in_deliberation)}

{self.mood_prompt()}

{self.agent_sentiments_prompt()}

{self.beliefs_prompt()}

{self.previous_utterance_prompt(previous_utterance, previous_speaker)}
"""
        if previous_speaker:
            prompt += f"You are {self.description}, reply to {previous_speaker.name} with a single sentence statement. Refer to what you know and believe."
        else:
            prompt += f"You are {self.description}. Try to convince the jury about your opinions. Be brief (one or two sentences). Refer to what you know and believe."

        utterance = await gen(prompt)
        utterance = utterance.strip('"')
        return utterance

    def is_certain(self):
        return abs(self.guilty_percent - self.innocent_percent) > 50

    def previous_utterance_prompt(self, previous_utterance, previous_speaker):
        if previous_utterance:
            return f"Previously {previous_speaker.name} said: {previous_utterance}"
        return ""

    def name_key(self):
        return re.sub(r"[^A-Z_]", "", self.name.upper().replace(" ", "_"))
