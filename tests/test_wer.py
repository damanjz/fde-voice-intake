import pytest

from app.wer import corpus_wer, edit_distance, number_to_words, wer, wer_tokens


def test_identical_is_zero():
    assert wer("where is my order", "Where is my order?") == 0.0


def test_substitution_insertion_deletion():
    assert wer("a b c d", "a x c d") == pytest.approx(0.25)
    assert wer("a b c d", "a b c d e") == pytest.approx(0.25)
    assert wer("a b c d", "a b d") == pytest.approx(0.25)


def test_empty_cases():
    assert wer("", "") == 0.0
    assert wer("", "something") == 1.0
    assert wer("hello there", "") == 1.0


def test_can_exceed_one():
    assert wer("hi", "a b c") == pytest.approx(3.0)


def test_punctuation_case_and_hyphen_ignored():
    assert wer("Moka Pot, 3-cup.", "moka pot three cup") == 0.0


def test_numbers_compared_as_words():
    assert wer("two grinders", "2 grinders") == 0.0
    assert wer("one thousand two hundred ninety nine rupees", "1,299 rupees") == 0.0


def test_number_to_words():
    assert number_to_words(0) == "zero"
    assert number_to_words(64) == "sixty four"
    assert number_to_words(1150) == "one thousand one hundred fifty"
    assert number_to_words(305) == "three hundred five"


def test_order_ids_normalised_only_when_asked():
    ref = "where is my order L C one one five zero"
    hyp = "Where is my order LC-1150?"
    assert wer(ref, hyp, normalise_ids=True) == 0.0
    assert wer(ref, hyp, normalise_ids=False) >= 0.5
    assert wer("el see eleven fifty", "LC 1150", normalise_ids=True) == 0.0


def test_wrong_id_counts_as_one_error():
    ref = "where is my order L C one one five zero"
    hyp = "Where is my order LC-1015"
    assert wer(ref, hyp, normalise_ids=True) == pytest.approx(1 / 5)


def test_edit_distance():
    assert edit_distance(["a", "b", "c"], ["a", "x", "c"]) == 1
    assert edit_distance(list("kitten"), list("sitting")) == 3


def test_corpus_wer_weights_by_length():
    pairs = [("a b c d e f g h i j", "a b c d e f g h i j"), ("x y", "p q")]
    assert corpus_wer(pairs) == pytest.approx(2 / 12)


def test_tokens():
    assert wer_tokens("It's LC-1150!", True) == ["its", "lcid1150"]
