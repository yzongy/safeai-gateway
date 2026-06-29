from safeai.policy import load_policy


def test_default_policy_actions_are_strict_for_secrets_and_tokenize_names():
    policy = load_policy("strict-ai")

    assert policy.action_for("API_KEY") == "fail"
    assert policy.action_for("PRIVATE_KEY") == "fail"
    assert policy.action_for("PERSON") == "tokenize"
    assert policy.action_for("EMAIL") == "mask"
