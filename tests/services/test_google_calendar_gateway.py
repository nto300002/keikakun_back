from datetime import datetime, timedelta

import pytest

from app.services.google_calendar_client import GoogleCalendarAuthenticationError
from app.services.calendar.google_calendar_gateway import GoogleCalendarGateway


class FakeGoogleCalendarClient:
    instances = []

    def __init__(self, service_account_json: str):
        self.service_account_json = service_account_json
        self.authenticated = False
        self.created_events = []
        self.deleted_events = []
        FakeGoogleCalendarClient.instances.append(self)

    def authenticate(self) -> None:
        self.authenticated = True

    def create_event(self, **kwargs) -> str:
        self.created_events.append(kwargs)
        return "google-event-id-123"

    def delete_event(self, **kwargs) -> None:
        self.deleted_events.append(kwargs)


class FailingAuthGoogleCalendarClient(FakeGoogleCalendarClient):
    def authenticate(self) -> None:
        raise GoogleCalendarAuthenticationError("invalid credentials")


@pytest.fixture(autouse=True)
def reset_fake_client_instances():
    FakeGoogleCalendarClient.instances = []


class TestGoogleCalendarGateway:
    def test_build_authenticated_client_authenticates_and_returns_client(self):
        gateway = GoogleCalendarGateway(client_class=FakeGoogleCalendarClient)

        client = gateway.build_authenticated_client("service-account-json")

        assert isinstance(client, FakeGoogleCalendarClient)
        assert client.service_account_json == "service-account-json"
        assert client.authenticated is True

    def test_build_authenticated_client_propagates_authentication_error(self):
        gateway = GoogleCalendarGateway(client_class=FailingAuthGoogleCalendarClient)

        with pytest.raises(GoogleCalendarAuthenticationError) as exc_info:
            gateway.build_authenticated_client("bad-json")

        assert "invalid credentials" in str(exc_info.value)

    def test_create_event_authenticates_and_delegates_to_client(self):
        gateway = GoogleCalendarGateway(client_class=FakeGoogleCalendarClient)
        start_datetime = datetime.now()
        end_datetime = start_datetime + timedelta(hours=1)

        event_id = gateway.create_event(
            service_account_json="service-account-json",
            calendar_id="calendar@example.com",
            title="title",
            description="description",
            start_datetime=start_datetime,
            end_datetime=end_datetime,
        )

        client = FakeGoogleCalendarClient.instances[0]
        assert client.authenticated is True
        assert event_id == "google-event-id-123"
        assert client.created_events == [
            {
                "calendar_id": "calendar@example.com",
                "title": "title",
                "description": "description",
                "start_datetime": start_datetime,
                "end_datetime": end_datetime,
            }
        ]

    def test_delete_event_authenticates_and_delegates_to_client(self):
        gateway = GoogleCalendarGateway(client_class=FakeGoogleCalendarClient)

        gateway.delete_event(
            service_account_json="service-account-json",
            calendar_id="calendar@example.com",
            event_id="event-id",
        )

        client = FakeGoogleCalendarClient.instances[0]
        assert client.authenticated is True
        assert client.deleted_events == [
            {
                "calendar_id": "calendar@example.com",
                "event_id": "event-id",
            }
        ]
