"""Unlink billing from the project once the budget is used up.

Triggered by budget notifications on Pub/Sub. Google publishes several
notifications a day; we act only when actual cost reaches the budget.
"""

import base64
import json
import os

import functions_framework
from google.cloud import billing_v1

PROJECT_NAME = f"projects/{os.environ.get('PROJECT_ID', '')}"


def over_budget(notification: dict) -> bool:
    return notification["costAmount"] >= notification["budgetAmount"]


@functions_framework.cloud_event
def stop_billing(cloud_event):
    notification = json.loads(base64.b64decode(cloud_event.data["message"]["data"]))
    cost, budget = notification["costAmount"], notification["budgetAmount"]
    if not over_budget(notification):
        print(f"Cost {cost} is below budget {budget}; nothing to do.")
        return

    client = billing_v1.CloudBillingClient()
    if not client.get_project_billing_info(name=PROJECT_NAME).billing_enabled:
        print("Billing already disabled.")
        return
    client.update_project_billing_info(
        name=PROJECT_NAME,
        project_billing_info=billing_v1.ProjectBillingInfo(billing_account_name=""),
    )
    print(f"Cost {cost} reached budget {budget}: billing unlinked from {PROJECT_NAME}.")
