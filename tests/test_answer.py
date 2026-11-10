import pytest

from app.answer import classify

YES = [
    "Yes", "Yes.", "yes please", "Yes, please go ahead.", "Yeah, sure, do it.", "yeah", "yep", "yup", "Sure", "sure go ahead",
    "Okay", "OK", "okay please", "Confirm", "confirmed", "go ahead", "Please go ahead", "do it", "Please do", "haan",
    "Haan, bana do", "ji", "Ji haan", "haan ji", "yes yes", "Yesss", "yeah please", "absolutely", "Yes, I do",
    "Yes please, thank you", "Haan karo", "Theek hai ji",
]
NO = [
    "No", "No.", "no thanks", "No, cancel that.", "No thanks, I will keep it.", "Nope", "nah", "nahi", "Nahin", "cancel",
    "Cancel it", "cancel that", "stop", "never mind", "Nevermind", "No, never mind", "no no no", "No, I don't want it",
    "no please", "Nahi, mat karo", "No cancel it please",
]
# Each of these carries a yes word (or a no word) but is NOT a clear answer: nothing may be sent.
HARD_NEGATIVES = [
    "Yeah, no", "Yeah no.", "Ji nahi", "Haan nahi", "Okay, bye", "Ha ha", "Haha", "Do it later", "Yes, no, wait", "Yeah, cancel it",
    "Yes please don't", "Yes but", "Yes, but what is the fee?", "Yes wait", "Ok so what is the fee?", "No wait", "No, but yes",
    "Don't cancel it", "Do not stop", "Okay, I will think about it", "Yes tomorrow", "Yeah maybe", "Sure, later", "Haan, kal karo",
    "Yes, what about the pickup fee", "Okay hold on", "Yes I want to talk to a person", "Hmm", "um", "", "   ", "What is my order status?",
    "Where is my order LC-1150?", "Thank you", "Bye", "Cancel the other order", "Ok thanks bye",
]


@pytest.mark.parametrize("text", YES)
def test_yes(text):
    assert classify(text) == "yes", text


@pytest.mark.parametrize("text", NO)
def test_no(text):
    assert classify(text) == "no", text


@pytest.mark.parametrize("text", HARD_NEGATIVES)
def test_hard_negatives_are_not_answers(text):
    assert classify(text) is None, text


def test_long_utterances_are_never_answers():
    assert classify("yes " * 9) is None
    assert classify("yes please go ahead and do it now thank you very much") is None
