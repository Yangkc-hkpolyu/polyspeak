"""Reviewed institutional excerpts, with provenance kept through a practice turn."""
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import re

DATA = json.loads((Path(__file__).parent / "data/collected_questions.json").read_text(encoding="utf-8"))
# Keep source data and original-language titles intact on disk. Present English labels
# in the application while preserving source URLs and original provenance.
contains_cjk = lambda value: bool(re.search(r"[\u4e00-\u9fff]", value))
publishers = {"新东方在线": "New Oriental Online", "新东方": "New Oriental", "TestDaily 厚朴优学": "TestDaily", "雅思哥": "IELTS Bro"}
topics = {"个人目标":"Personal goals", "健康习惯":"Healthy habits", "文化节庆":"Cultural celebrations", "阅读":"Reading", "友谊":"Friendship", "目标与成就":"Goals and achievements", "兴趣爱好":"Hobbies", "赠送礼物":"Giving gifts", "用餐习惯":"Eating habits", "户外空间":"Outdoor spaces", "天气":"Weather", "睡眠":"Sleep", "园艺":"Gardening", "音乐":"Music", "艺术与表达":"Art and expression", "学习方式":"Learning methods", "时间管理":"Time management", "个人成长":"Personal growth", "电影":"Films", "日常采购":"Shopping", "历史":"History", "远程办公":"Remote work"}

topics.update(dict(line.split("|", 1) for line in """你住所适合所有人吗|Housing suitability
你喜欢你住的地方吗|Your home
你住你国家哪个地方|Where you live
你最喜欢家乡什么|Your hometown
家乡有讨厌的地方吗|Your hometown
你住在家乡多久了|Your hometown
你家乡大吗|Your hometown
你家乡改变大吗|Changes in your hometown
哪个科目有挑战性|Challenging subjects
兴趣于学习有多重要|Interest in learning
你学校环境怎么样|School environment
你学校是学习好去处|School environment
你想改变学校哪部分|Improving your school
购物时的优质服务|Good service while shopping
演讲经历|Giving a speech
在他人帮助下做的决定|A decision made with help
旅途中有趣的建筑|An interesting building on a trip
你喜欢你的学校吗|Your school
你学校在哪|Your school
学习和父母生活区别|Study and family life
你一周学多少时间|Study habits
你喜欢什么学习方法|Learning methods
你学习用什么技术|Technology for learning
你对你专业感兴趣吗|Your field of study
你喜欢什么时候工作|Work schedule
你喜欢你的专业吗|Your field of study
你未来愿意住乡下吗|Living in the countryside
从窗户看能看到什么|The view from your window
你最喜欢哪个房间|Your favorite room
你通常做什么|Daily activities
你在那里住了多久了|Your home
你独居或与家人同住|Your household
你打算长期住这里吗|Your home
你住独栋住宅或公寓|Your home
你家人经常都在哪里|Your household
你城市的交通完善吗|City transport
公司设放松室的优势|Relaxation spaces at work
公司让你放松的地方|Relaxation spaces at work
未来工作有哪些挑战|Future work challenges
你曾经考虑换工作吗|Changing jobs
工作场所哪些需改进|Improving the workplace
你工作环境是否良好|Your work environment
你每周工作多少小时|Work hours
工作中谁的帮助最大|Help at work
你能否高效管理时间|Time management
你工作是否使用技术|Technology at work
你向往什么工作|Your ideal job
专业选择什么最重要|Choosing a major
你认为有趣吗|Personal interests
你怀念学生时代吗|Student life
你喜欢你的工作吗|Your job
中国最流行什么专业|Popular majors in China
你为何选择这份工作|Choosing a job
你未来想成为什么|Future ambitions
为什么选择这个专业|Choosing a major
你的工作是什么|Your job
你的专业是什么|Your field of study
你工作了还是学生|Work or study
节约时间|Saving time
受欢迎的人|A popular person
靠近自然的地方|A place close to nature
欣赏的运动员|An athlete you admire
公共场所丢东西|Losing something in public
喜欢的建筑|A building you like
你享受的聚会|A gathering you enjoyed
帮别人提升健康|Helping someone improve their health
教导你的人|Someone who taught you
不喜欢的短途旅行|A short trip you disliked
令人兴奋的书|An exciting book
浪费时间的活动|A time-wasting activity
拥挤的地方|A crowded place
做手工的人|A person who makes things by hand
喜欢历史的人|A person interested in history
和朋友度过的美好夜晚|A pleasant evening with friends
有用的书|A useful book
感兴趣的科学学科|A science subject that interests you
弄坏东西|Breaking something
社交媒体趣事|An interesting social media post
第一次用外语交流|First conversation in a foreign language
家中的老物件|An old object at home
欣赏的有创造力的人|A creative person you admire
首次尝试的兴奋活动|An exciting first-time activity
有好习惯的朋友|A friend with a good habit
别人向你道歉的经历|A time someone apologized
享受的晚餐|A dinner you enjoyed
突然停电的经历|A sudden power outage
攒钱想要买的物品|Something you are saving to buy
嘈杂之地|A noisy place
尊敬的长辈|An older person you respect
好的服务|Good service
采访名人|Interviewing a celebrity
有条理的人|An organized person
自然之地|A natural place
小时候学到的技能|A skill learned as a child
喜欢拍照的人|A person who enjoys photography
听不感兴趣的话|Listening to something uninteresting
传统故事|A traditional story
想提升的天赋|A talent to improve
经营家族企业的人|A person in a family business
想再去的旅行|A trip you would take again
迷路的经历|Getting lost
重要的好朋友|An important friend
告诉朋友实情的经历|Telling a friend the truth
想多了解的野生动物|Wildlife you want to learn about
想去的树木很多的地方|A wooded place to visit
擅长音乐的朋友|A friend who is good at music""".splitlines()))
for q in DATA["questions"]:
    if contains_cjk(q.get("topic", "")):
        q["topic"] = topics.get(q["topic"], q["text"])
for source in DATA["sources"]:
    source["publisher"] = publishers.get(source.get("publisher"), source.get("publisher"))
    if contains_cjk(source.get("title", "")):
        source["original_title"] = source["title"]
        source["title"] = "Source article (original language)"
    if contains_cjk(source.get("topic", "")):
        source["topic"] = next((q["topic"] for q in DATA["questions"] if q["source_id"] == source["id"]), "Speaking practice")
    if contains_cjk(source.get("note", "")):
        source["note"] = "The article has conflicting dates in an afternoon-session heading; only the morning-session art topic under the title date was included."
for note in DATA["access_notes"]:
    note["publisher"] = publishers.get(note.get("publisher"), note.get("publisher"))
    if note.get("kind") == "prediction":
        note["title"] = "IELTS September–December 2026 topic predictions"
        note["description"] = "Institutional predictions are not counted as recalled exam questions and have not been imported."
    else:
        note["title"] = "IELTS Bro speaking question bank"
        note["description"] = "The public entry point is available, but no questions were returned during review. See its website or app. Not included in the question count."
SOURCE_BY_ID = {s["id"]: s for s in DATA["sources"]}


def collection_sets(question_factory):
    sets = []
    for entry in DATA["questions"]:
        source = SOURCE_BY_ID[entry["source_id"]]
        item = question_factory(entry["stage"], entry["text"], source_id=entry["source_id"])
        item.update({key: deepcopy(entry[key]) for key in ("source_kind", "wording", "topic", "season")})
        item["bank_question_id"] = entry["id"]
        item["provenance"] = {key: source[key] for key in ("publisher", "title", "url", "published_on", "reported_exam_on", "verified_on") if source.get(key)}
        item["context"] = "Topic: " + entry["topic"] + ". This is an excerpt; see the source for the full task card and questions."
        if entry.get("editorial_edits"):
            item["editorial_edits"] = deepcopy(entry["editorial_edits"])
        sets.append({"id": "bank-" + entry["id"], "exam": entry["exam"], "title": entry["topic"], "kind": entry["source_kind"], "from_collection": True, "mock_allowed": False, "questions": [item]})
    return sets


def collection_catalog():
    items = deepcopy(DATA["questions"])
    for item in items:
        item["set_id"] = "bank-" + item["id"]
    return {"collected_questions": items, "web_sources": deepcopy(DATA["sources"]), "access_notes": deepcopy(DATA["access_notes"]), "collection_stats": {"questions": len(items), "sources": len(DATA["sources"]), "by_exam": dict(Counter(q["exam"] for q in items)), "by_season": dict(Counter(q["season"] for q in items)), "by_wording": dict(Counter(q["wording"] for q in items))}}
