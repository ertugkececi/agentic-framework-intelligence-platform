from app.framework import BaseService, CompanyLogger, business_service


@business_service
class OrderController(BaseService):
    def __init__(self) -> None:
        self.logger = CompanyLogger(__name__)

    def handle(self) -> None:
        self.logger.info("Order handled")


@business_service
class PaymentController(BaseService):
    def __init__(self) -> None:
        self.logger = CompanyLogger(__name__)

    def handle(self) -> None:
        self.logger.info("Payment handled")


@business_service
class ProfileController(BaseService):
    def __init__(self) -> None:
        self.logger = CompanyLogger(__name__)

    def handle(self) -> None:
        self.logger.info("Profile handled")