import pytest

from app.normalize import find_order_ids, normalize_order_ids, prepare_transcript, strip_fillers


def ids(text: str) -> list[str]:
    return normalize_order_ids(text).order_ids


@pytest.mark.parametrize(
    "spoken",
    [
        "LC-1150", "lc-1150", "LC 1150", "LC1150", "L.C. 1150", "L C 1150", "L-C 1150", "LC#1150", "LC, 1150",
        "L C one one five zero", "LC one one five zero", "el see eleven fifty", "El See eleven fifty",
        "el sea eleven fifty", "elsie eleven fifty", "Elsie 11:50", "L C 11 50", "L C 1 1 5 0", "LC 11, 50",
        "LC 1,150", "LC double one five zero", "LC double one fifty",
        "L C eleven hundred fifty", "LC one thousand one hundred fifty", "LC one thousand, one hundred and fifty",
        "LC one one hundred fifty", "LC ek ek paanch zero", "LC gyarah sau pachaas", "el see gyarah pachaas",
        "LC eleven five zero", "LC one one fifty", "LC 11 five oh", "LC 1150.", "order number LC one one five zero",
        "L C no. 1150", "L C number eleven fifty", "LC dash 1150", "L C is one one five zero", "al see 1150",
        "ell see eleven fifty", "l see one one five zero", "LC eleven fifty",
    ],
)
def test_1150_forms(spoken):
    assert ids(spoken) == ["LC-1150"], spoken


@pytest.mark.parametrize(
    "spoken,expected",
    [
        ("L C ten oh one", "LC-1001"),
        ("el see ten oh five", "LC-1005"),
        ("L C one zero zero one", "LC-1001"),
        ("LC ten fifteen", "LC-1015"),
        ("LC one zero one five", "LC-1015"),
        ("LC ten fifty", "LC-1050"),
        ("LC one zero five zero", "LC-1050"),
        ("LC eleven fifteen", "LC-1115"),
        ("LC eleven oh nine", "LC-1109"),
        ("el see twelve hundred", "LC-1200"),
        ("LC one two zero zero", "LC-1200"),
        ("LC twelve oh oh", "LC-1200"),
        ("LC one thousand fifty", "LC-1050"),
        ("LC one thousand and fifty", "LC-1050"),
        ("LC one thousand one", "LC-1001"),
        ("LC eleven twenty five", "LC-1125"),
        ("LC one one two five", "LC-1125"),
        ("LC eleven eighty eight", "LC-1188"),
        ("LC one one eight eight", "LC-1188"),
        ("LC double one eight eight", "LC-1188"),
        ("LC one double one seven", "LC-1117"),
        ("LC double one double zero", "LC-1100"),
        ("LC triple one two", "LC-1112"),
        ("LC eleven ninety nine", "LC-1199"),
        ("LC eleven sixty three", "LC-1163"),
        ("LC one oh four two", "LC-1042"),
        ("LC ek zero chaar teen", "LC-1043"),
        ("LC ek do chaar teen", "LC-1243"),
        ("LC ek ek saat nau", "LC-1179"),
        ("LC ek hazaar ek sau pachaas", "LC-1150"),
        ("LC one double one five", "LC-1115"),
        ("LC 1042", "LC-1042"),
        ("LC 10 42", "LC-1042"),
        ("LC 10:42", "LC-1042"),
        ("LC ten forty two", "LC-1042"),
        ("LC ten forty-two", "LC-1042"),
    ],
)
def test_other_ids(spoken, expected):
    assert ids(spoken) == [expected], spoken


def test_replaces_in_sentence():
    r = normalize_order_ids("Hi, where is my order el see eleven fifty? It was due yesterday.")
    assert r.text == "Hi, where is my order LC-1150? It was due yesterday."


def test_hinglish_sentence():
    r = normalize_order_ids("Mera order L C one one five zero kahan hai?")
    assert r.text == "Mera order LC-1150 kahan hai?"


def test_two_ids_in_one_utterance():
    r = normalize_order_ids("compare el see eleven fifty and L C one one six one")
    assert r.order_ids == ["LC-1150", "LC-1161"]
    assert r.text == "compare LC-1150 and LC-1161"


def test_id_is_closed_at_four_digits():
    assert normalize_order_ids("LC 1150 to arrive in two days").text == "LC-1150 to arrive in two days"
    assert normalize_order_ids("L C one one five zero for the grinder").text == "LC-1150 for the grinder"
    assert normalize_order_ids("LC 1150 do you have it").text == "LC-1150 do you have it"


def test_short_id_is_suspect_not_snapped():
    r = normalize_order_ids("where is LC one one five")
    assert r.order_ids == []
    assert r.suspect_ids == ["LC-115"]
    assert "LC-115" in r.text


def test_no_prefix_no_id():
    for t in ["eleven fifty grinders", "I want five grinders", "my number is 1150 rupees", "LC is out of stock",
              "I will see eleven fifty", "el is here", "the l c d screen"]:
        assert ids(t) == [], t


def test_bare_order_number():
    assert normalize_order_ids("order 1150 has not come").text == "order LC-1150 has not come"
    assert ids("order number eleven fifty one is late") == ["LC-1151"]
    assert ids("my order id is one one five zero") == ["LC-1150"]


def test_order_quantity_is_not_an_id():
    for t in ["I want to order 1000 grams of beans", "order 2 grinders", "order 1500 rupees worth", "order 12 bags"]:
        assert ids(t) == [], t


def test_bare_answer_only_when_the_agent_asked_for_an_order_id():
    for t in ["double one five zero", "Eleven fifty.", "1150", "one one five zero", "ten oh one"]:
        assert ids(t) == [], t  # nothing asked for an id: left alone
        assert normalize_order_ids(t, expect_order_id=True).order_ids and len(normalize_order_ids(t, True).order_ids) == 1, t
    for t in ["two", "five grinders", "fifty", "eleven fifty rupees"]:
        assert normalize_order_ids(t, expect_order_id=True).order_ids == [], t
    assert normalize_order_ids("Eleven fifty.", True).text == "LC-1150."
    assert normalize_order_ids("Eleven fifty.", False).text == "Eleven fifty."


def test_ambiguous_words_are_never_the_last_digit():
    for t in ["LC 115 to arrive", "LC one one five too", "LC one one five for", "LC 1 1 5 do", "LC one one five to."]:
        r = normalize_order_ids(t)
        assert r.order_ids == [], t
        assert r.suspect_ids == ["LC-115"], t
    assert ids("LC one two to five") == ["LC-1225"]  # between digits it is still read as two
    assert ids("LC one one for zero") == ["LC-1140"]


def test_fifth_digit_makes_the_id_suspect():
    r = normalize_order_ids("where is LC one one five zero five")
    assert r.order_ids == [] and r.suspect_ids == ["LC-11505"]
    assert r.text == "where is LC-11505"
    assert normalize_order_ids("LC 11505 please").suspect_ids == ["LC-11505"]
    assert normalize_order_ids("el see eleven fifty one two").suspect_ids == ["LC-11512"]
    # punctuation ends the id: the next words are a new sentence
    assert normalize_order_ids("LC-1150. Two days ago").order_ids == ["LC-1150"]
    assert normalize_order_ids("LC 1150, 5 days ago").order_ids == ["LC-1150"]


def test_elsie_needs_digits_right_after():
    assert ids("Elsie 1150") == ["LC-1150"]
    assert ids("elsie eleven fifty") == ["LC-1150"]
    for t in ["Elsie, 1150 is her number", "Elsie is here", "Elsie please check eleven fifty", "elsie called about 1150"]:
        assert ids(t) == [], t
    assert ids("el see - 1150") == ["LC-1150"]  # the two-word spoken prefix keeps its separators


def test_never_snaps_to_a_real_order():
    # The normaliser has no list of real orders: what is heard is what is written.
    assert ids("LC one zero zero zero") == ["LC-1000"]
    assert ids("LC nine nine nine nine") == ["LC-9999"]


def test_lowercase_and_odd_spacing():
    assert ids("lc 1150") == ["LC-1150"]
    assert ids("  L   C   one   one   five   zero ") == ["LC-1150"]


def test_devanagari_digits():
    assert ids("LC ११५०") == ["LC-1150"]


def test_match_positions():
    text = "my order LC one one five zero is late"
    (m,) = find_order_ids(text)
    assert text[m.start:m.end] == "LC one one five zero"
    assert m.order_id == "LC-1150" and m.valid


def test_idempotent():
    once = normalize_order_ids("el see eleven fifty").text
    assert normalize_order_ids(once).text == once == "LC-1150"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Um, yes please", "Yes please"),
        ("Uh, where is my order", "Where is my order"),
        ("Arre yaar, my order is late", "My order is late"),
        ("Hmm... no, cancel it", "No, cancel it"),
        ("Matlab I want a return", "I want a return"),
        ("Yes", "Yes"),
        ("Haan, theek hai", "Haan, theek hai"),
        ("Nahi, cancel karo", "Nahi, cancel karo"),
        ("I have a human question", "I have a human question"),
    ],
)
def test_fillers(raw, expected):
    assert strip_fillers(raw) == expected


def test_yes_no_words_survive_fillers():
    for t in ["Yes", "No", "haan", "nahi", "ji", "theek hai", "ok", "confirm", "cancel"]:
        assert strip_fillers(t) == t


def test_prepare_transcript_combines_both():
    r = prepare_transcript("Um, el see eleven fifty kahan hai yaar")
    assert r.text == "LC-1150 kahan hai"
    assert r.order_ids == ["LC-1150"]
    assert prepare_transcript("Um, uh.").text == ""


def test_swallowed_prefix_after_the_word_order():
    # Whisper heard "ids C-1151" for "el see eleven fifty one": the L is gone.
    assert normalize_order_ids("Where is my order ids C-1151?").text == "Where is my order ids LC-1151?"
    assert ids("my order C 1150 is late") == ["LC-1150"]
    assert ids("order L-1150") == ["LC-1150"]
    assert ids("order ids see one one five zero") == []  # "see" is not a prefix fragment


def test_swallowed_prefix_does_not_fire_elsewhere():
    for t in ["Vitamin C 1000 mg", "I need option C 1150 rupees", "order a size L 1150 grams", "grade C 1150",
              "I will order vitamin C 2000"]:
        assert ids(t) == [], t
    assert ids("order 2 grinders, C 1150") == []
