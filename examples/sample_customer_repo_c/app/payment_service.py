from app.core import BusinessUnit, component, AuditSink, SharedCache
from app.support import PaymentStorage, PaymentConverter
@component
class PaymentService(BusinessUnit):
 def __init__(self): self.audit=AuditSink(__name__); self.cache=SharedCache(); self.storage=PaymentStorage(); self.converter=PaymentConverter()
 def work(self): self.audit.record('x'); self.storage.save(self.converter.convert({}))
