from safeai.detectors import RedactionDetector
from safeai.policy import load_policy


def test_detector_finds_chinese_pii_money_and_secret_without_raw_in_summary():
    policy = load_policy("strict-ai")
    detector = RedactionDetector(policy)
    text = (
        "张三在涌源合生科技签署合同HT-2026-001，手机号13812345678，"
        "邮箱 founder@example.com，身份证11010519491231002X，金额人民币123456.78元。"
        "token sk-test_1234567890abcdef1234567890abcdef"
    )

    findings = detector.detect(text, source_id="sample.txt")
    entity_types = {finding.entity_type for finding in findings}

    assert {"PERSON", "ORG", "PHONE", "EMAIL", "ID_CARD", "MONEY", "CONTRACT_ID", "API_KEY"} <= entity_types
    assert any(finding.action == "fail" for finding in findings if finding.entity_type == "API_KEY")

    summary = [finding.to_report_dict() for finding in findings]
    rendered = repr(summary)
    assert "张三" not in rendered
    assert "13812345678" not in rendered
    assert "founder@example.com" not in rendered
    assert "sk-test" not in rendered
