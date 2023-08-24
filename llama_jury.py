import argparse
import re
import sys
from typing import Optional
import asyncio
import itertools
from dataclasses import dataclass, field
import random
from typing import Dict

from dotenv import load_dotenv

load_dotenv()


from llama import (
    gen,
    gen_formatted_response,
    response_format_prompt,
    fuzzy_percent,
)
import gpt
import db
from sd import make_image

ROOM_CHARACTERS = {
    "A": {
        "Aristotle": "The ancient Greek philosopher Aristotle",
        "Homer Simpson": "The funny but slightly dumb cartoon character Homer Simpson",
        "Agatha Christie": "The detective story author Agatha Christie",
        "Nikola Tesla": "The mad scientist polymath Nikola Tesla",
        "Dana Scully": "The intelligent, resourceful, and skeptical FBI agent Dana Scully",
        "Liutentant Worf": "The Klingon Lieutenant Worf from Star Trek TNG",
    },
    "B": {
        "Yoda": "The wise and powerful Jedi master Yoda",
        "Albert Einstein": "The genius physicist Albert Einstein",
        "Napoleon Bonaparte": "The ambitious French military leader Napoleon Bonaparte",
        "Count Dracula": "The bloodthirsty Romanian vampire Count Dracula",
        "Mother Teresa": "The compassionate and selfless nun Mother Teresa",
        "Mikhail Bakunin": "The Russian revolutionary anarchist Mikhail Bakunin",
    },
    "C": {
        "Al Capone": "The ruthless and notorious gangster Al Capone",
        "The Log Lady": "The mysterious Log Lady from Twin Peaks",
        "MacGyver": "The resourceful and ingenious agent MacGyver",
        "Confucius": "The wise and influential Chinese philosopher Confucius",
        "Marie Curie": "The pioneering and brilliant scientist Marie Curie",
        "The Terminator": "The Terminator cyborg played by Arnod Schwarzenegger",
    },
}

# Set to True to let the model decide who is most willing to speak.
# Set to False for faster deliberation
INTELLIGENTLY_PICK_NEXT_SPEAKER = True


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

You are currently {self.guilty_percent}% sure that the defendent is guity and {self.innocent_percent}% sure that the defendent is innocent."""

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
        if speaker is None:
            response_fields = [
                ("SUMMARY", str),
                ("MOOD", str),
                ("BELIEFS", str),
                ("GUILTY_PERCENT", fuzzy_percent),
                ("INNOCENT_PERCENT", fuzzy_percent),
            ]

            prompt += f"""{self.beliefs_prompt()}

The court says: {utterance}

You are {self.description}, in the signature voice of {self.name}, describe your updated summary of all evidence (detailed), mood (one word), beliefs (several bullet points), and certainty of guilt and innocence (percentages) in the following format:
"""
        else:
            prompt += f"""{self.agent_sentiments_prompt()}

{self.beliefs_prompt()}

{speaker.name} says: {utterance}

You are {self.description}, given your previous beliefs and what {speaker.name} said, in the signature voice of {self.description}, describe your updated mood (one word), new beliefs (several bullet points), updated certainty of guilt and innocence (percentages), and updated opinion about the speaker {speaker.name}'s views in relation to your own beliefs (concise) in the following format (do not output anything else):
"""
            opinion_key = "OPINION_ABOUT_" + re.sub(
                r"[^A-Z ]", "", speaker.name.upper().replace(" ", "_")
            )
            response_fields = [
                ("MOOD", str),
                ("BELIEFS", str),
                ("GUILTY_PERCENT", fuzzy_percent),
                ("INNOCENT_PERCENT", fuzzy_percent),
                (opinion_key, str),
            ]

        prompt += response_format_prompt(response_fields)
        parsed = await gen_formatted_response(prompt, response_fields)
        old_mood = self.mood
        if parsed:
            self.mood = parsed["MOOD"]
            self.beliefs = parsed["BELIEFS"]
            self.guilty_percent = parsed["GUILTY_PERCENT"]
            self.innocent_percent = parsed["INNOCENT_PERCENT"]
            if speaker is None:
                self.summary = parsed["SUMMARY"]
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

{previous_utterance_prompt(previous_utterance, previous_speaker)}

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

{previous_utterance_prompt(previous_utterance, previous_speaker)}
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


def previous_utterance_prompt(previous_utterance, previous_speaker):
    if previous_utterance:
        return f"Previously {previous_speaker.name} said: {previous_utterance}"
    return ""


async def generate_transcript():
    with open("transcript.txt") as f:
        example_transcript1 = f.read()
    with open("transcript2.txt") as f:
        example_transcript2 = f.read()
    transcript = await gpt.generate(
        f"""Generate a fictional court case. The suspected crime should be something a bit funny and not violent. Not too cutesy though. Generate a court transcript where the attorney and the prosecutor both interrogate witnesses. Make the outcome of the case somewhat ambiguous. Include opening and closing statements by both attorney and prosecutor. Start with a name for the case and the name of the defendant. Make everything as short as possible.

Split the transcript into blocks of 2-5 lines each, separated by newlines. Below are two examples of the form (but don't use the content of the examples, instead invent new stories):

Example transcript 1:

{example_transcript1}

Example transcript 2:

{example_transcript2}
"""
    )
    return transcript.split("\n\n")


async def summarize_verdict(agents):
    num_guilty = len([a for a in agents if a.guilty_percent - a.innocent_percent > 50])
    num_innocent = len(
        [a for a in agents if a.innocent_percent - a.guilty_percent > 50]
    )
    if num_innocent > num_guilty:
        verdict = "Not guilty"
    elif num_guilty > num_innocent:
        verdict = "Guilty"
    else:
        verdict = "Undecided"

    prompt = f"""You are chairman of the jury. Summarize for the court the beliefs of the members of the jury without mentioning individual jurors and end with the verdict {verdict}.

The beliefs of the jury are:
"""
    for agent in agents:
        prompt += f"* {agent.name}: {agent.beliefs}\n"

    return await gen(prompt)


def print_agents(agents):
    for agent in agents:
        print(f"\n{agent.name}")
        print(f"* Case summary:  {agent.summary}")
        print(f"* Case beliefs:  {agent.beliefs}")
        print(f"* Guilty %:      {agent.guilty_percent}")
        print(f"* Innocent %:    {agent.innocent_percent}")
        print(f"* Mood:          {agent.mood}")
        print("* Jury opinions:")
        for name, sentiment in agent.agent_sentiments.items():
            print(f"  * {name}: {sentiment}")
    print("\n")


def print_box(text):
    print("********************************")
    print(text)
    print("********************************")


async def main():
    parser = argparse.ArgumentParser(description="Llama Jury")
    parser.add_argument(
        "room", help="Name of the court room", choices=["A", "B", "C", "D"]
    )
    args = parser.parse_args()
    room = args.room
    db.init(room)

    characters = ROOM_CHARACTERS[room]
    agents = [Agent(name, description) for name, description in characters.items()]

    async with asyncio.TaskGroup() as tg:
        for agent in agents:
            other_agents = [a for a in agents if a != agent]
            tg.create_task(
                agent.set_preconceptions_about_fellow_jury_members(other_agents)
            )

    async with asyncio.TaskGroup() as tg:
        for agent in agents:
            tg.create_task(agent.set_initial_mood())

    print_agents(agents)
    db.save(room, agents=agents, evidence="The court is being asesmbled...")

    transcript = await generate_transcript()
    print("\n\n".join(transcript))
    for evidence in transcript:
        print_box(evidence)
        db.save(room, evidence=evidence)
        async with asyncio.TaskGroup() as tg:
            for agent in agents:
                tg.create_task(agent.hear(evidence, is_in_deliberation=False))

        print_agents(agents)
        db.save(room, agents=agents)

    print_box("The jury now goes into deliberation")
    db.save(room, evidence="The jury now goes into deliberation...")
    has_cleared_evidence = False

    previous_utterance = previous_speaker = None

    for i in itertools.count(start=0, step=1):
        other_agents = [a for a in agents if a != previous_speaker]
        if INTELLIGENTLY_PICK_NEXT_SPEAKER:
            async with asyncio.TaskGroup() as tg:
                for agent in agents:
                    tg.create_task(
                        agent.decide_to_speak(
                            is_in_deliberation=True,
                            previous_utterance=previous_utterance,
                            previous_speaker=previous_speaker,
                        )
                    )

            agent = random.choices(
                other_agents, weights=[a.speak_eagerness for a in other_agents], k=1
            )[0]
        else:
            agent = random.choice(other_agents)

        utterance = await agent.say(
            is_in_deliberation=True,
            previous_utterance=previous_utterance,
            previous_speaker=previous_speaker,
        )
        if previous_speaker:
            previous_speaker.latest_utterance = ""
        agent.latest_utterance = utterance
        for a in agents:
            a.latest_sentiment = ""

        if not has_cleared_evidence:
            db.save(room, evidence="")
            has_cleared_evidence = True

        db.save(room, agents=agents)

        previous_utterance = utterance
        previous_speaker = agent

        print_box(f"\n{agent.name} says: {utterance}\n")

        other_agents = [a for a in agents if a != agent]
        async with asyncio.TaskGroup() as tg:
            for a in other_agents:
                tg.create_task(
                    a.hear(is_in_deliberation=True, utterance=utterance, speaker=agent)
                )

        print_agents(agents)
        db.save(room, agents=agents)

        if i >= 3:
            if all(a.is_certain() for a in agents):
                break

    print_box("The jury has reached it's verdict")

    verdict = await summarize_verdict(agents)

    for a in agents:
        a.latest_utterance = ""
        a.latest_sentiment = ""

    print_box(verdict)
    db.save(room, agents=agents, verdict=verdict)


if __name__ == "__main__":
    asyncio.run(main())
