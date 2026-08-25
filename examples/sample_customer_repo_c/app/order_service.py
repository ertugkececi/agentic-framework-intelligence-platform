from app.core import BusinessUnit, component, AuditSink, SharedCache
from app.support import OrderStorage, OrderConverter
@component
class OrderService(BusinessUnit):
 def __init__(self): self.audit=AuditSink(__name__); self.cache=SharedCache(); self.storage=OrderStorage(); self.converter=OrderConverter()
 def work(self): self.audit.record('x'); self.storage.save(self.converter.convert({}))
