Sen deneyimli bir **AI Platform Architect, Agentic Systems Engineer ve Senior Software Engineer** olarak çalışacaksın.

Amacımız herhangi bir şirkete özel olmayan, farklı şirketlerin kendi yazılım framework'lerini, mimari kurallarını, coding convention'larını ve geliştirme pattern'lerini öğrenebilen ve daha sonra bu bilgilere göre yazılım geliştirme sürecini yöneten **genel amaçlı, on-premise kurulabilir bir Agentic Development Platform** geliştirmek.

Bu ürün tek bir şirketin framework'üne göre hard-code edilmeyecek.

Her müşteri kendi ortamında ürünü kuracak, kendi repository'lerini sisteme tanıtacak ve sistem müşterinin framework'ünü analiz ederek kendi **Framework Intelligence** katmanını oluşturacak.

## Temel mimari kararı

Agentic workflow orchestration için **LangGraph** kullan.

LangGraph framework bilgisinin kendisi değildir.

Mimariyi üç ana katmana ayır:

1. **Framework Learning Engine**
2. **Framework Knowledge Layer**
3. **LangGraph Agentic Development Engine**

Bu ayrımı tasarım boyunca koru.

---

# 1. Framework Learning Engine

Bu katmanın görevi müşterinin mevcut yazılım repository'lerini analiz ederek şirketin framework'ünü anlamaktır.

Kaynaklar şunlar olabilir:

* Git repository
* SVN repository
* source code
* configuration files
* Maven / Gradle files
* internal libraries
* framework source code
* existing applications
* test code
* documentation
* README
* architecture documents
* API definitions
* database/query examples

Sistem yalnızca embedding + similarity search yapan basit bir RAG sistemi olmamalı.

Repository içerisindeki yapıları analiz ederek **structured framework knowledge** çıkarmalı.

Örneğin şunları öğrenebilmelidir:

* service nasıl oluşturuluyor?
* controller yapısı nasıl?
* base class'lar neler?
* interface kullanımı nasıl?
* dependency injection pattern'i ne?
* annotation'lar nasıl kullanılıyor?
* exception handling standardı nedir?
* logging nasıl yapılıyor?
* transaction yönetimi nasıl?
* query nasıl oluşturuluyor?
* database erişimi nasıl?
* DTO / model / entity dönüşümleri nasıl?
* validation nasıl?
* config nasıl okunuyor?
* API geliştirme pattern'i nasıl?
* testler nasıl yazılıyor?
* naming convention nedir?
* package convention nedir?
* modüller birbirleriyle nasıl iletişim kuruyor?
* common/shared library'ler hangileri?
* hangi pattern'ler zorunlu?
* hangi pattern'ler yasak?
* legacy ve yeni implementasyonlar nasıl ayırt edilebilir?

Framework Learning Engine için gerekli agent/node tasarımını oluştur.

Örneğin ihtiyaç varsa:

* Repository Scanner
* Architecture Detector
* Dependency Analyzer
* Code Pattern Analyzer
* Framework Rule Extractor
* Example Miner
* Rule Validator
* Knowledge Indexer

kullanılabilir.

Ancak gereksiz yere her işi ayrı agent'a bölme.

Bir iş deterministic kod ile daha güvenilir yapılabiliyorsa LLM agent kullanma.

---

# 2. Framework Knowledge Layer

Framework Learning Engine tarafından öğrenilen bilgi merkezi ve tekrar kullanılabilir bir knowledge layer içinde saklanmalı.

Knowledge iki farklı biçimde tutulmalı.

## A. Unstructured / semantic knowledge

Örneğin:

* source code parçaları
* örnek implementasyonlar
* documentation
* framework kaynak kodu

Bunlar semantic/code retrieval için kullanılabilir.

Vector database kullanılabilir.

Ancak vector database'i tek bilgi kaynağı haline getirme.

## B. Structured Framework Knowledge

Öğrenilen kurallar explicit olarak saklanmalı.

Örneğin:

```yaml
service:
  base_class: AbstractService
  required_annotations:
    - BusinessService

exception:
  allowed_base_classes:
    - BusinessException
  forbidden:
    - RuntimeException

logging:
  required_logger: CompanyLogger
  forbidden:
    - System.out.println

query:
  naming_pattern: "*Query"
  execution_method: QueryExecutor
```

Gerçek schema'yı sen tasarla.

Structured knowledge için aşağıdakileri değerlendir:

* relational database
* document database
* graph database
* JSON/YAML rule store
* vector database metadata

Teknoloji seçimini gerekçelendir.

Framework bilgisinin **versioned** olması gerekiyor.

Örneğin:

Framework v1
Framework v2
Framework v3

aynı müşteride farklı application'lar tarafından kullanılabilir.

Knowledge şu seviyelerde ayrılabilmeli:

Customer
→ Framework
→ Framework Version
→ Project/Application
→ Module

---

# 3. LangGraph Agentic Development Engine

Development workflow'u LangGraph üzerinden yönet.

Ama tüm workflow'u autonomous agent haline getirme.

**Deterministic + Agentic hybrid architecture** kullan.

Örneğin:

User Request
↓
Task Analysis
↓
Framework Context Retrieval
↓
Codebase Context Retrieval
↓
Planning
↓
Implementation
↓
Compile
↓
Tests
↓
Framework Compliance Validation
↓
Static Analysis
↓
Review
↓
Final Result

Burada:

Agentic olabilecek aşamalar:

* requirement analysis
* planning
* implementation
* code review
* architecture reasoning

Deterministic olması gereken aşamalar:

* repository operations
* compilation
* tests
* lint
* static analysis
* dependency scanning
* syntax checks
* schema validation

LangGraph'ın şu özelliklerini gerektiğinde kullan:

* State
* Nodes
* Edges
* conditional edges
* checkpointing
* persistence
* retry
* interrupts
* human-in-the-loop
* subgraphs

Workflow başarısız olduğunda örneğin:

Implementation
↓
Compile
↓
FAIL
↓
Compiler Error Analysis
↓
Implementation

şeklinde kontrollü feedback loop oluşabilmeli.

Sonsuz retry engellenmeli.

Retry budget uygulanmalı.

---

# Framework-aware Coding

Coding agent doğrudan bütün repository'yi context'e almamalı.

Bir görev geldiğinde önce:

1. task analiz edilmeli
2. hangi framework bilgilerinin gerekli olduğu belirlenmeli
3. ilgili framework rule'ları getirilmeli
4. benzer doğru implementasyonlar bulunmalı
5. ilgili source-code dependency'leri bulunmalı
6. coding agent'a minimum fakat yeterli context verilmelidir

Örneğin:

"CustomerAccountService oluştur"

isteğinde sistem aşağıdakileri otomatik olarak bulabilmeli:

* service creation rules
* base class
* required annotations
* exception rules
* logging rules
* transaction rules
* benzer servisler
* kullanılan repository/query pattern'leri

ve ardından kod üretmeli.

---

# Framework Compliance Validator

Sistemde ayrıca bağımsız bir Framework Compliance mekanizması tasarla.

Generated code için:

* required pattern kullanılmış mı?
* yasak pattern var mı?
* doğru base class kullanılmış mı?
* doğru annotation kullanılmış mı?
* naming convention doğru mu?
* exception standardına uyuyor mu?
* logging standardına uyuyor mu?
* dependency usage doğru mu?

kontrol edilebilmeli.

Mümkün olan kontroller deterministic olmalı.

LLM yalnızca semantic/architectural değerlendirme gereken yerlerde kullanılmalı.

---

# Öğrenme mekanizması

Framework Learning Engine tek seferlik ingestion olmamalı.

Repository değiştikçe sistem değişiklikleri öğrenebilmeli.

Şunları tasarla:

Initial Learning

ve

Incremental Learning

Initial:

Repository
↓
Full Analysis
↓
Framework Knowledge

Incremental:

Git/SVN Change
↓
Changed Files Detection
↓
Impact Analysis
↓
Relevant Knowledge Update

Her commit sonrası bütün repository yeniden embed edilmemeli.

Incremental indexing ve incremental rule discovery tasarla.

---

# Confidence sistemi

LLM tarafından çıkarılan framework kurallarını kesin gerçek kabul etme.

Her framework rule için mümkünse:

* confidence score
* evidence
* source files
* example count
* conflicting examples
* framework version
* discovery timestamp

sakla.

Örneğin:

```json
{
  "rule": "Services extend AbstractService",
  "confidence": 0.96,
  "evidenceCount": 148,
  "exceptions": 3,
  "sources": [
    "customer-service/...",
    "payment-service/..."
  ]
}
```

Bir pattern 2 dosyada görülüyorsa bunu framework standardı olarak ilan etme.

Evidence-based rule discovery kullan.

---

# Human Validation

Framework discovery sırasında bazı kurallar için insan onayı gerekebilir.

Örneğin:

Detected Rule:

"All REST services extend BaseRestService"

Evidence:
94 / 97 implementations

Confidence:
0.97

Kullanıcı:

Approve
Reject
Edit

diyebilmeli.

Human-approved rule ile AI-inferred rule birbirinden ayrılmalı.

---

# Model bağımsızlığı

Architecture herhangi bir LLM sağlayıcısına bağımlı olmamalı.

Desteklenebilir modeller:

* OpenAI
* Anthropic
* Gemini
* open-source/local models
* OpenAI-compatible endpoints

Bir model abstraction layer oluştur.

Farklı görevler farklı modellere yönlendirilebilmeli.

Örneğin:

Planning → güçlü reasoning modeli

Simple classification → küçük model

Coding → coding modeli

Embedding → embedding modeli

Ancak ilk PoC'de gereksiz model routing complexity oluşturma.

---

# Deployment

Ürün enterprise müşterilere **on-premise** kurulabilir olmalı.

Bu nedenle:

* source code şirket dışına çıkmamalı seçeneği bulunmalı
* local LLM kullanılabilmeli
* local embedding modeli kullanılabilmeli
* local vector DB kullanılabilmeli
* credentials güvenli yönetilmeli
* multi-tenant architecture değerlendirilmeli
* customer isolation tasarlanmalı

Cloud zorunluluğu yaratma.

---

# Güvenlik

Agent'ın terminal erişimini kontrolsüz bırakma.

Tool permission modeli tasarla.

Örneğin:

read_repository
write_repository
run_build
run_test
database_read
database_write
shell_command
git_commit
git_push

gibi ayrı izinlar bulunabilir.

Default olarak destructive operations kapalı olmalı.

---

# Observability

Her development run için aşağıdakiler izlenebilir olmalı:

* workflow execution
* node execution
* agent decisions
* retrieved knowledge
* framework rules used
* tools called
* generated changes
* validation results
* token usage
* execution duration
* failures
* retries

Debug edilemeyen black-box agent sistemi oluşturma.

---

# İlk görev

Önce doğrudan büyük miktarda kod yazma.

İlk olarak mevcut çalışma dizinini/repository'yi incele.

Eğer repository boşsa projeyi sıfırdan oluştur.

Ardından aşağıdaki çıktıları üret.

## A. System Architecture

Detaylı component architecture oluştur.

Aşağıdaki katmanların ilişkisini açıkça göster:

Framework Learning Engine
Framework Knowledge Layer
LangGraph Orchestrator
Development Agents
Tool Layer
Model Gateway
Customer Repository
Observability
Security

Mermaid architecture diagram oluştur.

## B. LangGraph Graph Design

LangGraph state modelini tasarla.

Node'ları belirle.

Node responsibility'lerini açıkla.

Conditional edge'leri belirle.

Retry ve failure path'lerini göster.

## C. Framework Knowledge Model

Structured framework knowledge için data model/schema tasarla.

Rules, examples, evidence, confidence ve version bilgisini içersin.

## D. Repository Structure

Production-oriented repository/package yapısını tasarla.

Örneğin:

```text
src/
  framework_learning/
  framework_knowledge/
  orchestration/
  agents/
  retrieval/
  tools/
  models/
  validation/
  observability/
  security/
```

Ama daha iyi bir yapı varsa onu kullan.

## E. Technology Selection

Aşağıdakiler için teknoloji öner:

* LangGraph persistence
* relational/document database
* vector database
* code parsing
* AST analysis
* repository integration
* embeddings
* model abstraction
* observability

Her seçimin gerekçesini belirt.

Gereksiz teknoloji ekleme.

## F. PoC

Daha sonra minimal fakat gerçek çalışan PoC oluştur.

PoC şu senaryoyu göstermeli:

1. örnek bir repository alınır
2. repository analiz edilir
3. bazı framework pattern'leri keşfedilir
4. knowledge store'a yazılır
5. kullanıcı development task verir
6. gerekli framework context retrieve edilir
7. coding agent değişiklik üretir
8. validator framework kurallarını kontrol eder
9. test/build çalıştırılır
10. sonuç LangGraph state üzerinden tamamlanır

Mock edilmiş, gerçekte hiçbir şey yapmayan agent zinciri oluşturma.

En azından temel workflow gerçekten executable olsun.

---

# Mimari prensipler

Aşağıdaki prensiplere özellikle dikkat et:

1. LLM her problemi çözmek için kullanılmamalı.
2. Deterministic çözüm mümkünse deterministic çözüm tercih edilmeli.
3. Vector DB framework intelligence'ın tamamı değildir.
4. Framework knowledge açık ve sorgulanabilir olmalı.
5. Her rule evidence ile ilişkilendirilmeli.
6. Agent sayısını gereksiz yere artırma.
7. Context window'a bütün repository'yi doldurma.
8. Retrieval task-aware olmalı.
9. Workflow observable olmalı.
10. Workflow reproducible olmalı.
11. Customer-specific logic core product'a hard-code edilmemeli.
12. Framework versioning ilk günden düşünülmeli.
13. Security ve tool permissions ilk sınıf vatandaş olmalı.
14. LangGraph yalnızca orchestration katmanıdır.
15. Ürünün esas IP'si Framework Intelligence sistemidir.

---

# Çalışma yöntemi

Her önemli mimari karar öncesinde:

* problemi belirt
* seçenekleri değerlendir
* seçimini yap
* gerekçesini açıkla

Ancak analysis paralysis oluşturma.

Makul varsayımlar yaparak ilerle.

Belirsiz küçük detaylar için sürekli benden onay isteme.

Production-quality yaklaşım kullan.

Overengineering yapma.

İlk hedef:

**çalışan, genişletilebilir ve gerçek bir Framework Intelligence + Agentic Development PoC oluşturmak.**

Kod yazarken temiz architecture, typing, testability, dependency boundaries ve configuration management kullan.

README içerisinde sistemi nasıl çalıştıracağımı ve örnek senaryoyu nasıl test edeceğimi açıkça yaz.

Son olarak oluşturduğun mimarinin gelecekte:

* IDE plugin
* Claude Code integration
* Codex integration
* CLI
* REST API
* MCP server

üzerinden kullanılabilmesini engelleyecek bir bağımlılık oluşturma.
