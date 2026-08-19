"""Unit tests for the still-empty modules: banking, notification, analytics.

Üçünün de tek endpoint'i var (health check); models/schemas/service.py
dosyaları 0 satır olduğu için test edilecek başka bir şey yok.
"""

from __future__ import annotations

import pytest


@pytest.mark.parametrize("module_name", ["banking", "notification", "analytics"])
def test_stub_module_health_endpoint_reports_its_own_name(client, module_name):
    response = client.get(f"/api/{module_name}/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "module": module_name}
