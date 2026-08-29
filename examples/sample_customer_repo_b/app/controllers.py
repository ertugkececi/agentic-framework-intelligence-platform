from app.enterprise_framework import EnterpriseLog, FrameworkComponent, managed_component


@managed_component
class OrderController(FrameworkComponent):
    def __init__(self) -> None:
        self.log = EnterpriseLog(__name__)

    def handle(self) -> None:
        self.log.audit("Order handled")


@managed_component
class PaymentController(FrameworkComponent):
    def __init__(self) -> None:
        self.log = EnterpriseLog(__name__)

    def handle(self) -> None:
        self.log.audit("Payment handled")


@managed_component
class ProfileController(FrameworkComponent):
    def __init__(self) -> None:
        self.log = EnterpriseLog(__name__)

    def handle(self) -> None:
        self.log.audit("Profile handled")