from goldevidencebench.ui_search import (
    compute_potential,
    construct_greedy_plan,
    delta_phi,
    rebuild_suffix,
    replace_plan_step,
    score_plan_against_gold,
    search_with_simulated_annealing,
    state_matches,
    swap_plan_steps,
)


def test_compute_potential_overlay_and_modal() -> None:
    state = {"overlay_present": False, "modal_scope": "main"}
    assert compute_potential(state) == 2

    state = {"overlay_present": True, "modal_scope": "popup"}
    assert compute_potential(state) == -2


def test_compute_potential_tab_match() -> None:
    state = {"tab": "Billing", "instruction_tab": "Billing"}
    assert compute_potential(state) == 1

    state = {"tab": "Billing", "instruction_tab": "Settings"}
    assert compute_potential(state) == -1


def test_delta_phi() -> None:
    current_state = {"overlay_present": True, "modal_scope": "popup"}
    next_state = {"overlay_present": False, "modal_scope": "main"}
    assert delta_phi(current_state, next_state) == 4


def test_construct_greedy_plan_prefers_delta() -> None:
    candidates_by_step = [
        [
            {"candidate_id": "btn_popup", "overlay_present": True, "modal_scope": "popup"},
            {"candidate_id": "btn_main", "overlay_present": False, "modal_scope": "main"},
        ]
    ]
    plan = construct_greedy_plan(
        candidates_by_step,
        seed=0,
        apply_overlay_filter=False,
        apply_rules=False,
    )
    assert plan == ["btn_main"]


def test_construct_greedy_plan_is_deterministic() -> None:
    candidates_by_step = [
        [
            {"candidate_id": "btn_left", "modal_scope": "main"},
            {"candidate_id": "btn_right", "modal_scope": "main"},
        ]
    ]
    first = construct_greedy_plan(
        candidates_by_step,
        seed=7,
        apply_overlay_filter=False,
        apply_rules=False,
    )
    second = construct_greedy_plan(
        candidates_by_step,
        seed=7,
        apply_overlay_filter=False,
        apply_rules=False,
    )
    assert first == second


def test_construct_greedy_plan_uses_preselector() -> None:
    step = {
        "instruction": "Use the main page button, not the popup.",
        "candidates": [
            {"candidate_id": "btn_main", "modal_scope": None},
            {"candidate_id": "btn_popup", "modal_scope": "popup", "overlay": True},
        ],
    }
    plan = construct_greedy_plan([step], seed=1)
    assert plan == ["btn_main"]


def test_swap_plan_steps() -> None:
    plan = ["a", "b", "c"]
    swapped = swap_plan_steps(plan, 0, 2)
    assert swapped == ["c", "b", "a"]
    assert plan == ["a", "b", "c"]


def test_replace_plan_step() -> None:
    plan = ["a", "b"]
    replaced = replace_plan_step(plan, 1, "c")
    assert replaced == ["a", "c"]


def test_rebuild_suffix_prefers_greedy_choice() -> None:
    candidates_by_step = [
        [{"candidate_id": "keep", "modal_scope": "main"}],
        [
            {"candidate_id": "popup", "overlay_present": True, "modal_scope": "popup"},
            {"candidate_id": "main", "overlay_present": False, "modal_scope": "main"},
        ],
    ]
    plan = ["keep", "popup"]
    rebuilt = rebuild_suffix(
        plan,
        candidates_by_step,
        1,
        seed=0,
        apply_overlay_filter=False,
        apply_rules=False,
    )
    assert rebuilt == ["keep", "main"]


def test_search_with_simulated_annealing_improves_plan() -> None:
    candidates_by_step = [
        [
            {"candidate_id": "bad", "overlay_present": True, "modal_scope": "popup"},
            {"candidate_id": "good", "overlay_present": False, "modal_scope": "main"},
        ]
    ]
    initial_plan = ["bad"]

    def compute_score(plan: list[str | None]) -> float:
        return 1.0 if plan and plan[0] == "good" else 0.0

    best_plan, best_score = search_with_simulated_annealing(
        initial_plan,
        candidates_by_step,
        compute_score,
        iterations=1,
        temp_start=1.0,
        temp_end=1.0,
        seed=0,
        apply_overlay_filter=False,
        apply_rules=False,
    )
    assert best_plan == ["good"]
    assert best_score == 1.0


def test_search_with_simulated_annealing_returns_telemetry() -> None:
    candidates_by_step = [[{"candidate_id": "bad"}, {"candidate_id": "good"}]]
    initial_plan = ["bad"]

    def compute_score(plan: list[str | None]) -> float:
        return 1.0 if plan and plan[0] == "good" else 0.0

    best_plan, best_score, telemetry = search_with_simulated_annealing(
        initial_plan,
        candidates_by_step,
        compute_score,
        iterations=2,
        temp_start=1.0,
        temp_end=1.0,
        seed=0,
        apply_overlay_filter=False,
        apply_rules=False,
        return_telemetry=True,
    )
    assert best_plan == ["good"]
    assert best_score == 1.0
    assert telemetry["iterations"] == 2
    assert telemetry["proposed_moves"] == 2
    assert telemetry["accepted_moves"] >= 0
    assert "move_stats" in telemetry
    assert set(telemetry["move_stats"].keys()) == {"swap", "replace", "rebuild"}


def test_search_with_simulated_annealing_respects_validity() -> None:
    candidates_by_step = [[{"candidate_id": "bad"}, {"candidate_id": "good"}]]
    initial_plan = ["bad"]

    def compute_score(plan: list[str | None]) -> float:
        return 1.0 if plan and plan[0] == "bad" else 0.0

    def is_valid_plan(plan: list[str | None]) -> bool:
        return bool(plan and plan[0] == "good")

    best_plan, best_score = search_with_simulated_annealing(
        initial_plan,
        candidates_by_step,
        compute_score,
        is_valid_plan=is_valid_plan,
        iterations=1,
        temp_start=1.0,
        temp_end=1.0,
        seed=0,
        apply_overlay_filter=False,
        apply_rules=False,
    )
    assert best_plan == ["good"]
    assert best_score == 0.0


def test_score_plan_against_gold_flags_wrong_action() -> None:
    candidates_by_step = [
        {
            "candidates": [
                {"candidate_id": "bad", "modal_scope": "main"},
                {"candidate_id": "good", "modal_scope": "main"},
            ],
            "gold": {"candidate_id": "good"},
        }
    ]
    score, wrong_action = score_plan_against_gold(
        candidates_by_step,
        ["bad"],
        fatal_wrong=True,
        apply_overlay_filter=False,
        apply_rules=False,
    )
    assert wrong_action is True
    assert score <= -1e8


def test_score_plan_against_gold_rewards_delta() -> None:
    candidates_by_step = [
        {
            "candidates": [
                {"candidate_id": "popup", "overlay_present": True, "modal_scope": "popup"},
                {"candidate_id": "main", "overlay_present": False, "modal_scope": "main"},
            ],
            "gold": {"candidate_id": "main"},
        }
    ]
    score, wrong_action = score_plan_against_gold(
        candidates_by_step,
        ["main"],
        alpha=1.0,
        fatal_wrong=False,
        apply_overlay_filter=False,
        apply_rules=False,
    )
    assert wrong_action is False
    assert score > 0.0


def test_score_plan_against_gold_requires_state_gate() -> None:
    candidates_by_step = [
        {
            "candidates": [
                {"candidate_id": "tab_a", "modal_scope": "main", "next_state": {"panel": "a"}},
                {"candidate_id": "tab_b", "modal_scope": "main", "next_state": {"panel": "b"}},
            ],
            "gold": {"candidate_id": "tab_a"},
        },
        {
            "requires_state": {"panel": "a"},
            "candidates": [
                {"candidate_id": "btn_continue", "modal_scope": "main"},
            ],
            "gold": {"candidate_id": "btn_continue"},
        },
    ]
    score, wrong_action = score_plan_against_gold(
        candidates_by_step,
        ["tab_b", "btn_continue"],
        fatal_wrong=False,
        require_state_gate=True,
        apply_overlay_filter=False,
        apply_rules=False,
    )
    assert wrong_action is True
    assert score < 0.0


def test_state_matches() -> None:
    assert state_matches({"panel": "a"}, {"panel": "a", "other": 1}) is True
    assert state_matches({"panel": "b"}, {"panel": "a"}) is False
