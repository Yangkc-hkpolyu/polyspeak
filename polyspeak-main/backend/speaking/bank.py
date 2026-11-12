"""Attributed official excerpts and independently authored practice sets.

Full public official documents are linked and downloaded separately; excerpts
below stay short. Original questions are never labelled as past exam papers.
"""
from copy import deepcopy
from .collected_bank import collection_catalog, collection_sets

IELTS_URL = "https://ielts.org/cdn/ielts-downloadable-assets/ielts-sample-tests/ielts-speaking-sample-tasks-2023.pdf"
ETS_ROOT = "https://www.ets.org/content/dam/ets-org/pdfs/toefl/"
SOURCES = [
    {"id": "ielts-sample", "exam": "ielts", "title": "IELTS Official Speaking Sample Tasks", "url": IELTS_URL, "filename": "ielts-speaking-sample-tasks.pdf", "pages": "PDF pages 3–7", "kind": "official_sample", "description": "Questions about hometowns and homes, a long turn about an important possession, and discussions about consumer values and advertising; includes candidate responses.", "question_count": 14},
    {"id": "ets-full-1", "exam": "toefl", "title": "ETS 2026 Full-length Practice Test 1", "url": ETS_ROOT + "toefl-ibt-full-length-practice-test-1.pdf", "filename": "toefl-2026-full-1.pdf", "pages": "PDF pages 34–35", "kind": "official_sample", "description": "Seven Listen and Repeat items set in a zoo, plus four interview questions about city life.", "question_count": 11},
    {"id": "ets-full-2", "exam": "toefl", "title": "ETS 2026 Full-length Practice Test 2", "url": ETS_ROOT + "toefl-ibt-full-length-practice-test-2.pdf", "filename": "toefl-2026-full-2.pdf", "pages": "PDF pages 35–36", "kind": "official_sample", "description": "Seven Listen and Repeat items set in a campus gym, plus four interview questions about commuting habits.", "question_count": 11},
    {"id": "ets-teacher-1", "exam": "toefl", "title": "ETS Teacher Resources Practice Test 1", "url": ETS_ROOT + "toefl-ibt-teachers-resources-practice-test-1.pdf", "filename": "toefl-2026-teacher-1.pdf", "pages": "PDF pages 33–34", "kind": "official_sample", "description": "Seven Listen and Repeat items set at a university orientation event, plus four interview questions about work-life balance.", "question_count": 11},
    {"id": "ets-teacher-2", "exam": "toefl", "title": "ETS Teacher Resources Practice Test 2", "url": ETS_ROOT + "toefl-ibt-teachers-resources-practice-test-2.pdf", "filename": "toefl-2026-teacher-2.pdf", "pages": "PDF pages 35–36", "kind": "official_sample", "description": "Seven Listen and Repeat items about borrowing and returning library books, plus four interview questions about exercise habits.", "question_count": 11},
    {"id": "ets-rubric", "exam": "toefl", "title": "ETS 2026 Speaking Rubrics", "url": ETS_ROOT + "speaking-rubrics.pdf", "filename": "toefl-speaking-rubrics.pdf", "pages": "PDF pages 1–2", "kind": "official_rubric", "description": "Official scoring descriptors for Listen and Repeat and Take an Interview tasks."},
    {"id": "ets-overview", "exam": "toefl", "title": "ETS Updated TOEFL iBT Test Overview", "url": ETS_ROOT + "toefl-ibt-test-overview.pdf", "filename": "toefl-2026-overview.pdf", "pages": "Speaking Sample Tasks", "kind": "official_format", "description": "The updated 2026 test structure, speaking task types, and timing information."},
]
FORMAT_SOURCES = [
    {"title": "IELTS official speaking test format", "url": "https://ielts.org/take-a-test/test-types/ielts-academic-test/ielts-academic-format-speaking"},
    {"title": "ETS official speaking task types", "url": "https://www.ets.org/toefl/test-takers/ibt/about/content/speaking.html"},
    {"title": "ETS teacher resources and accompanying original audio", "url": "https://www.ets.org/toefl/teachers-advisors-agents/ibt/teaching/preparing-students.html"},
]


def question(stage, text, *, card=None, source_id=None):
    kind = "repeat" if stage == "repeat" else "long_turn" if stage == "part2" else "discussion" if stage == "part3" else "interview"
    return {"stage": stage, "task_type": kind, "text": text, "card": card or [], "source_id": source_id, "source_kind": "official_excerpt" if source_id else "original_practice", "prepare_seconds": 60 if stage == "part2" else 0, "answer_seconds": 120 if stage == "part2" else 60 if stage == "part3" else 20 if stage == "rounding" else 45 if stage == "interview" else 30}


def ielts_set(key, title, p1, long_turn, card, rounding, p3):
    items = [question("part1", x) for x in p1]
    items += [question("part2", long_turn, card=card), question("rounding", rounding)]
    items += [question("part3", x) for x in p3]
    return {"id": key, "exam": "ielts", "title": title, "kind": "original_practice", "mock_allowed": True, "questions": items}


def toefl_set(key, title, repeat, interview):
    items = []
    for i, text in enumerate(repeat):
        item = question("repeat", text)
        item["answer_seconds"] = 8 if i < 2 else 10 if i < 5 else 12
        items.append(item)
    items += [question("interview", text) for text in interview]
    return {"id": key, "exam": "toefl", "title": title, "kind": "original_practice", "mock_allowed": True, "questions": items}


SETS = [
    ielts_set("ielts-learning", "Learning beyond the classroom", [
        "Are you studying at the moment, or have you started working?",
        "Which part of a typical weekday do you look forward to?",
        "When you need to concentrate, what sort of surroundings do you choose?",
        "How do you usually organise tasks when several things are due?",
        "What did you enjoy learning before you went to university?",
        "Do you often ask other people for advice about your studies?",
        "How has your way of taking notes developed over time?",
        "What would make your usual study space more comfortable?",
    ], "Describe a practical skill that you learned from another person.", ["Who helped you and what the skill was", "How you practised it together", "A difficulty you encountered", "Why being able to do it matters to you"], "Have you had a chance to pass this skill on to somebody else?", [
        "How do people decide whether a skill is worth the effort of learning?",
        "In what ways can a community help adults keep learning?",
        "What might be lost when practical teaching moves entirely online?",
        "Who should take responsibility for teaching skills that employers need?",
    ]),
    ielts_set("ielts-places", "Places, neighbourhoods & change", [
        "What do you normally notice first when you arrive in a new area?",
        "Where do you go near home when you want a quiet moment?",
        "What is your neighbourhood like early in the morning?",
        "Do you find it easy to get around the area where you live?",
        "How do you usually find out about a new local business?",
        "Have the shops near your home changed since you moved there?",
        "What outdoor activity would you like to do more often?",
        "Would you enjoy living somewhere with fewer cars?",
    ], "Describe a public space you visited that made you feel welcome.", ["Where you found it", "What people were doing there", "A detail that helped you feel comfortable", "How you would improve a similar place near your home"], "Would you bring someone else to that place?", [
        "What makes shared public spaces work well for different generations?",
        "How should a city choose between more housing and more open space?",
        "What can residents contribute when a neighbourhood is being redesigned?",
        "How could changes in transport affect where communities gather?",
    ]),
    ielts_set("ielts-technology", "Everyday choices & technology", [
        "What is the first useful thing you do on your phone in the morning?",
        "When do you prefer doing something without using a screen?",
        "How do you decide whether to try a new app?",
        "What do you do with devices you no longer need?",
        "Do you enjoy repairing small things yourself?",
        "How do you usually remember important dates?",
        "Has the way you keep in touch with friends changed recently?",
        "What would you find difficult about a day without internet access?",
    ], "Describe a small change you made that improved your daily routine.", ["What you changed", "What prompted you to try it", "How you kept the change going", "What difference it made after a few weeks"], "Is this a change you would recommend to a friend?", [
        "Why do some useful habits spread quickly while others do not?",
        "How much influence should technology have over everyday decisions?",
        "What could organisations do to make sustainable choices easier?",
        "How might people's expectations of convenience change in the future?",
    ]),
    toefl_set("toefl-makerspace", "Campus makerspace & student projects", [
        "Safety glasses are beside the door.",
        "You can collect a toolbox from reception.",
        "The green tables are reserved for group projects.",
        "Please ask a technician before switching on any unfamiliar equipment.",
        "Students must complete the short safety workshop before using the cutting tools.",
        "If a machine stops unexpectedly, leave it switched off and report the problem to our staff.",
        "Although most materials are included in your membership, you will need to book specialist equipment at least a day ahead.",
    ], [
        "Think about a project you completed with other students. What was it, and what part of the work did you enjoy?",
        "Would you rather learn to use a new tool by experimenting or by watching a demonstration? Explain your choice.",
        "A university is deciding whether to fund more shared project spaces or more individual study rooms. Which would you support, and why?",
        "If students could make almost any object cheaply on campus, how might that change the way they learn? Give a benefit and a possible drawback.",
    ]),
    toefl_set("toefl-garden", "Community garden & everyday food", [
        "The garden gate opens at nine.",
        "Spare gloves are in the blue box.",
        "Each group looks after one small vegetable bed.",
        "Use the water from these tanks whenever the weather is dry.",
        "After collecting your tools, write your name on the sheet next to the shed.",
        "Any vegetables that are ready to harvest will be shared among the volunteers at the end of the afternoon.",
        "If you cannot come for your usual session, please tell the coordinator so that another volunteer can look after your plants.",
    ], [
        "When you are busy with study or work, how do you decide what to eat? Describe one thing that influences your choice.",
        "Imagine you can either prepare lunch at home or buy lunch near campus. Which option would suit you better, and why?",
        "Some universities teach students how to grow and cook simple food. Do you think this is a useful use of university resources? Explain.",
        "How might a large increase in locally grown food change a city? Discuss one possible advantage and one difficulty.",
    ]),
    toefl_set("toefl-media", "Student media room & digital communication", [
        "The microphones are in this cupboard.",
        "Please record your name before you begin.",
        "A red light means the room is in use.",
        "You can adjust the headphones with the dial beside the screen.",
        "Remember to save your recording before logging out of the studio computer.",
        "If your group needs extra time, check the booking calendar to see whether the next session is available.",
        "Because these recordings may be used by other students, make sure that everyone who speaks has agreed to take part.",
    ], [
        "What kind of online content do you find most useful for learning something new? Explain with an example.",
        "Would you prefer to explain an idea in a short audio recording or in a written message? Give reasons for your preference.",
        "Some teachers ask students to produce public videos instead of traditional assignments. What do you think about this approach?",
        "As automatic translation becomes more common, how could communication between students from different countries change? Describe a benefit and a concern.",
    ]),
]

# Short quotations from the IELTS document; full source is linked.
SETS.append({"id": "ielts-official-excerpts", "exam": "ielts", "title": "Official short excerpts · Hometowns, homes and important possessions", "kind": "official_excerpt", "mock_allowed": False, "questions": [
    {**question("part1", "What kind of place is it?", source_id="ielts-sample"), "context": "Topic: your hometown or village."},
    {**question("part1", "How long have you lived there?", source_id="ielts-sample"), "context": "Topic: the home where you currently live."},
    question("part2", "Describe something you own which is very important to you.", card=["Explain how you obtained the item, how long you have had it, what you use it for, and why it matters to you. This is a summary of the cue-card points; see the official PDF for the full card."], source_id="ielts-sample"),
]})
for key, title, text in [
    ("ets-full-1", "Zoo", "We have a variety of wildlife."),
    ("ets-full-2", "Campus gym", "Welcome to our campus gym."),
    ("ets-teacher-1", "University orientation", "Welcome to our event."),
    ("ets-teacher-2", "Library", "Welcome to the library."),
]:
    item = question("repeat", text, source_id=key)
    item["answer_seconds"] = 8
    SETS.append({"id": key + "-excerpt", "exam": "toefl", "title": "Official Listen and Repeat excerpt · " + title, "kind": "official_excerpt", "mock_allowed": False, "questions": [item]})


SETS.extend(collection_sets(question))


def get_set(set_id):
    for item in SETS:
        if item["id"] == set_id:
            return deepcopy(item)
    raise ValueError("This practice set could not be found. Please choose another set.")


def catalog():
    return {"sets": [{k: v for k, v in x.items() if k != "questions"} | {"count": len(x["questions"]), "sections": sorted({q["stage"] for q in x["questions"] if q["stage"] != "rounding"})} for x in SETS], "sources": deepcopy(SOURCES), "format_sources": FORMAT_SOURCES, "verified_on": "2026-10-24", "notice": "Institutional topic banks, recalled exam questions, official samples, and original practice sets are labelled separately. Recalled questions are not officially confirmed exam questions, and translations or paraphrases do not reproduce the original English exam wording.", **collection_catalog()}
