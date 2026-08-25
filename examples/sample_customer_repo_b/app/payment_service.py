from app.enterprise_framework import EnterpriseLog, FrameworkComponent, managed_component


@managed_component
class PaymentService(FrameworkComponent):
    def __init__(self) -> None:
        self.log = EnterpriseLog(__name__)

    def pay(self) -> None:
        self.log.audit("Payment received")
