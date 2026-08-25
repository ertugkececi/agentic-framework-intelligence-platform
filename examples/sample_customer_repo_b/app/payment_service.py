from app.enterprise_framework import EnterpriseLog, FrameworkComponent, managed_component
from app.repositories import PaymentRepository
from app.mapping import PaymentMapper


@managed_component
class PaymentService(FrameworkComponent):
    def __init__(self) -> None:
        self.log = EnterpriseLog(__name__)
        self.repository = PaymentRepository()
        self.mapper = PaymentMapper()

    def pay(self) -> None:
        payment = self.mapper.map({})
        self.repository.save(payment)
        self.log.audit("Payment received")
