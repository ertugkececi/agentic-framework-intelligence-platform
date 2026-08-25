from app.enterprise_framework import EnterpriseLog, FrameworkComponent, managed_component
from app.repositories import OrderRepository
from app.mapping import OrderMapper
from app.clients import PaymentClient


@managed_component
class OrderService(FrameworkComponent):
    def __init__(self) -> None:
        self.log = EnterpriseLog(__name__)
        self.repository = OrderRepository()
        self.mapper = OrderMapper()
        self.payment_client = PaymentClient()

    def create_order(self) -> None:
        order = self.mapper.map({})
        self.repository.save(order)
        self.payment_client.notify(order)
        self.log.audit("Order created")
