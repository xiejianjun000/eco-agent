"""渠道出站扩展能力测试（gateway/platforms bot 能力并入 r15 适配器）。

全部 mock http_post_json / http_get_json，禁止真实外呼。覆盖：
- 飞书 send_card 卡片结构（审批回调 value）与 tenant_access_token 缓存复用
- 企微 send_text_card / send_news / create_approval payload 与 token 缓存复用
- 钉钉 send_text（单聊）/ send_group_message（群）区别、send_card、
  query_approval 与双 token 缓存复用
"""

import json
from unittest import mock

from agent_core.channels import get_channel

FEISHU_CFG = {"app_id": "cli_test", "app_secret": "fs-secret"}
WECOM_CFG = {"corp_id": "ww_test", "secret": "wc-secret", "agent_id": "1000002"}
DINGTALK_CFG = {"app_key": "ding_key", "app_secret": "ding_secret", "robot_code": "robot_1"}


# ---------------- 飞书 ----------------


def test_feishu_send_card_structure():
    ch = get_channel("feishu", FEISHU_CFG)
    calls = []

    def fake_post(url, payload, headers=None, timeout=10):
        calls.append((url, payload, headers))
        if "tenant_access_token" in url:
            return {"code": 0, "tenant_access_token": "tat-1", "expire": 7200}
        return {"code": 0}

    with mock.patch("agent_core.channels.feishu.http_post_json", side_effect=fake_post):
        ok = ch.send_card(
            "ou_user1", "执法风险操作审批", "详情内容", approve_callback="cb-approve-1", reject_callback="cb-reject-1"
        )
    assert ok is True
    url, payload, headers = calls[-1]
    assert "receive_id_type=open_id" in url
    assert headers["Authorization"] == "Bearer tat-1"
    assert payload["msg_type"] == "interactive"
    assert payload["receive_id"] == "ou_user1"
    card = json.loads(payload["content"])
    assert card["header"]["title"]["content"] == "执法风险操作审批"
    assert card["header"]["template"] == "red"  # 标题含"审批"
    action = card["elements"][-1]
    assert action["tag"] == "action"
    approve, reject = action["actions"]
    assert approve["value"] == {"action": "approve", "callback": "cb-approve-1"}
    assert reject["value"] == {"action": "reject", "callback": "cb-reject-1"}


def test_feishu_send_card_no_callbacks_no_actions():
    ch = get_channel("feishu", {**FEISHU_CFG, "tenant_access_token": "tat-x"})
    with mock.patch("agent_core.channels.feishu.http_post_json", return_value={"code": 0}) as p:
        assert ch.send_card("ou_1", "普通通知", "内容") is True
    card = json.loads(p.call_args[0][1]["content"])
    assert card["header"]["template"] == "blue"  # 标题不含"审批"
    assert all(e["tag"] != "action" for e in card["elements"])


def test_feishu_send_card_token_failure_returns_false():
    ch = get_channel("feishu", FEISHU_CFG)
    with mock.patch("agent_core.channels.feishu.http_post_json", return_value={"code": 999}) as p:
        assert ch.send_card("ou_1", "t", "c") is False
        assert p.call_count == 1  # 只取 token，未发消息


def test_feishu_tenant_token_cache_reused():
    ch = get_channel("feishu", FEISHU_CFG)
    with mock.patch(
        "agent_core.channels.feishu.http_post_json", return_value={"code": 0, "tenant_access_token": "tat-c", "expire": 7200}
    ) as p:
        assert ch.get_tenant_access_token() == "tat-c"
        assert ch.get_tenant_access_token() == "tat-c"
        assert p.call_count == 1  # 第二次命中缓存


# ---------------- 企业微信 ----------------


def _wecom_mocks(token_resp=None, send_resp=None):
    token_resp = token_resp or {"errcode": 0, "access_token": "wct-1", "expires_in": 7200}
    send_resp = send_resp or {"errcode": 0}
    return (
        mock.patch("agent_core.channels.wecom.WeComChannel._get_token", return_value=token_resp),
        mock.patch("agent_core.channels.wecom.http_post_json", return_value=send_resp),
    )


def test_wecom_send_text_card():
    ch = get_channel("wecom", WECOM_CFG)
    tok, post = _wecom_mocks()
    with tok, post as p:
        assert ch.send_text_card("zhangsan", "标题", "描述", url="https://example.test/detail") is True
    url, payload = p.call_args[0][:2]
    assert "access_token=wct-1" in url
    assert payload["msgtype"] == "textcard"
    assert payload["agentid"] == 1000002
    card = payload["textcard"]
    assert card["title"] == "标题" and card["description"] == "描述"
    assert card["url"] == "https://example.test/detail"


def test_wecom_send_news():
    ch = get_channel("wecom", WECOM_CFG)
    articles = [{"title": "头条", "url": "https://example.test/a"}]
    tok, post = _wecom_mocks()
    with tok, post as p:
        assert ch.send_news("zhangsan", articles) is True
    payload = p.call_args[0][1]
    assert payload["msgtype"] == "news"
    assert payload["news"]["articles"] == articles


def test_wecom_create_approval_payload():
    ch = get_channel("wecom", WECOM_CFG)
    tok, post = _wecom_mocks(send_resp={"errcode": 0, "sp_no": "202401010001"})
    with tok, post as p:
        sp_no = ch.create_approval("creator1", ["approver1", "approver2"], "Tpl-001", {"contents": []})
    assert sp_no == "202401010001"
    url, payload = p.call_args[0][:2]
    assert "/cgi-bin/oa/applyevent" in url
    assert "access_token=wct-1" in url
    assert payload["creator_userid"] == "creator1"
    assert payload["template_id"] == "Tpl-001"
    assert payload["use_template_approver"] == 0
    assert payload["approver"] == [{"attr": 0, "userid": ["approver1", "approver2"]}]
    assert payload["apply_data"] == {"contents": []}


def test_wecom_create_approval_failure_returns_none():
    ch = get_channel("wecom", WECOM_CFG)
    tok, post = _wecom_mocks(send_resp={"errcode": 60011})
    with tok, post:
        assert ch.create_approval("c", ["a"], "T", {}) is None


def test_wecom_token_cache_reused_across_sends():
    ch = get_channel("wecom", WECOM_CFG)
    tok, post = _wecom_mocks()
    with tok as t, post:
        assert ch.send_text_card("u1", "t", "d") is True
        assert ch.send_news("u1", []) is True
        assert t.call_count == 1  # 第二次发送命中 token 缓存


# ---------------- 钉钉 ----------------


def _dingtalk_post_factory(calls):
    def fake_post(url, payload, headers=None, timeout=10):
        calls.append((url, payload, headers))
        if "oauth2/accessToken" in url:
            return {"accessToken": "rt-1", "expireIn": 7200}
        return {}

    return fake_post


def test_dingtalk_single_vs_group_message():
    ch = get_channel("dingtalk", DINGTALK_CFG)
    calls = []
    with mock.patch("agent_core.channels.dingtalk.http_post_json", side_effect=_dingtalk_post_factory(calls)):
        assert ch.send_text("user-1", "单聊内容") is True
        assert ch.send_group_message("cid-group-1", "群内容") is True

    single = next(c for c in calls if "oToMessages" in c[0])
    group = next(c for c in calls if "groupMessages" in c[0])
    # 单聊：oToMessages/batchSend + userIds
    assert single[1]["userIds"] == ["user-1"]
    assert "openConversationId" not in single[1]
    # 群：groupMessages/send + openConversationId
    assert group[1]["openConversationId"] == "cid-group-1"
    assert "userIds" not in group[1]
    # 两者都带 robotCode、sampleText、鉴权头
    for _url, payload, headers in (single, group):
        assert payload["robotCode"] == "robot_1"
        assert payload["msgKey"] == "sampleText"
        assert headers["x-acs-dingtalk-access-token"] == "rt-1"
    assert json.loads(group[1]["msgParam"]) == {"content": "群内容"}


def test_dingtalk_robot_token_cache_reused():
    ch = get_channel("dingtalk", DINGTALK_CFG)
    calls = []
    with mock.patch("agent_core.channels.dingtalk.http_post_json", side_effect=_dingtalk_post_factory(calls)):
        ch.send_text("u1", "a")
        ch.send_text("u2", "b")
    token_calls = [c for c in calls if "oauth2/accessToken" in c[0]]
    assert len(token_calls) == 1  # 第二次发送命中机器人 token 缓存
    assert token_calls[0][1] == {"appKey": "ding_key", "appSecret": "ding_secret"}


def test_dingtalk_send_card():
    ch = get_channel("dingtalk", DINGTALK_CFG)
    calls = []
    with mock.patch("agent_core.channels.dingtalk.http_post_json", side_effect=_dingtalk_post_factory(calls)):
        assert ch.send_card("user-1", "审批卡片", "卡片内容") is True
    url, payload, _headers = calls[-1]
    assert "oToMessages/batchSend" in url
    assert payload["msgKey"] == "sampleActionCard"
    card = json.loads(payload["msgParam"])
    assert card["header"]["title"]["content"] == "审批卡片"
    assert card["body"]["content"] == "卡片内容"


def test_dingtalk_query_approval_uses_oapi_token():
    ch = get_channel("dingtalk", DINGTALK_CFG)
    calls = []
    with (
        mock.patch(
            "agent_core.channels.dingtalk.http_get_json",
            return_value={"errcode": 0, "access_token": "oat-1", "expires_in": 7200},
        ) as g,
        mock.patch(
            "agent_core.channels.dingtalk.http_post_json",
            side_effect=lambda url, payload, headers=None, timeout=10: (
                calls.append((url, payload)) or {"errcode": 0, "process_instance": {"id": "pi-1", "status": "RUNNING"}}
            ),
        ),
    ):
        result = ch.query_approval("pi-1")
    assert result == {"id": "pi-1", "status": "RUNNING"}
    assert "appkey=ding_key" in g.call_args[0][0]
    url, payload = calls[0]
    assert "/topapi/processinstance/get" in url
    assert "access_token=oat-1" in url
    assert payload == {"process_instance_id": "pi-1"}


def test_dingtalk_app_token_cache_reused():
    ch = get_channel("dingtalk", DINGTALK_CFG)
    with mock.patch(
        "agent_core.channels.dingtalk.http_get_json", return_value={"errcode": 0, "access_token": "oat-c", "expires_in": 7200}
    ) as g:
        assert ch.get_app_token() == "oat-c"
        assert ch.get_app_token() == "oat-c"
        assert g.call_count == 1


def test_dingtalk_no_credentials_returns_empty_token():
    ch = get_channel("dingtalk", {})
    assert ch.get_app_token() == ""
    assert ch.get_robot_token() == ""
    assert ch.send_group_message("g", "t") is False  # 无 token 直接失败
    assert ch.query_approval("pi") is None
