# Agentic Framework Intelligence Platform

On-premise kurulabilir, şirketin mevcut repository'lerinden **explicit Framework Intelligence** öğrenen ve LangGraph ile framework-aware geliştirme akışı yürüten Python PoC.

> LangGraph yalnızca kontrol akışıdır. Ürünün kaynak gerçeği; versioned rules, evidence, confidence, örnekler ve dependency bağlamını taşıyan Framework Knowledge Layer'dır.

## Neler gerçek olarak çalışıyor?

Bu PoC mock/no-op agent zinciri değildir. `examples/sample_customer_repo` içindeki gerçek Python repository'si çalışma alanına kopyalanır ve aşağıdaki akış LangGraph `StateGraph` üzerinde uygulanır:

1. Python AST tarayıcı üç mevcut servisten framework pattern'lerini deterministik olarak çıkarır.
2. Minimum 3 evidence ve %80 confidence eşiğini geçen kurallar SQLite knowledge store'a yazılır.
3. Task için yalnızca `service.*` ve `logging.*` kuralları, temsilî örnekler ve dependency yolu retrieve edilir.
4. Provider-neutral `CodingModel` portunun local deterministic PoC implementasyonu `CustomerAccountService` ve onun pytest testini üretir.
5. Permission-checked araçlar `compileall` ve `pytest` çalıştırır.
6. Bağımsız AST tabanlı validator base class, decorator, logging ve `print()` yasağını doğrular.
7. Sonuç; build/test/validation artefact'ları ve event'lerle birlikte LangGraph state olarak döner.

PoC'ın bilinçli sınırı: yalnızca Python için dar bir vertical slice uygular. Mimari dokümanındaki Tree-sitter/JavaParser ve model sağlayıcı adaptörleri üretim genişletme noktalarıdır; desteklenmiyorlarmış gibi davranmaz.

## Hızlı başlangıç (Windows / Git Bash)

```bash
# Repo kökünde
uv venv .venv
uv pip install --python .venv/Scripts/python.exe 'langgraph>=0.2,<1' pytest
PYTHONPATH=src .venv/Scripts/python.exe -m pytest -q

# Kalıcı PoC artefact'ları ile çalıştırma (editable install gerektirmez)
PYTHONPATH=src .venv/Scripts/python.exe -m agentic_platform.cli --workspace .poc-run
```

Başarılı çıktıda şunlar görülür:

```json
{
  "status": "succeeded",
  "generated_files": ["app/customer_account_service.py"],
  "build_result": {"passed": true},
  "test_result": {"passed": true},
  "validation_report": {"passed": true}
}
```

`--workspace .poc-run` sonrasında inceleyebileceğiniz artefact'lar:

```text
.poc-run/
├── framework_knowledge.sqlite   # persist edilmiş structured rules + evidence
└── customer-repo/
    ├── app/customer_account_service.py
    └── tests/test_customer_account_service.py
```

## Testler

```bash
PYTHONPATH=src .venv/Scripts/python.exe -m pytest tests/integration/test_poc_workflow.py -v
```

Bu entegrasyon testi yalnızca state alanlarını kontrol etmez: oluşturulan dosyayı okur ve LangGraph içinden tetiklenen gerçek compile/test/compliance sonuçlarını doğrular.

## Mimari ve karar kayıtları

Detaylı tasarım: [ARCHITECTURE.md](ARCHITECTURE.md)

Doküman şunları içerir:

- Üç ana katman ve Mermaid component diyagramı
- Initial/incremental learning akışı
- LangGraph state, node, conditional edge, retry/human gate tasarımı
- Customer → Framework → Version → Project → Module modeli
- Evidence, conflict, confidence, human review ve provenance şeması
- PostgreSQL/Qdrant/Tree-sitter/OTel seçimleri ve gerekçeleri
- On-prem isolation, secrets, capability policy ve observability
- IDE/CLI/REST/MCP/Claude Code/Codex için bağımsız extension boundary

## Production'a ilerleme sırası

1. SQLite adapter'ını Alembic migration'lı PostgreSQL implementation ile değiştirin; `tenant_id` RLS ve immutable knowledge snapshots ekleyin.
2. `semantic_chunk` portunu Qdrant (veya küçük kurulumlar için pgvector) adapter'ına bağlayın.
3. Python AST adapter'ına Tree-sitter tabanlı dil adapter registry'si; Java/Kotlin için JavaParser/Semgrep zenginleştirmesi ekleyin.
4. Git/SVN connector'larını revision/diff ve değişiklik-etki analiziyle ekleyin; yalnızca değişen dosyaların observation/chunk kayıtlarını upsert edin.
5. `CodingModel` portuna OpenAI, Anthropic, Gemini ve OpenAI-compatible/local adaptörlerini ekleyin. Model seçimi konfigürasyondan gelsin; core'a sağlayıcı SDK'sı taşımayın.
6. Postgres LangGraph checkpointer, OTel exporter, worktree/container sandbox ve insan onay interrupt'larını production deployment'a ekleyin.

## Güvenlik varsayımları

PoC yalnızca repository read/write, build, test ve static validation capability'lerini verir. `shell_command`, `database_write`, `git_commit` ve `git_push` varsayılan olarak yoktur. Production'da her run tenant-scoped bir immutable capability grant, sandboxed worktree, allowlisted command ve secret-reference ile başlamalıdır.
