import random

from app.routers.next_move import select_next_problem


def test_random_selection_is_distinct_and_seedable():
    problems = [{"problem_key": "v1:a"}, {"problem_key": "v1:b"}]
    selected = select_next_problem(problems, policy="random", latest={}, rng=random.Random(0))
    assert selected == problems[1]


def test_unattempted_and_problem_key_exclusion():
    problems = [{"problem_key": "v1:a"}, {"problem_key": "v1:b"}]
    assert select_next_problem(problems, policy="unattempted", latest={"v1:a": {}},
                               rng=random.Random(0)) == problems[1]
    assert select_next_problem(problems, policy="random", latest={}, exclude_problem_key="v1:a",
                               rng=random.Random(0)) == problems[1]
    assert select_next_problem([problems[0]], policy="random", latest={},
                               exclude_problem_key="v1:a", rng=random.Random(0)) is None
