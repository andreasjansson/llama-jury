import sys
import time
import argparse
import asyncio
import random

from dotenv import load_dotenv

load_dotenv()


from llama import gen
import gpt
from db import DatabaseSession
from agent import Agent
from state import State, INITIAL_EVIDENCE, DELIBERATION_EVIDENCE

ROOM_CHARACTERS = {
    "A": {
        "Aristotle": "The ancient Greek philosopher Aristotle",
        "Homer Simpson": "The funny but slightly dumb cartoon character Homer Simpson",
        "Agatha Christie": "The detective story author Agatha Christie",
        "Nikola Tesla": "The mad scientist polymath Nikola Tesla",
        "Dana Scully": "The intelligent, resourceful, and skeptical FBI agent Dana Scully",
        "Lieutenant Worf": "The Klingon Lieutenant Worf from Star Trek TNG",
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
    "dev-A": {
        "Aristotle": "The ancient Greek philosopher Aristotle",
        "Homer Simpson": "The funny but slightly dumb cartoon character Homer Simpson",
        "Agatha Christie": "The detective story author Agatha Christie",
        "Nikola Tesla": "The mad scientist polymath Nikola Tesla",
        "Dana Scully": "The intelligent, resourceful, and skeptical FBI agent Dana Scully",
        "Lieutenant Worf": "The Klingon Lieutenant Worf from Star Trek TNG",
    },
    "dev-B": {
#        "Yoda": "The wise and powerful Jedi master Yoda",
#        "Albert Einstein": "The genius physicist Albert Einstein",
        "Napoleon Bonaparte": "The ambitious French military leader Napoleon Bonaparte",
        "Count Dracula": "The bloodthirsty Romanian vampire Count Dracula",
#        "Mother Teresa": "The compassionate and selfless nun Mother Teresa",
#        "Mikhail Bakunin": "The Russian revolutionary anarchist Mikhail Bakunin",
    },
    "dev-C": {
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


async def generate_transcript():
    with open("transcript.txt") as f:
        example_transcript1 = f.read()
    with open("transcript2.txt") as f:
        example_transcript2 = f.read()
    transcript = await gpt.generate(
        f"""Generate a fictional court case. The suspected crime should be something a bit funny and not violent. Not too cutesy though. Generate a court transcript where the attorney and the prosecutor both interrogate witnesses. Make the outcome of the case somewhat ambiguous. Include opening and closing statements by both attorney and prosecutor. Start with a name for the case and the name of the defendant. Make everything as short as possible.

Split the transcript into blocks of 2-5 lines each, separated by newlines. Below are two examples of the form (but don't use the content of the examples, instead invent a completely new story line. Feel free to include strange bits of evidence, drawing inspiration from science fiction, detective stories, gangster movies, historical events, etc.):

Example transcript 1:

{example_transcript1}

Example transcript 2:

{example_transcript2}
"""
    )
    return transcript


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
        "rooms",
        help="Names of the court rooms",
        choices=["A", "B", "C", "dev-A", "dev-B", "dev-C"],
        nargs="+",
    )
    args = parser.parse_args()
    rooms = args.rooms

    async with asyncio.TaskGroup() as tg:
        for room in rooms:
            tg.create_task(run_court(room))


async def run_court(room):
    db = DatabaseSession(room)

    state = await State.load(db, room)
    while True:
        match state.current_step():
            case state.EMPTY:
                await new_case(state)
            case state.EMPTY_CASE:
                await initialize_agents_and_transcripts(state)
            case state.PRESENTING_EVIDENCE:
                await next_evidence(state)
            case state.AWAITING_UTTERANCE:
                await next_utterance(state)
            case state.AWAITING_SENTIMENT:
                await next_sentiment(state)
            case state.AWAITING_VERDICT:
                await create_verdict(state)
            case state.COMPLETE:
                time.sleep(30)
                await new_case(state)
            case state.INVALID:
                sys.stderr.write("Invalid state!\n")
                sys.stderr.flush()
                await new_case(state)


async def new_case(state):
    state.reset_with_new_case()


async def initialize_agents_and_transcripts(state):
    async with asyncio.TaskGroup() as tg:
        tg.create_task(initialize_agents(state))
        tg.create_task(initialize_transcript(state))


async def initialize_agents(state):
    characters = ROOM_CHARACTERS[state.room]
    state.agents = [Agent(name, description) for name, description in characters.items()]

    async with asyncio.TaskGroup() as tg:
        for agent in state.agents:
            other_agents = [a for a in state.agents if a != agent]
            tg.create_task(
                agent.set_preconceptions_about_fellow_jury_members(other_agents)
            )

    async with asyncio.TaskGroup() as tg:
        for agent in state.agents:
            tg.create_task(agent.set_initial_mood())

    print_agents(state.agents)
    state.evidence = INITIAL_EVIDENCE
    state.save("agents", "evidence")


async def initialize_transcript(state):
    transcript = await generate_transcript()
    state.transcript = transcript
    state.save("transcript")


async def next_evidence(state):
    state.evidence = state.next_evidence()
    print_box(state.evidence)
    state.save("evidence")
    if state.evidence == DELIBERATION_EVIDENCE:
        return

    async with asyncio.TaskGroup() as tg:
        for agent in state.agents:
            tg.create_task(agent.hear(state.evidence, is_in_deliberation=False))

    print_agents(state.agents)
    state.save("agents")


async def next_utterance(state):
    previous_speaker = state.previous_speaker()
    previous_utterance = state.previous_utterance()
    other_agents = [a for a in state.agents if a != previous_speaker]
    if INTELLIGENTLY_PICK_NEXT_SPEAKER:
        async with asyncio.TaskGroup() as tg:
            for agent in state.agents:
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
    for a in state.agents:
        a.latest_sentiment = ""

    if state.evidence != "":
        state.evidence = ""
        state.save("evidence")

    state.save("agents")
    print_box(f"\n{agent.name} says: {utterance}\n")


async def next_sentiment(state):
    other_agents = [a for a in state.agents if a != state.previous_speaker()]
    async with asyncio.TaskGroup() as tg:
        for a in other_agents:
            tg.create_task(
                a.hear(is_in_deliberation=True, utterance=state.previous_utterance(), speaker=state.previous_speaker())
            )

    print_agents(state.agents)
    state.save("agents")
    state.num_deliberation_steps += 1


async def create_verdict(state):

    print_box("The jury has reached it's verdict")

    state.verdict = await summarize_verdict(state.agents)

    for a in state.agents:
        a.latest_utterance = ""
        a.latest_sentiment = ""

    print_box(state.verdict)
    state.save("agents", "verdict")


if __name__ == "__main__":
    asyncio.run(main())
