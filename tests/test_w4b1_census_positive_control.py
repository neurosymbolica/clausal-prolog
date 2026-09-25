"""The census must be SEEN to report a disagreement before any real number
it prints is worth reading.  56 instruments in this project's ledger failed
open; this is how the 57th is prevented."""
from clausal.logic.database import Database
from clausal.logic.predicate import field_names_for
from tests.predicate_api_support import class_arm_predicate


def test_a_planted_disagreement_is_visible_to_the_shadow_read():
    Pt = class_arm_predicate("PlantedDisagreement", ["x", "y"])
    db = Pt._state_row()._db
    # Register DELIBERATELY WRONG fields at the class's own arity.
    db.register_signature("PlantedDisagreement", 2, ("WRONG", "ALSO_WRONG"))
    assert field_names_for(Pt) == ("x", "y")
    assert field_names_for("PlantedDisagreement", arity=2, db=db) == (
        "WRONG", "ALSO_WRONG")
