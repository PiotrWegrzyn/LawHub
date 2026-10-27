"""Run with: pip install -r requirements.txt pytest && python -m pytest (from this directory)."""

import base64
import json
from types import SimpleNamespace
from unittest import mock

import main


def budget_event(cost, budget):
    payload = base64.b64encode(json.dumps({"costAmount": cost, "budgetAmount": budget}).encode())
    return SimpleNamespace(data={"message": {"data": payload}})


@mock.patch.object(main.billing_v1, "CloudBillingClient")
def test_below_budget_does_nothing(client_cls):
    main.stop_billing(budget_event(1.2, 5))
    client_cls.assert_not_called()


@mock.patch.object(main.billing_v1, "CloudBillingClient")
def test_at_budget_unlinks_billing(client_cls):
    client = client_cls.return_value
    client.get_project_billing_info.return_value.billing_enabled = True
    main.stop_billing(budget_event(5.01, 5))
    kwargs = client.update_project_billing_info.call_args.kwargs
    assert kwargs["project_billing_info"].billing_account_name == ""


@mock.patch.object(main.billing_v1, "CloudBillingClient")
def test_already_disabled_is_left_alone(client_cls):
    client = client_cls.return_value
    client.get_project_billing_info.return_value.billing_enabled = False
    main.stop_billing(budget_event(9, 5))
    client.update_project_billing_info.assert_not_called()
