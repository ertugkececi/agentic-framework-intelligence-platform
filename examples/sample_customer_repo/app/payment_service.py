from app.framework import BaseService, CompanyLogger, business_service


@business_service
class PaymentService(BaseService):
    def __init__(self) -> None:
        self.logger = CompanyLogger(__name__)

    def pay(self) -> None:
        self.logger.info("Payment received")
