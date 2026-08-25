from app.enterprise_framework import EnterpriseLog, FrameworkComponent, managed_component


@managed_component
class ProfileService(FrameworkComponent):
    def __init__(self) -> None:
        self.log = EnterpriseLog(__name__)

    def update_profile(self) -> None:
        self.log.audit("Profile updated")
