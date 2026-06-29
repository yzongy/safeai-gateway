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


def test_detector_finds_business_and_lab_domain_identifiers():
    policy = load_policy("strict-ai")
    detector = RedactionDetector(policy)
    text = (
        "客户为华东星火生物科技有限公司，客户编号为CUST-2026-009。"
        "合作单位：南湖合成生物研究中心。"
        "项目代号：GZO-Secret-Vector-2026，样本编号：SAMPLE-20260622-A17。"
    )

    entity_types = {finding.entity_type for finding in detector.detect(text, source_id="domain.md")}

    assert {"ORG", "CUSTOMER", "PROJECT", "SAMPLE_ID"} <= entity_types


def test_generic_org_detector_preserves_action_text_before_org():
    detector = RedactionDetector(load_policy("strict-ai"))
    text = "评估是否需要暂停向南湖合成生物研究中心同步原始序列数据。"

    finding = next(item for item in detector.detect(text, source_id="rd.md") if item.entity_type == "ORG")

    assert finding.value == "南湖合成生物研究中心"
