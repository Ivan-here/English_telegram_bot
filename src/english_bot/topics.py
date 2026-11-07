"""Neutral starters with 30-minute automatic rotation and instant refresh."""

import time
from html import escape

from .ui import keyboard

ROTATION_SECONDS = 30 * 60
TOPICS = {
    "daily": ("☕ Everyday life", (
        "What is one small thing that can make an ordinary day more enjoyable?",
        "How do you usually decide what to do with a free afternoon?",
        "What kind of place do you like to visit for a short break?",
        "What is a simple meal you enjoy, and what do you like about it?",
        "How do you prefer to spend a quiet evening?",
        "What everyday task would you like to make easier?",
        "What is something interesting you noticed recently?",
        "Do you prefer planning your day or deciding things as you go?",
        "What makes a public space pleasant to spend time in?",
        "What is a small habit you find useful?",
        "How do you choose something new to try?",
        "What would your ideal relaxed morning look like?",
    )),
    "history": ("🏛 History & society", (
        "Which period of history would you like to understand better, and why?",
        "How can learning about everyday life help us understand the past?",
        "What invention do you think changed daily life in an interesting way?",
        "What can old buildings tell us about the people who used them?",
        "How might travel have changed the way societies exchanged ideas?",
        "What would you ask someone who lived a hundred years ago?",
        "Which historical change would you like someone to explain to you?",
        "What makes a museum exhibition interesting to you?",
        "How do you think people will describe our everyday life in the future?",
        "What can we learn by comparing different accounts of the same event?",
        "How has communication changed the way people organise their lives?",
        "What part of a town's history would you be curious to discover?",
    )),
    "science": ("💡 Science & ideas", (
        "What scientific question have you always been curious about?",
        "Which everyday technology would you like to understand better?",
        "What makes an explanation easy for you to understand?",
        "If you could watch one scientific experiment, what would you choose?",
        "What could people learn from exploring the ocean?",
        "What is an example of a clever solution to a simple problem?",
        "Which discovery would you enjoy learning the story behind?",
        "What would you like to know about how the human body works?",
        "How might a new invention change an ordinary day?",
        "What would you want to find out about another planet?",
        "When have you changed your mind after learning something new?",
        "What is something in nature that you would like science to explain?",
    )),
    "culture": ("🌍 Culture & travel", (
        "What would you like to learn about a place before visiting it?",
        "What kind of story do you enjoy in a book or film?",
        "How can food help someone discover a different culture?",
        "Would you rather explore a new city on foot or with a guide, and why?",
        "What makes a piece of music memorable to you?",
        "What is a local tradition you would be interested in learning about?",
        "What would you include in a one-day tour of a place you know?",
        "How do you choose a book, film, or programme to try?",
        "What kind of landscape would you like to visit?",
        "What can people learn from stories set in unfamiliar places?",
        "Would you prefer a busy travel schedule or time to explore slowly?",
        "What everyday detail do you notice first when you visit a new place?",
    )),
    "learning": ("📚 Work & learning", (
        "What is a skill you would enjoy learning, and how would you start?",
        "Do you prefer learning by reading, watching, or trying things yourself?",
        "What helps you stay focused on a task?",
        "What makes instructions clear and useful?",
        "How would you explain something you know well to a beginner?",
        "What kind of project would you enjoy doing with other people?",
        "How do you decide which task to do first?",
        "What makes a place comfortable for studying or working?",
        "What is something useful you learned outside a classroom?",
        "How can a short break help when a task feels difficult?",
        "Would you rather practise a skill a little each day or in longer sessions?",
        "What makes feedback helpful when you are learning something new?",
    )),
    "nature": ("🌿 Nature & environment", (
        "What kind of outdoor place do you enjoy spending time in?",
        "What changes in nature do you notice when a new season begins?",
        "Which animal would you like to learn more about?",
        "What makes a park useful and welcoming for different people?",
        "What would you like to know about how plants grow?",
        "How does the weather affect the activities you choose?",
        "What can people discover by observing a familiar outdoor place closely?",
        "Would you rather explore a forest, a coast, or a mountain area?",
        "What is a natural sound you find interesting or pleasant?",
        "How could a neighbourhood make more room for trees and plants?",
        "What would you be curious to see on a guided nature walk?",
        "How do you think cities and wildlife can share space?",
    )),
}


def rotation_index(topic, now=None):
    slot = int(time.time() if now is None else now) // ROTATION_SECONDS
    return slot % len(TOPICS[topic][1])


def starter(topic, now=None, index=None):
    index = rotation_index(topic, now) if index is None else index
    return TOPICS[topic][1][index % len(TOPICS[topic][1])]


def topic_screen(topic, now=None, index=None):
    index = rotation_index(topic, now) if index is None else index % len(TOPICS[topic][1])
    question = starter(topic, index=index)
    return (
        f"<b>{escape(TOPICS[topic][0])}</b>\n\n"
        f"<b>A question to get started</b>\n{escape(question)}\n\n"
        "<i>Reply by voice or text. Questions change automatically every 30 minutes. "
        "Tap Refresh for a different question now.</i>",
        keyboard([
            [("↻ Refresh question", f"refresh:{topic}:{index}")],
            [("‹ Topics", "topics"), ("⚙️ Settings", "settings")],
        ]),
    )
