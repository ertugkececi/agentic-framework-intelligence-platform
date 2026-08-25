from app.enterprise_framework import EnterpriseLog, FrameworkComponent, managed_component
from app.repositories import ProfileRepository
from app.mapping import ProfileMapper
from app.clients import NotificationClient


@managed_component
class ProfileService(FrameworkComponent):
    def __init__(self) -> None:
        self.log = EnterpriseLog(__name__)
        self.repository = ProfileRepository()
        self.mapper = ProfileMapper()
        self.notification_client = NotificationClient()

    def update_profile(self) -> None:
        profile = self.mapper.map({})
        self.repository.save(profile)
        self.notification_client.notify(profile)
        self.log.audit("Profile updated")
