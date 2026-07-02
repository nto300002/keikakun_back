"""Google Calendar external API boundary."""

import inspect
from datetime import datetime
from typing import Type

from app.services.google_calendar_client import GoogleCalendarClient


class GoogleCalendarGateway:
    """Creates authenticated Google Calendar clients and delegates API calls."""

    def __init__(self, client_class: Type[GoogleCalendarClient] = GoogleCalendarClient):
        self.client_class = client_class

    def build_authenticated_client(self, service_account_json: str) -> GoogleCalendarClient:
        client = self.client_class(service_account_json)
        client.authenticate()
        return client

    def create_event(
        self,
        *,
        service_account_json: str,
        calendar_id: str,
        title: str,
        description: str,
        start_datetime: datetime,
        end_datetime: datetime,
    ) -> str:
        client = self.build_authenticated_client(service_account_json)
        return client.create_event(
            calendar_id=calendar_id,
            title=title,
            description=description,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
        )

    def delete_event(
        self,
        *,
        service_account_json: str,
        calendar_id: str,
        event_id: str,
    ) -> None:
        client = self.build_authenticated_client(service_account_json)
        result = client.delete_event(
            calendar_id=calendar_id,
            event_id=event_id,
        )
        if inspect.isawaitable(result):
            result.close()
