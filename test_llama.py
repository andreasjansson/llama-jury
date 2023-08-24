from llama import parse_formatted_response, response_format_prompt, fuzzy_percent

def test_parse_formatted_response():
    parsed = parse_formatted_response("""foo bar

MOOD:

i am happy

BELIEFS:

i believe i can fly

i believe i can touch the sky
GUILTY_PERCENT:

10
""", [("MOOD", str), ("BELIEFS", str), ("GUILTY_PERCENT", int)])

    assert parsed is not None
    assert parsed["MOOD"] == "i am happy"
    assert parsed["BELIEFS"] == """i believe i can fly

i believe i can touch the sky"""
    assert parsed["GUILTY_PERCENT"] == 10

    parsed = parse_formatted_response("""foo bar

MOOD: i am happy

BELIEFS: i believe i can fly

i believe i can touch the sky
GUILTY_PERCENT: 10
""", [("MOOD", str), ("BELIEFS", str), ("GUILTY_PERCENT", int)])

    assert parsed is not None
    assert parsed["MOOD"] == "i am happy"
    assert parsed["BELIEFS"] == """i believe i can fly

i believe i can touch the sky"""

    parsed = parse_formatted_response("""foo bar

MOOD: i am happy

BELIEFS: i believe i can fly

i believe i can touch the sky
GUILTY_PERCENT: foo
""", [("MOOD", str), ("BELIEFS", str), ("GUILTY_PERCENT", int)])
    assert parsed is None

    parsed = parse_formatted_response("""foo bar

MOOD: i am happy

BELIEFS: i believe i can fly

i believe i can touch the sky
""", [("MOOD", str), ("BELIEFS", str), ("GUILTY_PERCENT", int)])
    assert parsed is None

    parsed = parse_formatted_response("""MOOD: Grumpier than usual. I do not enjoy being stuck in this dull, pointless courtroom all day. I miss the thrill of battle and the fresh air of Qo'noS.

BELIEFS: This Human, Jerry Jenkins, looks like a scoundrel. He smells like one too. I can practically sense the stench of his illegal activities wafting through the air. His eyes are too wide and his voice is too loud - he's clearly hiding something. But... (pauses) ...I am not convinced that the prosecution has presented enough evidence to prove their case beyond a reasonable doubt. There are too many holes in their argument, too much room for doubt.

GUILTY_PERCENT: 60% (increased from 50%). My instincts tell me that Jenkins is guilty, but I need more information before I can be certain. As a Klingon warrior, I crave victory and justice - but I will not compromise my principles by convicting an innocent man.""", [("MOOD", str), ("BELIEFS", str), ("GUILTY_PERCENT", fuzzy_percent)])
    assert parsed["MOOD"] == "Grumpier than usual. I do not enjoy being stuck in this dull, pointless courtroom all day. I miss the thrill of battle and the fresh air of Qo'noS."
    assert parsed["BELIEFS"] == "This Human, Jerry Jenkins, looks like a scoundrel. He smells like one too. I can practically sense the stench of his illegal activities wafting through the air. His eyes are too wide and his voice is too loud - he's clearly hiding something. But... (pauses) ...I am not convinced that the prosecution has presented enough evidence to prove their case beyond a reasonable doubt. There are too many holes in their argument, too much room for doubt."
    assert parsed["GUILTY_PERCENT"] == 60

    parsed = parse_formatted_response("""foo bar

MOOD:

i am happy

BELIEFS:

i believe i can fly

i believe i can touch the sky
GUILTY PERCENT:

10
""", [("MOOD", str), ("BELIEFS", str), ("GUILTY_PERCENT", int)])

    assert parsed is not None
    assert parsed["MOOD"] == "i am happy"
    assert parsed["BELIEFS"] == """i believe i can fly

i believe i can touch the sky"""
    assert parsed["GUILTY_PERCENT"] == 10


def test_response_format_prompt():
    output = response_format_prompt([("MOOD", str), ("BELIEFS", str), ("GUILTY_PERCENT", int)])
    assert output == """MOOD:

BELIEFS:

GUILTY_PERCENT:"""


def test_fuzzy_percent():
    assert fuzzy_percent("60") == 60
    assert fuzzy_percent("60%") == 60
    assert fuzzy_percent("60.5%") == 60
    assert fuzzy_percent("""

    60%

    """) == 60
    assert fuzzy_percent("""

    60

    """) == 60
    assert fuzzy_percent("""

    60% (up from 40%)

    """) == 60
    assert fuzzy_percent("""
    i would say about 60% accurate

    """) == 60
    assert fuzzy_percent("""60

    i am more than 50 percent confident
    """) == 60
    assert fuzzy_percent("") is None
    assert fuzzy_percent("foo") is None
