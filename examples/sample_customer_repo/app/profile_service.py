from app.framework import BaseService, CompanyLogger, business_service


@business_service
class ProfileService(BaseService):
    def __init__(self) -> None:
        self.logger = CompanyLogger(__name__)

    def update_profile(self) -> None:
        self.logger.info("Profile updated")
