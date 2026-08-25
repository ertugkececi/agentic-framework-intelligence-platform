from app.enterprise_framework import EnterpriseLog, FrameworkComponent, managed_component


@managed_component
class OrderService(FrameworkComponent):
    def __init__(self) -> None:
        self.log = EnterpriseLog(__name__)

    def create_order(self) -> None:
        self.log.audit("Order created")
