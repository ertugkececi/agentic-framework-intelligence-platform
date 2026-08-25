# Agentic Framework Intelligence Platform

On-premise kurulabilir **Framework Intelligence + LangGraph** development platform PoC’u.

> **Kanıtlanmış PoC iddiası:** Platform customer framework’ünü runtime’da AST analiziyle öğrenir ve generator customer-specific framework isimlerini önceden bilmeden, yalnızca retrieve edilen structured `CodingContext` üzerinden framework-aware kod üretir.

LangGraph yalnızca workflow orchestration’dır. Framework bilgisinin kaynak gerçeği; evidence, confidence, import provenance, version ve explicit rule’lardan oluşan Framework Knowledge Layer’dır.

## Bu PoC gerçekte ne yapar?

```text
Customer repository
  → generic Python AST learning
  → structured FrameworkRule records + evidence/import metadata
  → task-aware CodingContext assembly
  → context-only deterministic generator
  → build + tests + AST compliance validation
  → LangGraph final state
```

Learner herhangi bir müşteri adı veya framework sembolü aramaz. Tekrarlanan service class’lardan şunları aggregate eder:

- ortak base class
- ortak decorator
- `__init__` içindeki `self.<attribute> = <dependency>(...)` dependency pattern’i
- aynı dependency attribute üzerinde ortak method call
- `from ... import ...` import provenance

Bir rule yalnızca minimum evidence ve confidence eşiğini geçtiğinde `active` olur; aksi halde `candidate` kalır.

## Aktif FrameworkRule türleri

| Rule | Anlamı | Import metadata |
|---|---|---|
| `service.base_class` | Service’in ortak base class’ı | `import_module` |
| `service.required_decorator` | Service decorator’ı | `import_module` |
| `logging.logger_class` | Constructor’da instantiate edilen dependency tipi | `import_module` |
| `logging.logger_attribute` | Dependency’nin `self` attribute adı | — |
| `logging.required_method` | Dependency attribute üzerinde ortak çağrılan method | — |
| `logging.forbidden_call` | Opsiyonel, imported/human-authored policy rule | — |

`logging.forbidden_call` validator tarafından generic olarak desteklenir. Negatif policy birden çok doğru örnekten güvenilir biçimde çıkarılamayacağı için bu minimal PoC onu otomatik infer etmez; ileride human approval veya policy import ile eklenir.

## İki framework demosu

### Framework A

Customer repository şunları içerir:

```python
from app.framework import BaseService, CompanyLogger, business_service

@business_service
class OrderService(BaseService):
    def __init__(self) -> None:
        self.logger = CompanyLogger(__name__)

    def create_order(self) -> None:
        self.logger.info("Order created")
```

Runtime’da öğrenilen rule değerleri:

```text
service.base_class = BaseService
service.required_decorator = business_service
logging.logger_class = CompanyLogger
logging.logger_attribute = logger
logging.required_method = info
```

Aynı product binary’nin ürettiği service:

```python
from app.framework import BaseService, CompanyLogger, business_service

@business_service
class CustomerAccountService(BaseService):
    def __init__(self) -> None:
        self.logger = CompanyLogger(__name__)

    def get_account(self, account_id: str) -> dict[str, str]:
        self.logger.info("Retrieving customer account")
        return {"account_id": account_id}
```

### Framework B

İkinci customer repository tamamen farklı isimler kullanır:

```python
from app.enterprise_framework import EnterpriseLog, FrameworkComponent, managed_component

@managed_component
class OrderService(FrameworkComponent):
    def __init__(self) -> None:
        self.log = EnterpriseLog(__name__)

    def create_order(self) -> None:
        self.log.audit("Order created")
```

Runtime’da öğrenilen rule değerleri:

```text
service.base_class = FrameworkComponent
service.required_decorator = managed_component
logging.logger_class = EnterpriseLog
logging.logger_attribute = log
logging.required_method = audit
```

**Platform source code değişmeden** üretilen service:

```python
from app.enterprise_framework import EnterpriseLog, FrameworkComponent, managed_component

@managed_component
class CustomerAccountService(FrameworkComponent):
    def __init__(self) -> None:
        self.log = EnterpriseLog(__name__)

    def get_account(self, account_id: str) -> dict[str, str]:
        self.log.audit("Retrieving customer account")
        return {"account_id": account_id}
```

Ayrıca mutation test’i, Framework B’de yalnızca customer repository içindeki `FrameworkComponent` sembolünü `DomainUnit` ile değiştirir. Product source’a dokunulmadan generated service `CustomerAccountService(DomainUnit)` olur.

## Çalıştırma (Windows / Git Bash)

```bash
uv venv .venv
uv pip install --python .venv/Scripts/python.exe 'langgraph>=0.2,<1' pytest

# Tüm acceptance testleri
PYTHONPATH=src .venv/Scripts/python.exe -m pytest -q

# Offline deterministic quickstart (boş bir output workspace ile)
mkdir -p .poc-run && cp -R examples/sample_customer_repo .poc-run/customer-repo && PYTHONPATH=src .venv/Scripts/python.exe -m agentic_platform.cli run --repository .poc-run/customer-repo --workspace .poc-run --task 'Create CustomerAccountService with method get_account(account_id)' --deterministic
```

CLI lifecycle komutları explicit’tir ve terminale tek satır JSON outcome yazar:

```bash
# Bir kez öğren ve bilgiyi .poc-run/framework_knowledge.sqlite içine kaydet
PYTHONPATH=src .venv/Scripts/python.exe -m agentic_platform.cli learn --repository .poc-run/customer-repo --workspace .poc-run --deterministic

# Yalnızca mevcut bilgiyi kullanarak geliştir (öğrenme yapmaz)
PYTHONPATH=src .venv/Scripts/python.exe -m agentic_platform.cli develop --repository .poc-run/customer-repo --workspace .poc-run --task 'Create PaymentHistoryService with method list_history(customer_id)' --deterministic
```

`run`, operator kolaylığı için `learn` ve `develop` fazlarını sıralı olarak birleştirir. `develop` için task zorunludur ve knowledge database yoksa nonzero JSON hata ile biter. CLI yalnızca local repository path’lerini kabul eder; deterministic modda network endpoint’i çağırmaz.

Kalıcı çalıştırma artefact’ları:

```text
.poc-run/
├── framework_knowledge.sqlite
└── customer-repo/
    ├── app/customer_account_service.py
    └── tests/test_customer_account_service.py
```

## Acceptance testleri

`tests/integration/test_poc_workflow.py` aşağıdakileri gerçek dosya/command execution ile doğrular:

1. Framework A rule discovery, imports, generation, build, pytest ve compliance.
2. Framework B için product code değişmeden aynı workflow.
3. Framework B mutation: base class rename → generated source da rename’i kullanır.
4. `src/agentic_platform` altında customer-specific framework symbol scan’i.
5. Unsupported task’in partial LangGraph state ile `KeyError` olmadan finalize edilmesi.
6. Temporary workspace ile CLI çalışma akışı.

## Güvenlik ve sınırlar

PoC yalnızca repository read/write, build, test ve validation capability’lerini verir. `shell_command`, `database_write`, `git_commit` ve `git_push` varsayılan capability grant içinde değildir.

Bu iterasyonun kasıtlı limitleri:

- Sadece Python AST ve `*Service` convention’ı desteklenir.
- Semantic/vector retrieval yoktur; representative service snippet’leri AST/source’dan alınır.
- SQLite tek-process demo store’dur; versioned tenant store değildir.
- Model local deterministic adapter’dır; gerçek provider adapters sonraki iterasyondadır.
- Retry/checkpoint/human approval production tasarımında bulunur, minimal working graph’ta uygulanmamıştır.

Detaylı hedef mimari ve sonraki üretim genişletme sınırları için [ARCHITECTURE.md](ARCHITECTURE.md) dosyasına bakın.
