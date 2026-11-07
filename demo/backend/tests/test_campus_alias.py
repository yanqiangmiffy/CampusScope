"""The interface shows the campuses as A / B; what a visitor types is mapped back to the notices' names."""
from app.services.qa_service import campus_alias


def test_displayed_campus_names_map_back():
    assert campus_alias("B校区寒假健身房开吗？") == "通州校区寒假健身房开吗？"
    assert campus_alias("我在A校区") == "我在中关村校区"
    assert campus_alias("Is the gym on Campus B open?") == "Is the gym on 通州校区 open?"
    assert campus_alias("今天田径场几点开放？") == "今天田径场几点开放？"
