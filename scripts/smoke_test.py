"""Quick smoke test for data loading."""
from app.catalog_loader import load_catalog
from app.repository import repository

load_catalog()
print(f"Catalog: {len(repository.products)} products")

from app.synonyms import expand_terms_with_synonyms
result = expand_terms_with_synonyms(["системник"])
print(f"Synonyms for 'системник': {result}")

from app.evaluation import EVALUATION_CASES
print(f"Evaluation cases: {len(EVALUATION_CASES)}")

from app.demo_scenarios import get_demo_scenarios
scenarios = get_demo_scenarios()
print(f"Demo scenarios: {len(scenarios)}")
for s in scenarios:
    print(f"  - {s.key}: {s.title}")

print("\nAll checks passed!")
