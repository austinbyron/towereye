from towereye.dice import AUTO, FACES, DieSelection, normalize


def test_normalize_accepts_known_dice_case_insensitively():
    assert normalize("D8") == "d8"
    assert normalize(" d20 ") == "d20"
    assert normalize("auto") == AUTO
    assert normalize("d7") is None
    assert normalize(None) is None
    assert normalize(20) is None


def test_faces_table_covers_the_standard_set():
    assert FACES == {"d4": 4, "d6": 6, "d8": 8, "d10": 10, "d12": 12, "d20": 20}


def test_selection_defaults_to_auto_and_allows_everything():
    sel = DieSelection()
    assert sel.die == AUTO
    assert sel.faces is None
    assert sel.allows(20)


def test_selection_set_validates_and_gates_values():
    sel = DieSelection()
    assert sel.set("d8") is True
    assert sel.die == "d8" and sel.faces == 8
    assert sel.allows(8) and not sel.allows(9)
    assert sel.set("bogus") is False
    assert sel.die == "d8"  # bad input leaves the selection alone
    assert sel.set("AUTO") is True
    assert sel.faces is None
