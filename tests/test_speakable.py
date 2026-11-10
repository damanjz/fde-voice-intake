from app.speakable import make_speakable, spell


def test_spell():
    assert spell("LC1150") == "L C one one five zero"


def test_citations_dropped():
    assert make_speakable("Returns take 30 days [KB-007].") == "Returns take 30 days."
    assert make_speakable("Returns take 30 days [KB-007, KB-012].") == "Returns take 30 days."
    assert make_speakable("Returns take 30 days (KB-007).") == "Returns take 30 days."
    assert "KB-" not in make_speakable("See KB-007 for more.")


def test_order_ids_spelled():
    out = make_speakable("Your order LC-1150 has shipped.")
    assert out == "Your order L C one one five zero has shipped."


def test_tickets_and_skus_spelled():
    assert "T one zero zero seven" in make_speakable("Ticket T-1007 is open.")
    assert "G R zero zero one" in make_speakable("The GR-001 is in stock.")


def test_rupees():
    assert make_speakable("The fee is INR 99.") == "The fee is 99 rupees."
    assert make_speakable("It costs Rs. 1,299.") == "It costs 1299 rupees."
    assert make_speakable("Total ₹2,499 only") == "Total 2499 rupees only"
    assert make_speakable("Refund INR 1,299.50 today") == "Refund 1299 rupees 50 paise today"
    assert make_speakable("You pay 99 INR") == "You pay 99 rupees"
    assert "INR" not in make_speakable("amount in INR")


def test_markdown_removed():
    out = make_speakable("## Status\n**Shipped** via `BlueDart`. See [the page](https://x.example/a).")
    assert "*" not in out and "`" not in out and "#" not in out and "http" not in out
    assert "Shipped" in out and "the page" in out


def test_short_list_kept():
    out = make_speakable("Options:\n- Grinder A\n- Grinder B\n- Grinder C")
    assert "Grinder A; Grinder B; Grinder C." in out
    assert "more" not in out


def test_long_list_shortened():
    items = "\n".join(f"- Product {i}" for i in range(1, 9))
    out = make_speakable("We have:\n" + items)
    assert "Product 3" in out and "Product 4" not in out
    assert "5 more" in out and "on screen" in out


def test_numbered_list():
    assert make_speakable("1. First\n2. Second") == "First; Second."


def test_dates_and_times():
    assert make_speakable("Delivered on 2026-11-05.") == "Delivered on 5 November 2026."
    assert make_speakable("Support hours are 9:00-19:00 IST, Mon-Sat.") == (
        "Support hours are 9 AM to 7 PM I S T, Monday to Saturday."
    )
    assert make_speakable("Call at 14:30") == "Call at 2 30 PM"


def test_email_and_phone():
    assert make_speakable("Write to help@larkfield.example") == "Write to help at larkfield dot example"
    assert "nine eight" in make_speakable("Call +91 98765 43210")


def test_tracking_number():
    assert make_speakable("Tracking BD123456789").startswith("Tracking B D one two three")


def test_abbreviations_and_symbols():
    assert make_speakable("20% off & free") == "20 percent off and free"
    assert make_speakable("Pay by UPI or COD") == "Pay by U P I or C O D"


def test_many_sentences_capped_but_confirm_kept():
    text = " ".join(f"Sentence {i} here." for i in range(1, 10)) + " Please confirm to go ahead, or cancel."
    out = make_speakable(text)
    assert "Sentence 5 here." in out and "Sentence 6 here." not in out
    assert "The rest is on your screen." in out
    assert out.endswith("Please confirm to go ahead, or cancel.")


def test_short_text_untouched():
    assert make_speakable("Hello there.") == "Hello there."


def test_empty():
    assert make_speakable("") == ""


def test_rs_inside_a_word_is_not_money():
    assert make_speakable("In the wars 2026 was loud") == "In the wars 2026 was loud"


def test_speak_pending_return_from_the_action_itself():
    from app.speakable import speak_pending

    pending = {"tool": "start_return", "args": {"order_id": "LC-1144", "skus": ["KT-002"], "reason": "kettle does not heat"}}
    text = "I can start a return ... Estimated refund: INR 2,499 (after the INR 99 reverse pickup fee). Please confirm."
    out = speak_pending(pending, text)
    assert out == ("I can start a return for order L C one one four four, items K T zero zero two, reason: kettle does "
                   "not heat, estimated refund 2499 rupees. Say yes or no, or press Confirm or Cancel.")


def test_speak_pending_is_never_truncated():
    from app.speakable import speak_pending

    long_reason = " ".join(f"word{i}" for i in range(80))
    out = speak_pending({"tool": "start_return", "args": {"order_id": "LC-1150", "skus": ["GR-001", "BR-002", "BR-003", "BR-004", "BR-005"],
                                                          "reason": long_reason}}, "")
    assert "word79" in out and "on your screen" not in out and "more, which" not in out
    assert out.endswith("Say yes or no, or press Confirm or Cancel.")
    for sku in ("G R zero zero one", "B R zero zero five"):
        assert sku in out


def test_speak_pending_ticket_and_unknown():
    from app.speakable import speak_pending

    out = speak_pending({"tool": "create_ticket", "args": {"priority": "high", "summary": "Invoice has the wrong address."}}, "x")
    assert out == "I can open a high priority support ticket: Invoice has the wrong address. Say yes or no, or press Confirm or Cancel."
    many = " ".join(f"Sentence {i}." for i in range(1, 12))
    out = speak_pending({"tool": "something_new", "args": {}}, many)
    assert "Sentence 11." in out and out.endswith("Cancel.")
