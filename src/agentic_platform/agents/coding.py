from pathlib import Path
from agentic_platform.security.policy import Capability

def implement_service(repository,service_name,context,model,grant):
 grant.require(Capability.WRITE_REPOSITORY); app=repository/'app'; tests=repository/'tests'; app.mkdir(exist_ok=True); tests.mkdir(exist_ok=True)
 (app/'customer_account_service.py').write_text(model.generate_service(service_name,context))
 (tests/'test_customer_account_service.py').write_text("from app.customer_account_service import CustomerAccountService\n\ndef test_generated_service():\n    assert CustomerAccountService().get_account('A')['account_id'] == 'A'\n")
 return ['app/customer_account_service.py']
