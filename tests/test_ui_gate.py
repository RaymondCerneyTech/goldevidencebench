from goldevidencebench.ui_gate import (
    GateModel,
    extract_gate_features,
    gate_feature_names,
    select_candidate,
    train_logistic_regression,
    build_feature_vector,
)


def test_extract_gate_features_commit_apply() -> None:
    row = {"instruction": "Commit the changes."}
    candidate = {"candidate_id": "btn_apply", "label": "Apply", "role": "button"}
    features = extract_gate_features(row, candidate)
    assert features["instr_has_commit"] == 1.0
    assert features["label_has_apply"] == 1.0
    assert features["label_match_any"] == 1.0


def test_train_gate_model_prefers_apply() -> None:
    rows = [
        {
            "instruction": "Commit the changes.",
            "candidates": [
                {"candidate_id": "btn_ok", "label": "OK", "role": "button"},
                {"candidate_id": "btn_apply", "label": "Apply", "role": "button"},
            ],
            "gold": {"candidate_id": "btn_apply"},
        },
        {
            "instruction": "Finalize the update.",
            "candidates": [
                {"candidate_id": "btn_ok_b", "label": "OK", "role": "button"},
                {"candidate_id": "btn_apply_b", "label": "Apply", "role": "button"},
            ],
            "gold": {"candidate_id": "btn_apply_b"},
        },
    ]
    feature_names = gate_feature_names()
    x_rows = []
    y_rows = []
    for row in rows:
        gold_id = row["gold"]["candidate_id"]
        for candidate in row["candidates"]:
            x_rows.append(build_feature_vector(row, candidate, feature_names))
            y_rows.append(1 if candidate["candidate_id"] == gold_id else 0)

    weights, bias = train_logistic_regression(x_rows, y_rows, lr=0.2, epochs=300)
    model = GateModel(feature_names=feature_names, weights=weights, bias=bias)
    selected = select_candidate(rows[0], rows[0]["candidates"], model)
    assert selected == "btn_apply"


def test_extract_gate_features_toolbar_menu() -> None:
    row = {"instruction": "Use the toolbar action."}
    toolbar = {
        "candidate_id": "btn_toolbar",
        "label": "Refresh",
        "role": "button",
        "app_path": "Toolbar > Actions",
        "next_state": {"location": "toolbar"},
    }
    menu = {
        "candidate_id": "btn_menu",
        "label": "Refresh",
        "role": "menuitem",
        "app_path": "Menu Bar > Actions",
        "next_state": {"location": "menu"},
    }
    toolbar_features = extract_gate_features(row, toolbar)
    menu_features = extract_gate_features(row, menu)
    assert toolbar_features["instr_toolbar_role_match"] == 1.0
    assert toolbar_features["instr_menu_role_match"] == 0.0
    assert toolbar_features["app_path_match_any"] == 1.0
    assert toolbar_features["next_location_toolbar"] == 1.0
    assert toolbar_features["next_location_menu"] == 0.0
    assert menu_features["instr_toolbar_role_match"] == 0.0
    assert menu_features["instr_menu_role_match"] == 0.0
    assert menu_features["next_location_toolbar"] == 0.0
    assert menu_features["next_location_menu"] == 1.0
