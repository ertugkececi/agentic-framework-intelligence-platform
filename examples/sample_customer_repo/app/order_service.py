from app.framework import BaseService, CompanyLogger, business_service


@business_service
class OrderService(BaseService):
    def __init__(self) -> None:
        self.logger = CompanyLogger(__name__)

    def create_order(self) -> None:
        self.logger.info("Order created")
